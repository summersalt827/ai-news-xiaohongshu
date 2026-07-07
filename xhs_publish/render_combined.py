#!/usr/bin/env python3
"""Render curated AI news as Xiaohongshu-format cards + cover.

Output per run:
  - 4 individual card HTMLs + PNGs (1080×1440, one per news item)
  - 1 cover HTML + PNG (1080×1440, 2×2 grid)

Design follows 小红书发布.md style guide:
  1080×1440 @2x (= 2160×2880 PNG), warm white (#faf9f5),
  orange accent (#d97757), Inter + PingFang SC.
"""

from __future__ import annotations

import html
from datetime import date, datetime
from pathlib import Path

# ── Card CSS (single card, 1080px) ─────────────────────────────

CARD_CSS = """
:root {
  --bg: #F8F5EF; --text: #1a1918; --text-secondary: #555;
  --muted: #777; --line: #E5DDD1; --accent: #D97757;
  --green: #629987; --blue: #6a9bcc; --lavender: #7b7cb8;
  --inset-bg: rgba(255,255,255,.45);
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text);
  width: 1080px; height: 1440px; overflow: hidden;
  line-height: 1.6; -webkit-font-smoothing: antialiased;
}
body::before {
  content:""; position:absolute; inset:0;
  background: radial-gradient(circle, rgba(0,0,0,.012) 1px, transparent 1px);
  background-size: 6px 6px; opacity: .25; pointer-events: none;
}
/* Decorative circles — colors vary per card via inline style */
.circle-top {
  position:absolute; width:600px; height:600px; right:-180px; top:-280px;
  border-radius:50%; opacity:.22; pointer-events:none;
}
.circle-bottom {
  position:absolute; width:320px; height:320px; left:-140px; bottom:-150px;
  border-radius:50%;
  background: radial-gradient(circle, rgba(234,167,134,.1), rgba(234,167,134,.04));
  opacity:.35; pointer-events:none;
}
.circle-right {
  position:absolute; width:500px; height:500px; right:-120px; bottom:-200px;
  border-radius:50%;
  background: radial-gradient(circle, rgba(255,255,255,.5), rgba(255,255,255,.1));
  opacity:.3; pointer-events:none;
}
.dots {
  position:absolute; right:200px; top:260px; width:220px; height:130px;
  background-image: radial-gradient(#999 1px, transparent 1px);
  background-size: 18px 18px; opacity:.2; pointer-events:none;
}
.top-accent-bar { position:relative; z-index:2; height:4px; background: var(--accent); }

/* ── Hero ── */
.card-hero {
  position:relative; z-index:2; text-align:center; padding: 40px 64px 28px;
}
.card-hero .hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 13px; font-weight: 600; letter-spacing: 1.5px;
  color: var(--accent); border: 1.5px solid var(--accent);
  border-radius: 100vw; padding: 5px 16px; margin-bottom: 16px;
  background: none;
}
.card-hero .hero-badge.github {
  color: #32312f; border-color: #555;
}
.hero-badge-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); }
.hero-badge.github .hero-badge-dot { background: #f0c040; }
.card-hero h1 {
  font-family: "Times New Roman", Georgia, "Noto Serif SC", serif;
  font-size: 42px; font-weight: 400; color: var(--text);
  letter-spacing: -0.5px; line-height: 1.2;
}
.accent-rule { width: 44px; height: 3px; background: var(--accent); margin: 16px auto 0; }

/* ── Content ── */
.card-content { position:relative; z-index:2; padding: 0 68px 12px; }
.info-card {
  background: none; border: none;
  border-left: 1.5px solid var(--line); border-radius: 0;
  padding: 6px 0 6px 18px; margin-bottom: 12px;
}
.info-card h3 {
  font-size: 16px; font-weight: 600; color: var(--text);
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
}
.info-card p { font-size: 15px; color: var(--text-secondary); line-height: 1.75; }

/* ── Key points ── */
.key-points { position:relative; z-index:2; padding: 0 68px 18px; }
.key-points h3 {
  font-size: 15px; font-weight: 600; color: var(--text-secondary);
  margin-bottom: 10px; display: flex; align-items: center; gap: 6px;
}
.key-point { font-size: 15px; color: var(--text-secondary); line-height: 1.6; margin-bottom: 6px; padding-left: 4px; }
.key-point .num { font-weight: 700; margin-right: 6px; font-size: 16px; }
.key-point .num.c1 { color: var(--accent); }
.key-point .num.c2 { color: var(--green); }
.key-point .num.c3 { color: var(--blue); }

/* ── Source note ── */
.source-note {
  position:relative; z-index:2; text-align:center;
  font-size: 13px; color: var(--muted); padding: 0 56px 10px;
}

/* ── Insight Box ── */
.insight-box-wrap { position:relative; z-index:2; padding: 0 56px 28px; }
.insight-box {
  background: #1a1918; border-radius: 18px;
  padding: 30px 38px; text-align: center;
}
.insight-label {
  font-size: 12px; font-weight: 700; letter-spacing: 1.5px;
  color: #a1a09e; margin-bottom: 10px; text-transform: uppercase;
}
.insight-text {
  font-size: 20px; font-weight: 700; color: #faf9f5; line-height: 1.55;
}
.insight-text .highlight { color: var(--accent); }

/* ── Footer ── */
.card-footer {
  position:relative; z-index:2; text-align:center; padding: 16px 56px 32px;
  border-top: 1px solid var(--line);
  font-size: 13px; color: var(--muted); letter-spacing: 2px;
}
.card-footer .idx { font-weight: 600; color: var(--text); }
"""

# ── Cover CSS (2×N grid) ──────────────────────────────────────

COVER_CSS = """
:root {
  --bg: #F8F5EF; --text: #1a1918; --text-secondary: #555;
  --muted: #777; --line: #E5DDD1; --accent: #D97757;
  --green: #629987; --blue: #6a9bcc; --lavender: #7b7cb8; --rose: #c46686;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
  background: var(--bg); color: var(--text);
  width: 1080px; height: 1440px; overflow: hidden;
  -webkit-font-smoothing: antialiased;
}
body::before {
  content:""; position:absolute; inset:0;
  background: radial-gradient(circle, rgba(0,0,0,.012) 1px, transparent 1px);
  background-size: 6px 6px; opacity: .25; pointer-events: none;
}
.circle-top {
  position:absolute; width:700px; height:700px; right:-200px; top:-340px;
  border-radius:50%;
  background:radial-gradient(circle at center,#F5C6AE,#EEB394 55%,#EAA786);
  opacity:.18; pointer-events:none;
}
.circle-bottom {
  position:absolute; width:360px; height:360px; left:-150px; bottom:-160px;
  border-radius:50%;
  background:radial-gradient(circle,rgba(234,167,134,.12),rgba(234,167,134,.04));
  opacity:.4; pointer-events:none;
}
.dots {
  position:absolute; right:180px; top:280px; width:220px; height:130px;
  background-image:radial-gradient(#999 1px,transparent 1px);
  background-size:18px 18px; opacity:.2; pointer-events:none;
}
.top-accent-bar { position:relative; z-index:2; height:4px; background: var(--accent); }

.cover-hero {
  position:relative; z-index:2; text-align:center; padding: 56px 56px 36px;
}
.cover-hero .hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 600; letter-spacing: 2px;
  color: var(--accent); border: 1.5px solid var(--accent);
  border-radius: 100vw; padding: 8px 22px; margin-bottom: 22px;
  background: none;
}
.hero-badge-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); }
.cover-hero h1 {
  font-family: "Times New Roman", Georgia, "Noto Serif SC", serif;
  font-size: 68px; font-weight: 400; color: var(--text);
  letter-spacing: -2px; line-height: 1;
}
.accent-line { width: 52px; height: 3px; background: var(--accent); margin: 22px auto 0; }
.cover-hero .subtitle { margin-top: 16px; font-size: 20px; color: var(--muted); font-weight: 400; }

.card-grid-2x2 {
  position:relative; z-index:2;
  display: grid; grid-template-columns: 1fr 1fr; gap: 16px;
  padding: 0 56px 32px;
}
.cover-card {
  background: none; border: 1px solid var(--line);
  border-radius: 0; padding: 32px 28px; position: relative; overflow: hidden;
}
.cover-card .cc-emoji { font-size: 28px; margin-bottom: 12px; }
.cover-card .cc-title { font-size: 19px; font-weight: 600; color: var(--text); margin-bottom: 8px; line-height: 1.35; }
.cover-card .cc-desc { font-size: 15px; color: var(--text-secondary); line-height: 1.65; }
.cover-card .cc-badge {
  position: absolute; top: 14px; right: 16px;
  width: 32px; height: 32px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; color: #faf9f5;
}
.cc-badge.l1 { background: var(--accent); }
.cc-badge.l2 { background: var(--green); }
.cc-badge.l3 { background: var(--blue); }
.cc-badge.l4 { background: var(--lavender); }
.cc-badge.l5 { background: var(--rose); }

.insight-section { position:relative; z-index:2; padding: 0 56px 40px; }
.insight-box {
  background: #1a1918; border-radius: 22px;
  padding: 44px 52px; text-align: center;
}
.insight-label {
  font-size: 13px; font-weight: 700; letter-spacing: 1.5px;
  color: #a1a09e; margin-bottom: 14px; text-transform: uppercase;
}
.insight-text { font-size: 26px; font-weight: 700; color: #faf9f5; line-height: 1.55; }
.insight-text .highlight { color: var(--accent); }

.cover-footer {
  position:relative; z-index:2; text-align:center; padding: 24px 56px 44px;
  border-top: 1px solid var(--line);
  font-size: 15px; color: var(--muted); letter-spacing: 1.5px;
}
.cover-footer .tags { margin-top: 10px; font-size: 15px; color: var(--accent); }
"""


def _layer_class(idx: int) -> str:
    return ["l1", "l2", "l3", "l4", "l5"][(idx - 1) % 5]


def _render_card_html(item: dict, idx: int, total: int, date_str: str) -> str:
    """Render a single card HTML for one news item — rich multi-section format."""
    date_display = date.fromisoformat(date_str).strftime("%Y年%m月%d日")
    emoji_text = html.escape(item.get("emoji", "📌"))
    title = html.escape(item.get("title", ""))
    summary = html.escape(item.get("summary", ""))
    detail = html.escape(item.get("detail", ""))
    why_care = html.escape(item.get("why_care", ""))
    source_note = html.escape(item.get("source_note", ""))
    source_type = item.get("source_type", "")

    is_github = source_type == "github"

    # Key points (3 bullet points)
    key_points = item.get("key_points", [])
    if isinstance(key_points, str):
        key_points = [p.strip() for p in key_points.split("\n") if p.strip()][:3]
    if not key_points:
        key_points = [summary[:30], why_care[:30], f"关注{title[:20]}"]

    kp_html = ""
    if key_points:
        colors = ["c1", "c2", "c3"]
        pts = []
        for i, pt in enumerate(key_points[:3]):
            c = colors[i]
            pts.append(f'    <div class="key-point"><span class="num {c}">{"①②③"[i]}</span>{html.escape(pt)}</div>')
        kp_html = f"""  <div class="key-points">
    <h3>🧠 小白记住这三点</h3>
{chr(10).join(pts)}
  </div>"""

    # Source badge color
    src_cls = "github" if is_github else "news"

    # Per-card circle gradient color
    circle_gradients = [
        "radial-gradient(circle at center,#F5C6AE,#EEB394 55%,#EAA786)",
        "radial-gradient(circle at center,#C6D9CE,#B2C9BA 55%,#A5BBA6)",
        "radial-gradient(circle at center,#C6D0E5,#B2BCE0 55%,#A5A8D4)",
        "radial-gradient(circle at center,#D6C6E0,#C8B5D4 55%,#BDA5C8)",
        "radial-gradient(circle at center,#E5C6CE,#E0B2BC 55%,#D4A5AF)",
    ]
    circle_bg = circle_gradients[(idx - 1) % len(circle_gradients)]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} | AI 小白速览</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Serif+SC:wght@400;600&display=swap" rel="stylesheet">
<style>
{CARD_CSS}
</style>
</head>
<body>

<div class="circle-top" style="background:{circle_bg}"></div>
<div class="circle-bottom"></div>
<div class="circle-right"></div>
<div class="dots"></div>

<div class="top-accent-bar"></div>

<header class="card-hero">
  <div class="hero-badge {src_cls}">
    <span class="hero-badge-dot"></span>
    {'⭐ GitHub 最新趋势' if is_github else 'AI 小白速览'} · {date_display}
  </div>
  <h1>{emoji_text} {title}</h1>
  <div class="accent-rule"></div>
</header>

<div class="card-content">
  <div class="info-card">
    <h3>📰 发生了什么？</h3>
    <p>{summary}</p>
  </div>
  <div class="info-card">
    <h3>🔍 深入了解一下</h3>
    <p>{detail if detail else summary}</p>
  </div>
  <div class="info-card">
    <h3>💡 为什么值得关注</h3>
    <p>{why_care}</p>
  </div>
</div>

{kp_html}

<div class="insight-box-wrap">
  <div class="insight-box">
    <div class="insight-label">Key Insight</div>
    <p class="insight-text">这条新闻的关键在于<span class="highlight">「{title[:30]}」</span>{'正在改变我们使用 AI 的方式。' if not is_github else '代表了开源社区最新的创新方向。'}</p>
  </div>
</div>

<div class="source-note">📍 {source_note}</div>

<footer class="card-footer">
  <span class="idx">{idx:02d}</span> / {total:02d}
</footer>

</body>
</html>"""


def _render_cover_html(items: list[dict], date_str: str) -> str:
    """Render 2×N cover grid HTML."""
    date_display = date.fromisoformat(date_str).strftime("%Y年%m月%d日")

    cards = []
    for idx, item in enumerate(items, 1):
        layer = _layer_class(idx)
        emoji_text = html.escape(item.get("emoji", "📌"))
        title = html.escape(item.get("title", ""))
        summary = html.escape(item.get("summary", ""))

        cards.append(f"""    <div class="cover-card">
      <div class="cc-badge {layer}">{idx:02d}</div>
      <div class="cc-emoji">{emoji_text}</div>
      <div class="cc-title">{title}</div>
      <div class="cc-desc">{summary[:120]}</div>
    </div>""")

    first_title = html.escape(items[0].get("title", "AI")) if items else "AI"

    date_eng = date.fromisoformat(date_str).strftime("%b %d, %Y").upper()

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 速览 | {date_display}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Serif+SC:wght@400;600&display=swap" rel="stylesheet">
<style>
{COVER_CSS}
</style>
</head>
<body>

<div class="circle-top"></div>
<div class="circle-bottom"></div>
<div class="dots"></div>

<div class="top-accent-bar"></div>

<header class="cover-hero">
  <div class="hero-badge">
    <span class="hero-badge-dot"></span>
    AI 速览
  </div>
  <h1>今日 AI 速览</h1>
  <div class="accent-line"></div>
  <p class="subtitle">{date_display} · 精选 {len(items)} 条，零基础也能看懂</p>
</header>

<main class="card-grid-2x2">
{"".join(cards)}
</main>

<section class="insight-section">
  <div class="insight-box">
    <div class="insight-label">Key Insight</div>
    <p class="insight-text">
      今天最值得关注的是<span class="highlight">「{first_title}」</span>，这可能会改变普通人日常使用 AI 的方式。
    </p>
  </div>
</section>

<footer class="cover-footer">
  <div class="tags">#AI新闻 #人工智能 #科技资讯</div>
  <div style="margin-top:8px">AI 速览 · {date_display}</div>
</footer>

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
    lines = [
        f"🤖 AI 速览 | {date_display}", "",
        "今天挑了 4 条最好懂的 AI 新闻，零基础也能跟上～", "",
        "─" * 30, "",
    ]
    for i, item in enumerate(items, 1):
        emoji = item.get("emoji", "📌")
        title = item.get("title", "")
        summary = item.get("summary", "")
        source_type = item.get("source_type", "")
        if source_type == "github":
            lines.append(f"🔥 GitHub 今日最火项目")
            lines.append(f"{emoji} {title}")
            lines.append(f"   {summary[:100]}")
            lines.append(f"   ⭐ 24小时 star 增速最快，开发者都在关注")
        else:
            lines.append(f"{emoji} {i:02d} · {title}")
            lines.append(f"   {summary[:100]}")
        lines.append("")
    lines += [
        "─" * 30, "",
        "每天 4 条，帮你轻松跟上 AI 圈 ✨",
        "右上角关注，明天继续～", "",
        "#AI新闻 #AI小白 #人工智能 #科技资讯 #每日打卡 #自我提升 #知识分享 #效率工具",
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
                file_uri = Path(html_path).as_uri()

                page = browser.new_page(
                    viewport={"width": 1080, "height": 1440},
                    device_scale_factor=2,
                )
                page.goto(file_uri, wait_until="networkidle", timeout=30000)
                page.screenshot(path=str(png_path))  # viewport only = 2160×2880
                page.close()
                png_paths.append(png_path)
            browser.close()
    except Exception as exc:
        print(f"  [screenshot] failed: {exc}")

    return png_paths
