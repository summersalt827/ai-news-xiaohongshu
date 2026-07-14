#!/usr/bin/env python3
"""Render curated AI news as Xiaohongshu-format cards + cover.

Output per run:
  - 4 individual card HTMLs + PNGs (1080×1440, one per news item)
  - 1 cover HTML + PNG (1080×1440, 2×2 grid)

Design: design-doc style — light gradient bg, deep blue / teal palette,
hard-shadow cards with thick blue borders, Space Mono + Noto Sans SC.
"""

from __future__ import annotations

import html
import re
from datetime import date, datetime
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════
# Size scaling — base reference is 1440px; cards are 1080px wide
# ═══════════════════════════════════════════════════════════════════

def _fs(base: int) -> int:
    """Scale a size from 1440px reference to 1080px card width."""
    return int(base * 1080 / 1440)

# ── Card CSS (design-doc style, 1080×1440 portrait) ──────────────

CARD_CSS = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  width:1080px;
  font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  background:linear-gradient(180deg,#f9fafb 0%,#ffffff 50%,#f9fafb 100%);
  color:#163f77;-webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
}}
.stage{{
  width:1080px;padding:{_fs(80)}px {_fs(80)}px {_fs(140)}px {_fs(80)}px;
  display:flex;flex-direction:column;
}}
.top-row{{
  display:flex;justify-content:space-between;align-items:center;
  margin-bottom:{_fs(40)}px;flex-shrink:0;
}}
.tag{{
  font-family:'Space Mono',monospace;font-size:{_fs(24)}px;font-weight:700;
  color:#1ca77a;letter-spacing:1px;display:flex;align-items:center;gap:{_fs(12)}px;
}}
.tag .dot{{
  width:{_fs(18)}px;height:{_fs(18)}px;border-radius:50%;
  background:#1ca77a;display:inline-block;flex-shrink:0;
}}
.meta{{
  font-family:'Space Mono',monospace;font-size:{_fs(20)}px;
  color:#60748a;letter-spacing:1px;
}}
.headline{{margin-bottom:{_fs(50)}px;flex-shrink:0}}
.headline h1{{
  font-size:{_fs(88)}px;font-weight:900;color:#124783;
  line-height:1.08;letter-spacing:-1px;word-break:break-word;
}}
.headline .sub{{
  font-size:{_fs(28)}px;font-weight:600;color:#60748a;
  margin-top:{_fs(14)}px;word-break:break-word;
}}
.top-card{{
  border:4px solid #1c4f8d;border-radius:{_fs(24)}px;
  padding:{_fs(40)}px;margin-bottom:{_fs(36)}px;
  box-shadow:{_fs(14)}px {_fs(14)}px 0 rgba(0,0,0,.07);
  display:flex;align-items:center;gap:{_fs(30)}px;flex-shrink:0;
}}
.top-card.tc-blue{{background:#e8f0fa}}
.top-card.tc-green{{background:#e8f5e9}}
.top-card .tc-emoji{{font-size:{_fs(56)}px;flex-shrink:0}}
.top-card .tc-info{{display:flex;flex-direction:column;gap:{_fs(8)}px;min-width:0}}
.top-card .tc-title{{
  font-size:{_fs(40)}px;font-weight:900;color:#124783;word-break:break-word;
}}
.top-card .tc-desc{{
  font-family:'Space Mono',monospace;font-size:{_fs(22)}px;
  color:#138d78;font-weight:700;word-break:break-word;
}}
.info-card{{
  background:#fff;border:4px solid #1c4f8d;border-radius:{_fs(24)}px;
  padding:{_fs(36)}px {_fs(42)}px;display:flex;flex-direction:column;
  gap:{_fs(20)}px;box-shadow:{_fs(14)}px {_fs(14)}px 0 rgba(0,0,0,.07);
  flex:0 0 auto;
}}
.info-card .rc-title{{
  font-size:{_fs(46)}px;font-weight:900;color:#123e74;
  margin-bottom:{_fs(6)}px;word-break:break-word;flex-shrink:0;
}}
.ibox{{
  min-height:{_fs(66)}px;border-radius:{_fs(14)}px;border:3px solid #e2e8f0;
  display:flex;align-items:flex-start;padding:{_fs(14)}px {_fs(22)}px;
  font-size:{_fs(22)}px;font-family:'Space Mono',monospace;color:#475569;
  word-break:break-word;flex-shrink:0;
}}
.ibox.active{{border-color:#1ca77a;color:#178a70}}
.ibox .label{{
  font-weight:700;color:#1d6fb5;margin-right:{_fs(12)}px;
  font-size:{_fs(20)}px;white-space:nowrap;
  font-family:'Noto Sans SC',sans-serif;flex-shrink:0;
}}
.ibox .label.gh{{color:#1ca77a}}
.rc-footer{{
  font-family:'Space Mono',monospace;font-size:{_fs(20)}px;color:#64748b;
  margin-top:{_fs(14)}px;font-weight:600;flex-shrink:0;
}}
.caption-pill{{
  align-self:center;padding:{_fs(20)}px {_fs(44)}px;
  border:4px solid #17212d;border-radius:{_fs(28)}px;background:#fff;
  font-size:{_fs(30)}px;font-weight:900;color:#17212d;
  box-shadow:{_fs(10)}px {_fs(10)}px 0 rgba(0,0,0,.07);text-align:center;
  max-width:900px;word-break:break-word;flex-shrink:0;
  margin-top:{_fs(40)}px;
}}
"""

# ── Cover CSS (design-doc style, 1080×1440) ─────────────────────

COVER_CSS = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
body{{
  width:1080px;height:1440px;overflow:hidden;
  font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  background:linear-gradient(180deg,#f9fafb 0%,#ffffff 50%,#f9fafb 100%);
  color:#163f77;display:flex;align-items:center;justify-content:center;
  -webkit-font-smoothing:antialiased;
  -moz-osx-font-smoothing:grayscale;
}}
.stage{{
  width:1080px;height:1440px;padding:{_fs(60)}px {_fs(80)}px;
  padding-bottom:{_fs(140)}px;display:flex;flex-direction:column;
}}
.top-row{{
  display:flex;justify-content:space-between;align-items:center;
  margin-bottom:{_fs(30)}px;flex-shrink:0;
}}
.tag{{
  font-family:'Space Mono',monospace;font-size:{_fs(24)}px;font-weight:700;
  color:#1ca77a;letter-spacing:1px;display:flex;align-items:center;gap:{_fs(12)}px;
}}
.tag .dot{{
  width:{_fs(18)}px;height:{_fs(18)}px;border-radius:50%;
  background:#1ca77a;display:inline-block;flex-shrink:0;
}}
.meta{{
  font-family:'Space Mono',monospace;font-size:{_fs(20)}px;
  color:#60748a;letter-spacing:1px;
}}
.hero{{margin-bottom:{_fs(36)}px;flex-shrink:0}}
.hero h1{{
  font-size:{_fs(88)}px;font-weight:900;color:#124783;
  line-height:1.05;letter-spacing:-1px;
}}
.hero .sub{{
  font-size:{_fs(24)}px;font-weight:600;color:#60748a;
  margin-top:{_fs(12)}px;
}}
.grid{{
  display:grid;grid-template-columns:1fr 1fr;gap:{_fs(36)}px;
  flex:1 1 auto;margin-bottom:{_fs(30)}px;min-height:0;
}}
.icard{{
  background:#fff;border:4px solid #1c4f8d;border-radius:{_fs(24)}px;
  padding:{_fs(36)}px {_fs(40)}px;display:flex;align-items:center;
  gap:{_fs(24)}px;box-shadow:{_fs(14)}px {_fs(14)}px 0 rgba(0,0,0,.07);
}}
.ic-emoji{{font-size:{_fs(48)}px;flex-shrink:0}}
.ic-title{{
  font-size:{_fs(28)}px;font-weight:700;color:#124783;
  line-height:1.25;word-break:break-word;
}}
.caption-pill{{
  align-self:center;padding:{_fs(22)}px {_fs(50)}px;
  border:4px solid #17212d;border-radius:{_fs(28)}px;background:#fff;
  font-size:{_fs(32)}px;font-weight:900;color:#17212d;
  box-shadow:{_fs(10)}px {_fs(10)}px 0 rgba(0,0,0,.07);text-align:center;
  flex-shrink:0;
}}
"""


def _layer_class(idx: int) -> str:
    return ["l1", "l2", "l3", "l4", "l5"][(idx - 1) % 5]


# ═══════════════════════════════════════════════════════════════════
# Headline splitter — extracts en/cn keywords from news titles
# ═══════════════════════════════════════════════════════════════════

def _split_headline(title: str) -> dict:
    """Extract en_keyword, cn_keyword, cn_punchline from a news title."""
    # Extract English words (len>=2, skip single letters like 'A' from 'AI')
    en_parts = re.findall(r'[A-Za-z]{2,}(?:\s+[A-Za-z]{2,})*|[A-Z][a-z]+', title)
    en_keyword = ' '.join(en_parts).strip() if en_parts else ''

    # Pure Chinese: remove English, emoji, punctuation
    cn = title
    for p in sorted(en_parts, key=len, reverse=True):
        cn = cn.replace(p, '', 1)
    cn = re.sub(r'[^一-鿿　-〿＀-￯「」『』【】]', '', cn)

    # Remove exclamatory prefixes
    cn = re.sub(r'^(天|绝了|重磅|突发|快讯|刚刚|惊了|妈耶)[！!]?', '', cn)
    cn = re.sub(r'^(我的|你的|他的|她的|这个|那个|这种|那种|这些|那些)', '', cn)

    # Find quoted text — that's the keyword
    quoted = re.findall(r'[「「]([^」」]+)[」」]', cn)
    if quoted:
        cn_keyword = quoted[0][:4]
        cn_punchline = cn.replace(f'「{quoted[0]}」', '').strip()
    else:
        parts = re.split(r'[，,。！的了吧吗呢啊哦哈呀]', cn, maxsplit=1)
        first_seg = parts[0]
        rest_seg = parts[1] if len(parts) > 1 else ''
        if len(first_seg) >= 4:
            cn_keyword = first_seg[:3]
        elif len(first_seg) >= 2:
            cn_keyword = first_seg[:2]
        else:
            cn_keyword = first_seg
        cn_punchline = (first_seg[len(cn_keyword):] + rest_seg).lstrip('，,。！!？?')
        if not cn_punchline:
            cn_punchline = cn

    if not en_keyword:
        en_lower = re.findall(r'[A-Za-z]{2,}', title)
        if en_lower:
            en_keyword = ' '.join(en_lower)
        elif 'github' in title.lower():
            en_keyword = 'Open Source'
        else:
            en_keyword = 'AI'

    if not cn_keyword:
        cn_keyword = title[:3]

    return {
        'en_keyword': en_keyword,
        'cn_keyword': cn_keyword,
        'cn_punchline': cn_punchline or title,
    }


# ═══════════════════════════════════════════════════════════════════
# HTML Generators
# ═══════════════════════════════════════════════════════════════════

def _render_card_html(item: dict, idx: int, total: int, date_str: str) -> str:
    """Render a single card — design-doc style, stacked 9:16 layout."""
    date_obj = date.fromisoformat(date_str)
    date_display = date_obj.strftime("%Y年%m月%d日")
    emoji_text = html.escape(item.get("emoji", "📌"))
    title = html.escape(item.get("title", ""))
    summary = html.escape(item.get("summary", ""))
    detail = html.escape(item.get("detail", ""))
    why_care = html.escape(item.get("why_care", ""))
    source_note = html.escape(item.get("source_note", ""))
    source_type = item.get("source_type", "")

    is_github = source_type == "github"
    cat_label = "GitHub 热门" if is_github else "AI 要闻"
    tc_class = "tc-green" if is_github else "tc-blue"

    hl = _split_headline(title)
    hl_title = hl.get("cn_punchline", title)

    # Info boxes
    info_items = []
    if summary:
        info_items.append((True, "发生了什么？", summary))
    if detail and detail != summary:
        info_items.append((False, "深入了解一下", detail))
    if why_care:
        info_items.append((False, "为什么值得关注", why_care))

    # Caption pill text from first key point
    key_points = item.get("key_points", [])
    if isinstance(key_points, str):
        key_points = [p.strip() for p in key_points.split("\n") if p.strip()][:3]
    caption_text = ""
    if key_points:
        caption_text = html.escape(key_points[0])

    # Info boxes HTML
    ibox_html = ""
    for active, label, text in info_items:
        cls = "ibox active" if active else "ibox"
        lbl_cls = "label gh" if is_github else "label"
        ibox_html += (
            f'<div class="{cls}">'
            f'<span class="{lbl_cls}">{label}</span>'
            f'{html.escape(text)}</div>'
        )

    # Caption pill HTML
    pill_html = ""
    if caption_text:
        pill_html = f'<div class="caption-pill">{caption_text}</div>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | AI News</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Noto+Sans+SC:wght@500;700;900&display=swap" rel="stylesheet">
<style>
{CARD_CSS}
</style>
</head>
<body>
<div class="stage">

<div class="top-row">
  <div class="tag"><span class="dot"></span>{idx:02d} / {cat_label}</div>
  <div class="meta">{date_display} · {html.escape(source_note[:20])}</div>
</div>

<div class="headline">
  <h1>{html.escape(hl_title)}</h1>
  <div class="sub">{summary}</div>
</div>

<div class="top-card {tc_class}">
  <div class="tc-emoji">{emoji_text}</div>
  <div class="tc-info">
    <div class="tc-title">{html.escape(hl.get("cn_keyword", title[:3]))}</div>
    <div class="tc-desc">{html.escape(hl.get("en_keyword", cat_label))}</div>
  </div>
</div>

<div class="info-card">
  <div class="rc-title">{cat_label}</div>
  {ibox_html}
  <div class="rc-footer">{html.escape(source_note)} · {date_display}</div>
</div>

{pill_html}

</div>
</body>
</html>"""


def _render_cover_html(items: list[dict], date_str: str) -> str:
    """Render cover — design-doc style, 2×2 grid + caption pill."""
    date_obj = date.fromisoformat(date_str)
    date_display = date_obj.strftime("%Y年%m月%d日")
    n = len(items)

    # Item preview cards
    item_cards = ""
    for i, item in enumerate(items[:6]):
        emoji_t = html.escape(item.get("emoji", "📌"))
        title_t = html.escape(item.get("title", ""))
        cat = item.get("source_note", "")
        is_gh = "github" in cat.lower()
        corner = "⭐" if is_gh else emoji_t
        item_cards += (
            f'<div class="icard">'
            f'<div class="ic-emoji">{corner}</div>'
            f'<div class="ic-title">{title_t}</div>'
            f'</div>'
        )

    caption_text = f"精选 {n} 条 AI 新闻 · 深度解读"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 速览 | {date_display}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Mono:wght@400;700&family=Noto+Sans+SC:wght@500;700;900&display=swap" rel="stylesheet">
<style>
{COVER_CSS}
</style>
</head>
<body>
<div class="stage">

<div class="top-row">
  <div class="tag"><span class="dot"></span>AI NEWS WEEKLY</div>
  <div class="meta">{date_display} · 精选 {n} 条</div>
</div>

<div class="hero">
  <h1>本周 AI 速览</h1>
  <div class="sub">{date_display} · 最值得关注的 AI 动态</div>
</div>

<div class="grid">
  {item_cards}
</div>

<div class="caption-pill">{caption_text}</div>

</div>
</body>
</html>"""


# ── Public API ─────────────────────────────────────────────────

def save_cards_and_cover(
    items: list[dict], output_dir: Path, date_str: str,
    cover_items: list[dict] | None = None,
) -> tuple[list[Path], Path, Path]:
    """Save individual card HTMLs + cover HTML + caption to disk.

    cover_items: items to show on cover grid (defaults to all).
    Returns: (card_html_paths, cover_html_path, caption_path)
    """
    if cover_items is None:
        cover_items = items

    output_dir.mkdir(parents=True, exist_ok=True)

    card_paths: list[Path] = []
    for idx, item in enumerate(items, 1):
        slug = f"{idx:02d}"
        html = _render_card_html(item, idx, len(items), date_str)
        p = output_dir / f"{date_str}_card_{slug}.html"
        p.write_text(html, encoding="utf-8")
        card_paths.append(p)

    cover_html = _render_cover_html(cover_items, date_str)
    cover_path = output_dir / f"{date_str}_cover.html"
    cover_path.write_text(cover_html, encoding="utf-8")

    caption_path = output_dir / f"{date_str}_combined_caption.txt"
    _write_caption(items, caption_path, date_str)

    return card_paths, cover_path, caption_path


def _write_caption(items: list[dict], path: Path, date_str: str):
    date_display = date.fromisoformat(date_str).strftime("%Y年%m月%d日")
    n = len(items)
    lines = [
        f"🤖 AI 周报 | {date_display}", "",
        f"本周精选 {n} 条最重要的 AI 新闻，零基础也能跟上～", "",
        "─" * 30, "",
    ]
    for i, item in enumerate(items, 1):
        emoji = item.get("emoji", "📌")
        title = item.get("title", "")
        summary = item.get("summary", "")
        source_type = item.get("source_type", "")
        cat = item.get("category", "")
        if source_type == "github":
            lines.append(f"🔥 GitHub 本周最火项目")
            lines.append(f"{emoji} {title}")
            lines.append(f"   {summary[:100]}")
            lines.append(f"   ⭐ 7天 star 增速最快，开发者都在关注")
        else:
            cat_tag = f"【{cat}】" if cat else ""
            lines.append(f"{emoji} {i:02d} · {cat_tag}{title}")
            lines.append(f"   {summary[:100]}")
        lines.append("")
    lines += [
        "─" * 30, "",
        "每周精选，帮你轻松跟上 AI 圈 ✨",
        "右上角关注，下周继续～", "",
        "#AI新闻 #AI小白 #人工智能 #科技资讯 #每周AI #自我提升 #知识分享 #效率工具",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def screenshot_htmls(html_paths: list[Path], output_dir: Path) -> list[Path]:
    """Screenshot each HTML as PNG using Playwright headless Chrome.

    Returns list of PNG paths.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  [screenshot] playwright not installed, skip PNG")
        return []

    output_dir.mkdir(parents=True, exist_ok=True)
    png_paths: list[Path] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            for html_path in html_paths:
                png_path = output_dir / html_path.with_suffix(".png").name
                file_uri = Path(html_path).resolve().as_uri()

                page = browser.new_page(
                    viewport={"width": 1080, "height": 2400},
                    device_scale_factor=2,
                )
                page.goto(file_uri, wait_until="networkidle", timeout=30000)
                page.screenshot(path=str(png_path), full_page=True)  # full page, no truncation
                page.close()
                png_paths.append(png_path)
            browser.close()
    except Exception as exc:
        print(f"  [screenshot] failed: {exc}")

    return png_paths
