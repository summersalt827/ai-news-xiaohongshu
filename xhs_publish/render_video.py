#!/usr/bin/env python3
"""Animated HTML → video with scene-switch transitions + TTS narration.

Generates animated card HTML pages (16:9 + 9:16), records each page
via Playwright frame capture, mixes in macOS TTS narration, and
concatenates scenes with FFmpeg xfade transitions.

Output per run:
  - *_video_16x9.mp4  (B站 1920×1080)
  - *_video_9x16.mp4  (小红书 1080×1920)
"""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════════

# macOS TTS voice (Mandarin female)
TTS_VOICE = "Tingting"

COVER_DURATION = 3.0  # seconds
CARD_DURATION = 5.0  # seconds per card
TRANSITION = 0.4  # crossfade seconds between scenes
FPS = 30

ASPECTS = {
    "16:9": dict(width=3840, height=2160),
    "9:16": dict(width=2160, height=3840),
}

FFMPEG_PATH = str(
    Path.home() / "Library/Application Support/bilibili/ffmpeg/ffmpeg"
)
if not Path(FFMPEG_PATH).is_file():
    FFMPEG_PATH = shutil.which("ffmpeg") or "ffmpeg"

# ═══════════════════════════════════════════════════════════════════
# Animation CSS (shared)
# ═══════════════════════════════════════════════════════════════════

ANIM_CSS = """
@keyframes slideUp {
  from { opacity: 0; transform: translateY(40px); }
  to   { opacity: 1; transform: translateY(0); }
}
@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 1; }
}
@keyframes scaleIn {
  from { opacity: 0; transform: scale(0.9); }
  to   { opacity: 1; transform: scale(1); }
}
@keyframes slideLeft {
  from { opacity: 0; transform: translateX(-60px); }
  to   { opacity: 1; transform: translateX(0); }
}
@keyframes slideRight {
  from { opacity: 0; transform: translateX(60px); }
  to   { opacity: 1; transform: translateX(0); }
}
.anim { animation-fill-mode: both; }
.anim-slide-up  { animation: slideUp 0.6s ease-out both; }
.anim-fade-in   { animation: fadeIn 0.5s ease-out both; }
.anim-scale-in  { animation: scaleIn 0.5s ease-out both; }
.anim-slide-l   { animation: slideLeft 0.5s ease-out both; }
.anim-slide-r   { animation: slideRight 0.5s ease-out both; }
.delay-1 { animation-delay: 0.0s; }
.delay-2 { animation-delay: 0.35s; }
.delay-3 { animation-delay: 0.7s; }
.delay-4 { animation-delay: 1.05s; }
.delay-5 { animation-delay: 1.4s; }
.delay-6 { animation-delay: 1.75s; }
.delay-7 { animation-delay: 2.1s; }
"""

# ═══════════════════════════════════════════════════════════════════
# HTML Generators
# ═══════════════════════════════════════════════════════════════════

def _color_for(idx: int) -> str:
    return ["#d97757", "#629987", "#6a9bcc", "#7b7cb8", "#c46686"][(idx - 1) % 5]


def _render_card_html(item: dict, idx: int, total: int,
                      date_str: str, aspect: str) -> str:
    """Animated single-card HTML page."""
    w, h = ASPECTS[aspect]["width"], ASPECTS[aspect]["height"]
    date_disp = date.fromisoformat(date_str).strftime("%Y年%m月%d日")
    emoji_t = html.escape(item.get("emoji", "📌"))
    title = html.escape(item.get("title", ""))
    summary = html.escape(item.get("summary", ""))
    detail = html.escape(item.get("detail", summary))
    why_care = html.escape(item.get("why_care", ""))
    source_note = html.escape(item.get("source_note", ""))
    kps = item.get("key_points", [])
    if isinstance(kps, str):
        kps = [p.strip() for p in kps.split("\n") if p.strip()][:3]

    is_github = "github" in source_note.lower()
    is_landscape = aspect == "16:9"

    # -- GitHub badge --
    gh_badge_html = ""
    if is_github:
        gh_badge_html = '<div class="github-badge anim anim-scale-in delay-1">⭐ GitHub 热门项目</div>'

    # -- key points HTML --
    kp_colors = ["#d97757", "#629987", "#6a9bcc"]
    kp_html = ""
    if kps:
        items = []
        for i, pt in enumerate(kps[:3]):
            c = kp_colors[i]
            items.append(
                f'<span class="kp-item anim anim-slide-up delay-{4+i}">'
                f'<b style="color:{c}">{"①②③"[i]}</b> {html.escape(pt)}</span>'
            )
        label_delay = "4" if is_landscape else "4"
        kp_html = (
            f'<div class="key-points anim anim-fade-in delay-{label_delay}">'
            + "".join(items)
            + "</div>"
        )

    if is_landscape:
        return _render_card_16x9(w, h, emoji_t, title, summary, detail,
                                 why_care, source_note, kps, kp_html,
                                 idx, total, date_disp, gh_badge_html)
    else:
        return _render_card_9x16(w, h, emoji_t, title, summary, detail,
                                 why_care, source_note, kps, kp_html,
                                 idx, total, date_disp, gh_badge_html)


def _render_info_boxes(items: list) -> str:
    """Render info-box list for right card."""
    if not items:
        return ""
    parts = []
    for active, label, text in items:
        cls = "info-box active" if active else "info-box"
        parts.append(
            f'<div class="{cls} anim anim-fade-in delay-4">'
            f'<span class="label">{label}</span>'
            f'{html.escape(text)}</div>'
        )
    return "".join(parts)


def caption_pill_html(text: str) -> str:
    """Bottom caption pill."""
    if not text:
        return ""
    return f'<div class="caption-pill anim anim-slide-up delay-5">{text}</div>'


def _render_card_16x9(w, h, emoji, title, summary, detail, why_care,
                      source, kps, kp_html, idx, total, date_disp,
                      gh_badge_html="") -> str:
    """Design-doc style — light gradient bg, blue/teal palette, hard-shadow cards."""
    is_github = bool(gh_badge_html)
    cat_label = "GitHub 热门" if is_github else "AI 要闻"
    cat_class = "type-green" if is_github else "type-blue"
    accent_color = "#1ca77a" if is_github else "#1d6fb5"
    card_accent_bg = "#e8f5e9" if is_github else "#e8f0fa"

    hl = _split_headline(title)
    hl_title = hl.get("cn_punchline", title)

    # Card scale: use w/2400 to fit content within fixed 16:9 frame
    fs = lambda base: int(base * w / 2400)

    # Map content to input-box style items (dynamic, no text truncation)
    info_items = []
    if summary:
        info_items.append((True, "发生了什么？", summary))
    if why_care:
        info_items.append((False, "为什么值得关注", why_care))

    # Bottom caption from key points (no truncation)
    caption_text = ""
    if kps:
        caption_text = html.escape(kps[0])

    # Left card content (no truncation)
    left_title_short = hl.get("cn_keyword", title)
    left_sub = hl.get("en_keyword", cat_label)

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Noto+Sans+SC:wght@500;700;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{w}px;height:{h}px;overflow:hidden;
  font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  background:linear-gradient(90deg,#f9fafb 0%,#ffffff 50%,#f9fafb 100%);
  color:#163f77;display:flex;align-items:flex-start;justify-content:center;
  -webkit-font-smoothing:antialiased}}
.stage{{width:{w}px;height:100%;padding:{fs(60)}px {fs(120)}px;
  padding-bottom:{fs(100)}px;display:flex;flex-direction:column}}
.top-row{{display:flex;justify-content:space-between;align-items:center;margin-bottom:{fs(24)}px;flex-shrink:0}}
.tag{{font-family:'Space Mono',monospace;font-size:{fs(24)}px;font-weight:700;
  color:#1ca77a;letter-spacing:1px;display:flex;align-items:center;gap:{fs(12)}px}}
.tag .dot{{width:{fs(16)}px;height:{fs(16)}px;border-radius:50%;background:#1ca77a;display:inline-block;flex-shrink:0}}
.meta{{font-family:'Space Mono',monospace;font-size:{fs(20)}px;color:#60748a;letter-spacing:1px}}
.headline{{margin-bottom:{fs(28)}px;flex-shrink:0}}
.headline h1{{font-size:{fs(84)}px;font-weight:900;color:#124783;line-height:1.08;letter-spacing:-1px}}
.headline .sub{{font-size:{fs(24)}px;font-weight:600;color:#60748a;margin-top:{fs(10)}px}}
.two-col{{display:flex;gap:{fs(48)}px;flex:1 1 auto;margin-bottom:{fs(24)}px;min-height:0}}
.left-card{{width:{fs(480)}px;background:{card_accent_bg};border:4px solid #1c4f8d;
  border-radius:{fs(20)}px;padding:{fs(32)}px;display:flex;flex-direction:column;
  box-shadow:{fs(12)}px {fs(12)}px 0 rgba(0,0,0,.07);flex-shrink:0}}
.left-card .lc-star{{font-family:'Space Mono',monospace;font-size:{fs(20)}px;
  font-weight:700;color:#1c4f8d;margin-bottom:{fs(28)}px;letter-spacing:1px}}
.left-card .lc-title{{font-size:{fs(60)}px;font-weight:900;color:#124783;line-height:1.08;word-break:break-word}}
.left-card .lc-desc{{font-family:'Space Mono',monospace;font-size:{fs(18)}px;
  color:#138d78;margin-top:{fs(14)}px;font-weight:700;word-break:break-word}}
.right-card{{flex:1 1 auto;background:#fff;border:4px solid #1c4f8d;border-radius:{fs(20)}px;
  padding:{fs(28)}px {fs(36)}px;display:flex;flex-direction:column;gap:{fs(14)}px;
  box-shadow:{fs(12)}px {fs(12)}px 0 rgba(0,0,0,.07);min-height:0;overflow-y:auto}}
.right-card .rc-title{{font-size:{fs(36)}px;font-weight:900;color:#123e74;
  margin-bottom:{fs(4)}px;word-break:break-word;flex-shrink:0}}
.info-box{{border-radius:{fs(10)}px;border:3px solid #e2e8f0;
  display:flex;align-items:flex-start;padding:{fs(10)}px {fs(18)}px;
  font-size:{fs(20)}px;font-family:'Space Mono',monospace;color:#475569;
  word-break:break-word;flex-shrink:0}}
.info-box.active{{border-color:#1ca77a;color:#178a70}}
.info-box .label{{font-weight:700;color:{accent_color};margin-right:{fs(8)}px;
  font-size:{fs(18)}px;white-space:nowrap;font-family:'Noto Sans SC',sans-serif;flex-shrink:0}}
.rc-footer{{font-family:'Space Mono',monospace;font-size:{fs(16)}px;color:#64748b;
  margin-top:auto;font-weight:600;flex-shrink:0;padding-top:{fs(8)}px}}
.caption-pill{{align-self:center;padding:{fs(14)}px {fs(36)}px;
  border:4px solid #17212d;border-radius:{fs(22)}px;background:#fff;
  font-size:{fs(24)}px;font-weight:900;color:#17212d;
  box-shadow:{fs(8)}px {fs(8)}px 0 rgba(0,0,0,.07);text-align:center;
  flex-shrink:0;word-break:break-word;max-width:{int(w * 0.85)}px;margin-top:{fs(16)}px}}
{ANIM_CSS}
</style></head><body>
<div class="stage">
<div class="top-row anim anim-fade-in delay-1">
  <div class="tag"><span class="dot"></span>{idx:02d} / {cat_label}</div>
  <div class="meta">{date_disp} · {html.escape(source)}</div>
</div>
<div class="headline anim anim-slide-l delay-2">
  <h1>{html.escape(hl_title)}</h1>
  <div class="sub">{html.escape(summary)}</div>
</div>
<div class="two-col">
  <div class="left-card anim anim-scale-in delay-3">
    <div class="lc-star">{emoji}</div>
    <div class="lc-title">{html.escape(left_title_short)}</div>
    <div class="lc-desc">{html.escape(left_sub)}</div>
  </div>
  <div class="right-card anim anim-slide-r delay-3">
    <div class="rc-title">{html.escape(hl_title)}</div>
    {_render_info_boxes(info_items)}
    <div class="rc-footer">{html.escape(source)} · {date_disp}</div>
  </div>
</div>
{caption_pill_html(caption_text)}
</div>
</body></html>"""


def _render_card_9x16(w, h, emoji, title, summary, detail, why_care,
                      source, kps, kp_html, idx, total, date_disp,
                      gh_badge_html="") -> str:
    """Design-doc style for 9:16 vertical — same palette, stacked layout."""
    is_github = bool(gh_badge_html)
    cat_label = "GitHub 热门" if is_github else "AI 要闻"
    card_accent_bg = "#e8f5e9" if is_github else "#e8f0fa"

    hl = _split_headline(title)
    hl_title = hl.get("cn_punchline", title)

    fs = lambda base: int(base * w / 1440)

    info_items = []
    if summary:
        info_items.append((True, "发生了什么？", summary))
    if detail and detail != summary:
        info_items.append((False, "深入了解一下", detail))
    if why_care:
        info_items.append((False, "为什么值得关注", why_care))

    caption_text = ""
    if kps:
        caption_text = html.escape(kps[0][:48])

    left_sub = hl.get("en_keyword", cat_label)[:28]

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Noto+Sans+SC:wght@500;700;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{w}px;height:{h}px;overflow:hidden;
  font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  background:linear-gradient(180deg,#f9fafb 0%,#ffffff 50%,#f9fafb 100%);
  color:#163f77;display:flex;align-items:center;justify-content:center;
  -webkit-font-smoothing:antialiased}}
.stage{{width:{w}px;height:{h}px;padding:{fs(80)}px {fs(80)}px {fs(120)}px {fs(80)}px;
  display:flex;flex-direction:column;position:relative}}
.top-row{{display:flex;justify-content:space-between;align-items:center;margin-bottom:{fs(40)}px}}
.tag{{font-family:'Space Mono',monospace;font-size:{fs(24)}px;font-weight:700;
  color:#1ca77a;letter-spacing:1px;display:flex;align-items:center;gap:{fs(12)}px}}
.tag .dot{{width:{fs(18)}px;height:{fs(18)}px;border-radius:50%;background:#1ca77a;display:inline-block}}
.meta{{font-family:'Space Mono',monospace;font-size:{fs(20)}px;color:#60748a;letter-spacing:1px}}
.headline{{margin-bottom:{fs(50)}px}}
.headline h1{{font-size:{fs(88)}px;font-weight:900;color:#124783;line-height:1.08;letter-spacing:-1px}}
.headline .sub{{font-size:{fs(28)}px;font-weight:600;color:#60748a;margin-top:{fs(14)}px}}
.top-card{{background:{card_accent_bg};border:4px solid #1c4f8d;
  border-radius:{fs(24)}px;padding:{fs(40)}px;margin-bottom:{fs(36)}px;
  box-shadow:{fs(14)}px {fs(14)}px 0 rgba(0,0,0,.07);display:flex;align-items:center;gap:{fs(30)}px}}
.top-card .tc-emoji{{font-size:{fs(56)}px}}
.top-card .tc-info{{display:flex;flex-direction:column;gap:{fs(8)}px}}
.top-card .tc-title{{font-size:{fs(40)}px;font-weight:900;color:#124783}}
.top-card .tc-desc{{font-family:'Space Mono',monospace;font-size:{fs(22)}px;color:#138d78;font-weight:700}}
.info-card{{background:#fff;border:4px solid #1c4f8d;border-radius:{fs(24)}px;
  padding:{fs(36)}px {fs(42)}px;display:flex;flex-direction:column;gap:{fs(20)}px;
  box-shadow:{fs(14)}px {fs(14)}px 0 rgba(0,0,0,.07);flex:1}}
.info-card .rc-title{{font-size:{fs(46)}px;font-weight:900;color:#123e74;margin-bottom:{fs(6)}px}}
.ibox{{min-height:{fs(66)}px;border-radius:{fs(14)}px;border:3px solid #e2e8f0;
  display:flex;align-items:center;padding:{fs(14)}px {fs(22)}px;
  font-size:{fs(22)}px;font-family:'Space Mono',monospace;color:#475569;flex:1}}
.ibox.active{{border-color:#1ca77a;color:#178a70}}
.ibox .label{{font-weight:700;color:#1d6fb5;margin-right:{fs(12)}px;
  font-size:{fs(20)}px;white-space:nowrap;font-family:'Noto Sans SC',sans-serif}}
.ibox .label.gh{{color:#1ca77a}}
.rc-footer{{font-family:'Space Mono',monospace;font-size:{fs(20)}px;color:#64748b;
  margin-top:{fs(14)}px;font-weight:600}}
.caption-pill{{align-self:center;padding:{fs(20)}px {fs(44)}px;
  border:4px solid #17212d;border-radius:{fs(28)}px;background:#fff;
  font-size:{fs(30)}px;font-weight:900;color:#17212d;
  box-shadow:{fs(10)}px {fs(10)}px 0 rgba(0,0,0,.07);text-align:center;
  max-width:{w * 0.8}px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
  margin-top:{fs(40)}px}}
{ANIM_CSS}
</style></head><body>
<div class="stage">
<div class="top-row anim anim-fade-in delay-1">
  <div class="tag"><span class="dot"></span>{idx:02d} / {cat_label}</div>
  <div class="meta">{date_disp}</div>
</div>
<div class="headline anim anim-slide-l delay-2">
  <h1>{html.escape(hl_title)}</h1>
  <div class="sub">{html.escape(summary[:60])}</div>
</div>
<div class="top-card anim anim-scale-in delay-3">
  <div class="tc-emoji">{emoji}</div>
  <div class="tc-info">
    <div class="tc-title">{html.escape(hl.get("cn_keyword", title[:8]))}</div>
    <div class="tc-desc">{html.escape(left_sub)}</div>
  </div>
</div>
<div class="info-card anim anim-slide-up delay-3">
  <div class="rc-title">{cat_label}</div>
  {_render_info_boxes_9x16(info_items, is_github)}
  <div class="rc-footer">{html.escape(source[:36])} · {date_disp}</div>
</div>
{caption_pill_html(caption_text)}
</div>
</body></html>"""


def _render_info_boxes_9x16(items, is_github=False):
    """Render info-box list for 9:16 right card."""
    if not items:
        return ""
    parts = []
    for active, label, text in items:
        cls = "ibox active" if active else "ibox"
        label_cls = "label gh" if is_github else "label"
        parts.append(
            f'<div class="{cls} anim anim-fade-in delay-4">'
            f'<span class="{label_cls}">{label}</span>'
            f'{html.escape(text[:70])}</div>'
        )
    return "".join(parts)



def _render_cover_html(items: list[dict], date_str: str, aspect: str) -> str:
    """Design-doc cover — light gradient, blue/teal, hard-shadow cards."""
    w, h = ASPECTS[aspect]["width"], ASPECTS[aspect]["height"]
    date_obj = date.fromisoformat(date_str)
    date_disp = date_obj.strftime("%Y.%m.%d")
    date_disp_cn = date_obj.strftime("%Y年%m月%d日")
    n = len(items)
    is_landscape = aspect == "16:9"

    # Cover uses a tighter scale to fit 6 cards within the fixed frame
    fs_cover = lambda base: int(base * w / 2400)

    # Item preview cards for the grid
    item_cards = ""
    for i, item in enumerate(items[:6]):
        emoji_t = html.escape(item.get("emoji", "📌"))
        title_t = html.escape(item.get("title", ""))
        cat = item.get("source_note", "")
        is_gh = "github" in cat.lower()
        corner = "⭐" if is_gh else emoji_t
        item_cards += (
            f'<div class="icard anim anim-scale-in delay-{3+i}">'
            f'<div class="ic-emoji">{corner}</div>'
            f'<div class="ic-title">{title_t}</div>'
            f'</div>'
        )

    caption_text = f"本周精选 {n} 条 AI 新闻 · 深度解读"

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Noto+Sans+SC:wght@500;700;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{w}px;height:{h}px;overflow:hidden;
  font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  background:linear-gradient(90deg,#f9fafb 0%,#ffffff 50%,#f9fafb 100%);
  color:#163f77;display:flex;align-items:flex-start;justify-content:center;
  -webkit-font-smoothing:antialiased}}
.stage{{width:{w}px;height:100%;padding:{fs_cover(50)}px {fs_cover(100)}px;
  padding-bottom:{fs_cover(80)}px;display:flex;flex-direction:column}}
.top-row{{display:flex;justify-content:space-between;align-items:center;margin-bottom:{fs_cover(24)}px;flex-shrink:0}}
.tag{{font-family:'Space Mono',monospace;font-size:{fs_cover(24)}px;font-weight:700;
  color:#1ca77a;letter-spacing:1px;display:flex;align-items:center;gap:{fs_cover(12)}px}}
.tag .dot{{width:{fs_cover(16)}px;height:{fs_cover(16)}px;border-radius:50%;background:#1ca77a;display:inline-block}}
.meta{{font-family:'Space Mono',monospace;font-size:{fs_cover(20)}px;color:#60748a;letter-spacing:1px}}
.hero{{margin-bottom:{fs_cover(28)}px;flex-shrink:0}}
.hero h1{{font-size:{fs_cover(84)}px;font-weight:900;color:#124783;line-height:1.05;letter-spacing:-1px}}
.hero .sub{{font-size:{fs_cover(24)}px;font-weight:600;color:#60748a;margin-top:{fs_cover(10)}px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:{fs_cover(28)}px;flex:1 1 auto;margin-bottom:{fs_cover(24)}px;min-height:0}}
.icard{{background:#fff;border:4px solid #1c4f8d;border-radius:{fs_cover(20)}px;
  padding:{fs_cover(28)}px {fs_cover(36)}px;display:flex;align-items:center;gap:{fs_cover(24)}px;
  box-shadow:{fs_cover(12)}px {fs_cover(12)}px 0 rgba(0,0,0,.07)}}
.ic-emoji{{font-size:{fs_cover(44)}px;flex-shrink:0}}
.ic-title{{font-size:{fs_cover(28)}px;font-weight:700;color:#124783;line-height:1.25;word-break:break-word}}
.caption-pill{{align-self:center;padding:{fs_cover(18)}px {fs_cover(40)}px;
  border:4px solid #17212d;border-radius:{fs_cover(24)}px;background:#fff;
  font-size:{fs_cover(30)}px;font-weight:900;color:#17212d;
  box-shadow:{fs_cover(8)}px {fs_cover(8)}px 0 rgba(0,0,0,.07);text-align:center;flex-shrink:0}}
{ANIM_CSS}
</style></head><body>
<div class="stage">
<div class="top-row anim anim-fade-in delay-1">
  <div class="tag"><span class="dot"></span>AI NEWS WEEKLY</div>
  <div class="meta">{date_disp_cn} · 精选 {n} 条</div>
</div>
<div class="hero anim anim-slide-l delay-2">
  <h1>本周 AI 速览</h1>
  <div class="sub">{date_disp} · 最值得关注的 AI 动态</div>
</div>
<div class="grid">
  {item_cards}
</div>
<div class="caption-pill anim anim-slide-up delay-5">{caption_text}</div>
</div>
</body></html>"""

def _split_headline(title: str) -> dict:
    """Extract en_keyword, cn_keyword, cn_punchline from a news title."""
    import re

    # Extract English words (len>=2, skip single letters like 'A' from 'AI')
    en_parts = re.findall(r'[A-Za-z]{2,}(?:\s+[A-Za-z]{2,})*|[A-Z][a-z]+', title)
    # Merge adjacent English fragments, filter noise
    en_keyword = ' '.join(en_parts).strip() if en_parts else ''

    # Pure Chinese: remove English, emoji, punctuation
    cn = title
    for p in sorted(en_parts, key=len, reverse=True):
        cn = cn.replace(p, '', 1)
    cn = re.sub(r'[^一-鿿　-〿＀-￯「」『』【】]', '', cn)

    # Remove exclamatory prefixes
    cn = re.sub(r'^(天|绝了|重磅|突发|快讯|刚刚|惊了|妈耶)[！!]?', '', cn)
    # Skip possessive/pronoun/demonstrative prefixes
    cn = re.sub(r'^(我的|你的|他的|她的|这个|那个|这种|那种|这些|那些)', '', cn)

    # Find quoted text — that's the keyword
    quoted = re.findall(r'[「「]([^」」]+)[」」]', cn)
    if quoted:
        cn_keyword = quoted[0][:4]
        cn_punchline = cn.replace(f'「{quoted[0]}」', '').strip()
    else:
        # Split on natural breaks: comma, 的, 了, function words
        parts = re.split(r'[，,。！的了吧吗呢啊哦哈呀]', cn, maxsplit=1)
        first_seg = parts[0]
        rest_seg = parts[1] if len(parts) > 1 else ''
        # Keyword: first 2-3 chars of first segment (try not to cut mid-word)
        if len(first_seg) >= 4:
            cn_keyword = first_seg[:3]
        elif len(first_seg) >= 2:
            cn_keyword = first_seg[:2]
        else:
            cn_keyword = first_seg
        cn_punchline = (first_seg[len(cn_keyword):] + rest_seg).lstrip('，,。！!？?')
        if not cn_punchline:
            cn_punchline = cn

    # Fallback English keyword
    if not en_keyword:
        en_lower = re.findall(r'[A-Za-z]{2,}', title)
        if en_lower:
            en_keyword = ' '.join(en_lower)
        elif 'github' in title.lower():
            en_keyword = 'Open Source'
        else:
            en_keyword = 'AI'

    # Fallback Chinese
    if not cn_keyword:
        cn_keyword = title[:3]

    return {
        'en_keyword': en_keyword,
        'cn_keyword': cn_keyword,
        'cn_punchline': cn_punchline or title,
    }


def _render_title_card_html(item: dict, date_str: str, aspect: str) -> str:
    """VerySmallWoods-style opening title card — cream paper + blue ink."""
    w, h = ASPECTS[aspect]["width"], ASPECTS[aspect]["height"]
    date_obj = date.fromisoformat(date_str)
    date_disp = date_obj.strftime("%Y.%m.%d")
    date_disp_cn = date_obj.strftime("%Y年%m月%d日")

    title = item.get("title", "")
    summary = item.get("summary", "")
    why_care = item.get("why_care", "")
    source_note = item.get("source_note", "")
    is_github = "github" in source_note.lower()

    hl = _split_headline(title)

    tag_label = "GITHUB TRENDING" if is_github else "AI NEWS DAILY"
    eyebrow_left = "GitHub 热门" if is_github else "AI 要闻"
    eyebrow_right = source_note.replace("来源：", "").replace("来源: ", "")[:24]
    quote_text = why_care[:40] if why_care else summary[:40]

    # Scale: reference 1440x810 → target w×h
    scale_x = w / 1440
    scale_y = h / 810
    fs = lambda base: int(base * min(scale_x, scale_y))

    return f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@1,500;1,600&family=Space+Mono:wght@400;700&family=Noto+Sans+SC:wght@500;700;900&display=swap');
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{w}px;height:{h}px;overflow:hidden;
  display:flex;align-items:center;justify-content:center;
  background:#000;-webkit-font-smoothing:antialiased}}
.stage{{width:{w}px;height:{h}px;background:#ECE7DA;position:relative;overflow:hidden;
  background-image:linear-gradient(rgba(43,59,214,0.08) 1px,transparent 1px),
    linear-gradient(90deg,rgba(43,59,214,0.08) 1px,transparent 1px);
  background-size:{fs(36)}px {fs(36)}px;
  font-family:'Noto Sans SC',sans-serif}}
.frame{{position:absolute;inset:{fs(36)}px;border:1.5px solid rgba(43,59,214,0.35)}}
.frame::before,.frame::after{{content:'';position:absolute;width:{fs(14)}px;height:{fs(14)}px;border:1.5px solid #2B3BD6}}
.frame::before{{top:-1.5px;left:-1.5px;border-right:none;border-bottom:none}}
.frame::after{{bottom:-1.5px;right:-1.5px;border-left:none;border-top:none}}
.top-row{{position:absolute;top:{fs(68)}px;left:{fs(100)}px;right:{fs(100)}px;
  display:flex;justify-content:space-between;align-items:center}}
.tag{{border:1.5px solid #2B3BD6;padding:{fs(6)}px {fs(16)}px;
  font-family:'Space Mono',monospace;font-size:{fs(14)}px;letter-spacing:2px;color:#2B3BD6}}
.meta{{font-family:'Space Mono',monospace;font-size:{fs(14)}px;letter-spacing:1.5px;color:#2B3BD6}}
.eyebrow{{position:absolute;top:{fs(360)}px;left:{fs(100)}px;
  font-family:'Space Mono',monospace;font-size:{fs(15)}px;letter-spacing:3px;color:#5865E0;
  display:flex;align-items:center;gap:{fs(14)}px}}
.eyebrow .dot{{color:#2B3BD6;opacity:0.6}}
.headline{{position:absolute;top:{fs(395)}px;left:{fs(96)}px;line-height:1.05}}
.headline .l1{{display:flex;align-items:baseline;gap:{fs(14)}px}}
.headline .en{{font-family:'EB Garamond',serif;font-style:italic;font-weight:600;
  font-size:{fs(104)}px;color:#2B3BD6;max-width:{w - fs(220)}px;overflow:hidden;white-space:nowrap}}
.headline .cn-serif{{font-family:'Noto Serif SC','Songti SC',serif;font-style:italic;font-weight:600;
  font-size:{fs(92)}px;color:#2B3BD6}}
.headline .l2{{font-weight:900;font-size:{fs(76)}px;letter-spacing:2px;color:#2B3BD6;margin-top:{fs(6)}px;
  max-width:{w - fs(200)}px}}
.subline{{position:absolute;top:{fs(640)}px;left:{fs(100)}px;
  font-size:{fs(24)}px;color:#2B3BD6;display:flex;align-items:baseline;gap:{fs(10)}px;
  max-width:{w - fs(200)}px}}
.subline .en{{font-family:'Space Mono',monospace;font-weight:400;font-size:{fs(22)}px}}
.subline b{{font-weight:900}}
.subline .sep{{opacity:0.5;margin:0 4px}}
.bottom-row{{position:absolute;bottom:{fs(66)}px;left:{fs(100)}px;right:{fs(100)}px;
  display:flex;justify-content:space-between;align-items:flex-end}}
.quote{{font-size:{fs(16)}px;letter-spacing:1px;color:#5865E0;max-width:{w*0.6}px}}
.format{{font-family:'Space Mono',monospace;font-size:{fs(14)}px;letter-spacing:1.5px;color:#2B3BD6;
  display:flex;align-items:center;gap:{fs(10)}px}}
{ANIM_CSS}
</style></head><body>
<div class="stage">
<div class="frame"></div>
<div class="top-row anim anim-fade-in delay-1">
  <div class="tag">{html.escape(tag_label)}</div>
  <div class="meta">{date_disp_cn} · 精选 AI 新闻</div>
</div>
<div class="eyebrow anim anim-fade-in delay-1">
  <span>{html.escape(eyebrow_left)}</span>
  <span class="dot">·</span>
  <span>{html.escape(eyebrow_right)}</span>
  <span class="dot">·</span>
  <span>AI 小白速览</span>
</div>
<div class="headline">
  <div class="l1">
    <span class="en anim anim-slide-l delay-2">{html.escape(hl['en_keyword'])}</span>
    <span class="cn-serif anim anim-fade-in delay-2">{html.escape(hl['cn_keyword'])}</span>
  </div>
  <div class="l2 anim anim-slide-up delay-3">{html.escape(hl['cn_punchline'])}</div>
</div>
<div class="subline anim anim-fade-in delay-4">
  <span class="en">{date_disp}</span>
  <span class="sep">·</span>
  <span><b>今日</b>最热 AI 新闻，{html.escape(summary[:36])}</span>
</div>
<div class="bottom-row anim anim-fade-in delay-5">
  <div class="quote">{html.escape(quote_text)}</div>
</div>
</div>
</body></html>"""


# ═══════════════════════════════════════════════════════════════════
# TTS Narration
# ═══════════════════════════════════════════════════════════════════

def _generate_narration(text: str, output_aiff: Path) -> Path:
    """Generate AIFF narration via macOS say. Returns path to .aiff."""
    subprocess.run(
        ["say", "-v", TTS_VOICE, "-o", str(output_aiff), text],
        capture_output=True, text=True, timeout=30,
    )
    return output_aiff


def _aiff_to_aac(aiff_path: Path, aac_path: Path) -> Path:
    """Convert AIFF to AAC audio."""
    subprocess.run([
        FFMPEG_PATH, "-y", "-i", str(aiff_path),
        "-c:a", "aac", "-b:a", "128k", str(aac_path),
    ], capture_output=True, text=True, timeout=30)
    return aac_path


def _narration_to_aac(text: str, output_aac: Path) -> Path:
    """Generate AAC narration via best available TTS provider with failover chain.

    Chain: Azure TTS → Zhipu TTS → macOS say (local).
    Each provider has its own circuit breaker to avoid hammering degraded services.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from news_pipeline.circuit_breaker import get_breaker

    # 1. Try Azure TTS (neural, best quality)
    cb_azure = get_breaker("tts:azure", failure_threshold=3, cooldown_seconds=60)
    if cb_azure.allow_call():
        try:
            from xhs_publish.azure_tts import get_key_region, generate_narration_aac
            key, _region = get_key_region()
            if key:
                result = generate_narration_aac(text, output_aac)
                cb_azure.on_success()
                return result
        except Exception as exc:
            print(f"  [tts] Azure failed: {exc}")
            cb_azure.on_failure()
    else:
        print("  [tts] Azure circuit OPEN, skipping to next provider")

    # 2. Try Zhipu TTS (Chinese, easy signup)
    cb_zhipu = get_breaker("tts:zhipu", failure_threshold=3, cooldown_seconds=60)
    if cb_zhipu.allow_call():
        try:
            from xhs_publish.zhipu_tts import get_key, generate_narration_aac
            key = get_key()
            if key:
                result = generate_narration_aac(text, output_aac)
                cb_zhipu.on_success()
                return result
        except Exception as exc:
            print(f"  [tts] Zhipu failed: {exc}")
            cb_zhipu.on_failure()
    else:
        print("  [tts] Zhipu circuit OPEN, skipping to next provider")

    # 3. Fallback: macOS say → aiff → aac (always available)
    print("  [tts] falling back to macOS say")
    aiff_path = output_aac.with_suffix(".aiff")
    _generate_narration(text, aiff_path)
    _aiff_to_aac(aiff_path, output_aac)
    aiff_path.unlink(missing_ok=True)
    return output_aac


def _get_audio_duration(path: Path) -> float:
    """Get duration of an audio file in seconds via ffprobe."""
    result = subprocess.run([
        FFMPEG_PATH, "-i", str(path),
    ], capture_output=True, text=True)
    for line in result.stderr.splitlines():
        if "Duration" in line:
            parts = line.strip().split()[1].rstrip(",").split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 3.0  # fallback


# ═══════════════════════════════════════════════════════════════════
# Playwright frame-by-frame recording → video segment
# ═══════════════════════════════════════════════════════════════════

def _record_page(html_path: Path, duration: float,
                 width: int, height: int, output: Path) -> Path:
    """Open animated HTML in Playwright with built-in video recording."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("playwright not installed")

    file_uri = Path(html_path).resolve().as_uri()
    tmp_video_dir = Path(tempfile.mkdtemp(prefix="pw_video_"))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": width, "height": height},
            record_video_dir=str(tmp_video_dir),
            record_video_size={"width": width, "height": height},
        )
        page = context.new_page()
        page.goto(file_uri, wait_until="networkidle", timeout=30000)

        # Wait for animations to complete
        page.wait_for_timeout(int(duration * 1000))

        context.close()
        browser.close()

    # Playwright saves as .webm in tmp_video_dir
    webm_files = list(tmp_video_dir.glob("*.webm"))
    if not webm_files:
        raise RuntimeError("Playwright did not produce a video file")

    webm_path = webm_files[0]

    # Convert webm → mp4
    result = subprocess.run([
        FFMPEG_PATH, "-y",
        "-i", str(webm_path),
        "-c:v", "libx264", "-preset", "fast", "-crf", "18",
        "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-an",
        str(output),
    ], capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"webm→mp4 conversion failed:\n{result.stderr[-300:]}")

    shutil.rmtree(tmp_video_dir, ignore_errors=True)
    return output


# ═══════════════════════════════════════════════════════════════════
# Scene concatenation
# ═══════════════════════════════════════════════════════════════════

def _concat_segments(segments: list[dict], output: Path,
                     width: int, height: int) -> Path:
    """Simple concat video segments + narration audio — perfectly synced."""
    if not segments:
        raise ValueError("need at least 1 segment")

    tmp_dir = Path(tempfile.mkdtemp(prefix="concat_"))

    try:
        # Build concat list for video segments
        video_list = tmp_dir / "video_list.txt"
        vlines = []
        for s in segments:
            vlines.append(f"file '{Path(s['path']).resolve()}'")
        video_list.write_text("\n".join(vlines))

        # Build concat list for narration audio
        narration_aacs = [
            s["narration_aac"] for s in segments
            if s.get("narration_aac") and Path(s["narration_aac"]).is_file()
        ]

        if narration_aacs:
            audio_list = tmp_dir / "audio_list.txt"
            alines = []
            for aac in narration_aacs:
                alines.append(f"file '{Path(aac).resolve()}'")
            audio_list.write_text("\n".join(alines))

            # Concat video + concat audio → mux together
            result = subprocess.run([
                FFMPEG_PATH, "-y",
                "-f", "concat", "-safe", "0", "-i", str(video_list),
                "-f", "concat", "-safe", "0", "-i", str(audio_list),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-c:a", "aac", "-b:a", "128k",
                "-shortest",
                str(output),
            ], capture_output=True, text=True, timeout=120)
            if result.returncode != 0:
                raise RuntimeError(f"concat failed:\n{result.stderr[-400:]}")
        else:
            subprocess.run([
                FFMPEG_PATH, "-y",
                "-f", "concat", "-safe", "0", "-i", str(video_list),
                "-c:v", "libx264", "-preset", "fast", "-crf", "18",
                "-pix_fmt", "yuv420p", "-r", str(FPS),
                "-an",
                str(output),
            ], capture_output=True, text=True, timeout=60)

        return output
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def _mix_bgm(video_path: Path, bgm_path: str, output: Path) -> Path:
    """Mix background music at low volume with existing video audio."""
    tmp_dir = Path(tempfile.mkdtemp(prefix="bgm_mix_"))
    try:
        # Get video duration
        result = subprocess.run([
            FFMPEG_PATH, "-i", str(video_path),
        ], capture_output=True, text=True)
        duration = 30  # fallback
        for line in result.stderr.splitlines():
            if "Duration" in line:
                d = line.strip().split()[1].rstrip(",")
                parts = d.split(":")
                duration = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                break

        # Trim BGM to video duration and mix at low volume
        subprocess.run([
            FFMPEG_PATH, "-y",
            "-i", str(video_path),
            "-stream_loop", "-1", "-i", bgm_path,
            "-filter_complex",
            f"[1:a]atrim=0:{duration:.1f},volume=0.1,afade=t=in:d=1.5,afade=t=out:st={duration-3:.1f}:d=3[bgm];"
            f"[0:a]volume=1.3[narr];"
            f"[narr][bgm]amix=inputs=2:duration=first:weights=1 0.3[outa]",
            "-map", "0:v", "-map", "[outa]",
            "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
            "-shortest",
            str(output),
        ], capture_output=True, text=True, timeout=60)
        return output
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════
# Main orchestrator
# ═══════════════════════════════════════════════════════════════════

def render_video_from_items(
    items: list[dict],
    output_dir: Path,
    date_str: str,
    *,
    aspect: str = "16:9",
    transition: str = "fade",
    bgm_path: str = "",
) -> Path:
    """items → animated HTML → record segments → concat with narration → .mp4

    Args:
        items: curated AI news items
        output_dir: where to put output
        date_str: YYYY-MM-DD
        aspect: '16:9' or '9:16'
        transition: xfade transition type
        bgm_path: optional path to background music mp3
    """
    w, h = ASPECTS[aspect]["width"], ASPECTS[aspect]["height"]
    output_dir.mkdir(parents=True, exist_ok=True)
    segments_dir = output_dir / f"{date_str}_video_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)

    try:
        # ── Generate narrations FIRST, pad to match segment, then record video ──
        segments: list[dict] = []

        def _pad_aac(aac_path: Path, target_dur: float) -> Path:
            """Pad AAC with silence to exactly target_dur seconds."""
            padded = aac_path.with_name(aac_path.stem + "_padded.aac")
            subprocess.run([
                FFMPEG_PATH, "-y",
                "-i", str(aac_path),
                "-af", f"apad=pad_dur={target_dur:.2f}",
                "-c:a", "aac", "-b:a", "128k",
                str(padded),
            ], capture_output=True, text=True, timeout=30)
            return padded

        # --- Cover ---
        date_disp = date.fromisoformat(date_str).strftime("%m月%d日")
        cover_text = f"AI小白速览，{date_disp}。精选{len(items)}条AI新闻。"
        cover_aac_raw = segments_dir / "cover_narration_raw.aac"
        _narration_to_aac(cover_text, cover_aac_raw)
        cover_narr_dur = _get_audio_duration(cover_aac_raw)
        cover_dur = cover_narr_dur + 0.3  # tight padding
        cover_aac = _pad_aac(cover_aac_raw, cover_dur)

        cover_html = segments_dir / f"cover_{aspect.replace(':','x')}.html"
        cover_html.write_text(
            _render_cover_html(items, date_str, aspect), encoding="utf-8"
        )
        cover_mp4 = segments_dir / f"cover.mp4"
        _record_page(cover_html, cover_dur, w, h, cover_mp4)
        segments.append({
            "path": cover_mp4, "duration": cover_dur,
            "narration_aac": cover_aac,
        })

        # --- Cards ---
        for i, item in enumerate(items, 1):
            # 1. Write HTML
            card_html = segments_dir / f"card_{i:02d}_{aspect.replace(':','x')}.html"
            card_html.write_text(
                _render_card_html(item, i, len(items), date_str, aspect),
                encoding="utf-8",
            )

            # 2. Generate narration, pad to match segment
            title_text = item.get("title", "")
            source_note = item.get("source_note", "")
            is_github = "github" in source_note.lower()
            if title_text:
                if is_github:
                    narrate = f"今天GitHub上最火的开源项目。{title_text}"
                else:
                    narrate = f"{title_text}"
                card_aac_raw = segments_dir / f"card_{i:02d}_narration_raw.aac"
                _narration_to_aac(narrate, card_aac_raw)
                card_narr_dur = _get_audio_duration(card_aac_raw)
                card_dur = card_narr_dur + 0.3
                card_aac = _pad_aac(card_aac_raw, card_dur)
            else:
                card_aac = None
                card_dur = 5.0

            # 3. Record video to match narration duration
            card_mp4 = segments_dir / f"card_{i:02d}.mp4"
            _record_page(card_html, card_dur, w, h, card_mp4)
            segments.append({
                "path": card_mp4, "duration": card_dur,
                "narration_aac": card_aac,
            })

        # ── Concat (simple, no xfade for perfect sync) ──
        out = output_dir / f"{date_str}_video_{aspect.replace(':','x')}.mp4"
        _concat_segments(segments, out, w, h)

        # ── Mix BGM ──
        if bgm_path and Path(bgm_path).is_file():
            out_with_bgm = output_dir / f"{date_str}_video_{aspect.replace(':','x')}_bgm.mp4"
            _mix_bgm(out, bgm_path, out_with_bgm)
            return out_with_bgm

        return out

    finally:
        # Clean segments if too large — keep for debugging during dev
        pass


# ═══════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: render_video.py <output_dir> [date_str]")
        sys.exit(1)

    output_dir = Path(sys.argv[1])
    date_str = sys.argv[2] if len(sys.argv) > 2 else output_dir.name

    # Read items from the caption file (for testing without full pipeline)
    caption_file = output_dir / f"{date_str}_combined_caption.txt"
    items = []
    if caption_file.exists():
        # Extract titles from caption as mock items
        text = caption_file.read_text(encoding="utf-8")
        titles = [l.strip()[4:] for l in text.splitlines() if l.strip().startswith(("🔥", "📌")) or (l.strip() and l[0].isdigit())]
        # Simplified: just use lines as mock
        items = [
            {"emoji": "🤖", "title": "AI News Item",
             "summary": "Summary of the news item.",
             "detail": "Detailed explanation of the news.",
             "why_care": "Why this matters.",
             "source_note": "Source: AI News",
             "key_points": ["Key point 1", "Key point 2", "Key point 3"]}
        ]
        # We need real items. For CLI testing, use hardcoded mock.
        items = [
            {
                "emoji": "🤖", "title": f"测试卡片 #{i}",
                "summary": f"这是第{i}条AI新闻的摘要内容，用简单的话解释发生了什么。",
                "detail": f"第{i}条新闻的详细解释，包含更多背景和数据。",
                "why_care": "这对普通人使用AI的方式有重要影响。",
                "source_note": "来源：TechCrunch",
                "key_points": ["关键点一", "关键点二", "关键点三"],
            } for i in range(1, 5)
        ]
    else:
        items = [
            {
                "emoji": "🤖", "title": f"测试卡片 #{i}",
                "summary": f"这是第{i}条AI新闻的摘要。",
                "detail": f"第{i}条新闻的详细解释。",
                "why_care": "这对AI行业有重要影响。",
                "source_note": "来源：TechCrunch",
                "key_points": ["关键点一", "关键点二", "关键点三"],
            } for i in range(1, 5)
        ]

    print(f"Generating video ({len(items)} items)...")
    out = render_video_from_items(items, output_dir, date_str, aspect="16:9")
    print(f"16:9 → {out}")

    out2 = render_video_from_items(items, output_dir, date_str, aspect="9:16")
    print(f"9:16 → {out2}")
