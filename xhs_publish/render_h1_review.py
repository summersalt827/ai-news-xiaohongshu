"""Render 2026 H1 AI Review cards — 7 monthly cards + cover."""
import json, subprocess, tempfile, os
from pathlib import Path

OUT_DIR = Path(__file__).parent.parent / "xiaohongshu" / "2026-H1-review"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_URL = Path(__file__).parent.parent

# --- Card Data ---
CARDS = [
    {
        "month": "01", "title": "物理 AI 的\nChatGPT 时刻",
        "subtitle": "JANUARY · 兴奋",
        "accent": "#4da6ff", "bg": "#0d1a2d",
        "events": [
            {"num": "$100亿", "label": "OpenAI × Cerebras 算力合同", "detail": "750MW · AI史上最大基建交易"},
            {"num": "$200亿", "label": "xAI 融资", "detail": "马斯克从NVIDIA等手中拿走"},
            {"num": "10×", "label": "Vera Rubin 推理成本降10倍", "detail": "黄仁勋CES宣言: 物理AI的ChatGPT时刻"},
            {"num": "首发", "label": "Meta 超级智能实验室", "detail": "扎克伯格: 开源阵营也有核武器"},
        ]
    },
    {
        "month": "02", "title": "算法战争 +\n$974亿收购战",
        "subtitle": "FEBRUARY · 戏剧",
        "accent": "#b366ff", "bg": "#1a0d2e",
        "events": [
            {"num": "$974亿", "label": "马斯克敌意收购 OpenAI", "detail": "Altman反讽: 不如我买Twitter"},
            {"num": "100万", "label": "Claude Opus 4.6 上下文", "detail": "Agent协作 · 从安全优等生变能力卷王"},
            {"num": "1080p", "label": "Seedance 2.0 炸场", "detail": "字节Sora杀手 · 视频+音频+文字一次输出"},
        ]
    },
    {
        "month": "03", "title": "AI编程\n重新洗牌",
        "subtitle": "MARCH · 崛起",
        "accent": "#4dcc88", "bg": "#0d1f14",
        "events": [
            {"num": "80%", "label": "Claude Code SWE-bench 逼近", "detail": "终端编程横扫GitHub · 三国杀成型"},
            {"num": "$500亿", "label": "DeepSeek V4 融资", "detail": "腾讯·宁德时代入局"},
            {"num": "昇腾", "label": "首次跑在华为NPU上", "detail": "不再依赖英伟达"},
        ]
    },
    {
        "month": "04", "title": "史上最强模型\n+ 监管前夜",
        "subtitle": "APRIL · 登顶",
        "accent": "#e6994d", "bg": "#1f1408",
        "events": [
            {"num": "87.6%", "label": "Opus 4.7 SWE-bench 新高", "detail": "xhigh推理 · 2567px视觉 · 参数控制被移除"},
            {"num": "1.6T", "label": "DeepSeek V4-Pro 参数", "detail": "49B激活 · Vals AI开源第一"},
            {"num": "导火索", "label": "Mythos + Glasswing 预览", "detail": "防御性网络安全 · 后来全面管制的起点"},
        ]
    },
    {
        "month": "05", "title": "华盛顿\n终于出手了",
        "subtitle": "MAY · 转折",
        "accent": "#e64d4d", "bg": "#1f0d0d",
        "events": [
            {"num": "EO 14409", "label": "特朗普签署AI行政令", "detail": "NSA分级基准 · DOJ优先起诉AI网络犯罪"},
            {"num": "月更", "label": "Claude Opus 4.8 发布", "detail": "编程+Agent+长协作全面强化"},
            {"num": "$950亿", "label": "Cerebras IPO 估值上限", "detail": "Cursor融资$9亿 · 估值逼近$100亿"},
        ]
    },
    {
        "month": "06", "title": "保险箱\n锁上了",
        "subtitle": "JUNE · 封锁",
        "accent": "#cc5555", "bg": "#0f0a0a",
        "events": [
            {"num": "全球禁令", "label": "Mythos 5 + Fable 5 发布即下架", "detail": "美商务部长下令 · 首次对具体模型全球封锁"},
            {"num": "$600亿", "label": "SpaceX 收购 Cursor", "detail": "AI编程进入航天军工 · xAI 11位联创全离职"},
            {"num": "91.9%", "label": "GPT-5.6 Sol 终局", "detail": "超越Mythos 5但被曝作弊 · 仅20家可用"},
        ]
    },
    {
        "month": "∞", "title": "上半年最大变量\n不是技术\n是谁能用技术",
        "subtitle": "CONCLUSION · 冷静",
        "accent": "#cccccc", "bg": "#1a1a1a",
        "events": [
            {"num": "180天", "label": "AI史上性能增速最快的半年", "detail": "Opus 4.6→4.8 · Seedance 2.0→2.5 · DeepSeek V4 · GPT-5.6"},
            {"num": "2家", "label": "双双被锁进保险箱", "detail": "Anthropic · OpenAI — 开源闭源在政府面前没有区别"},
            {"num": "1个问题", "label": "下半年的核心", "detail": "不再是模型能做多强 · 而是你能用到多强"},
        ]
    },
]

def make_card_html(card, idx):
    accent = card["accent"]
    bg = card["bg"]
    events_html = ""
    for ev in card["events"]:
        events_html += f"""<div class="event">
            <div class="event-num">{ev['num']}</div>
            <div class="event-body">
                <div class="event-label">{ev['label']}</div>
                <div class="event-detail">{ev['detail']}</div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width: 1080px; height: 1440px;
    background: {bg};
    font-family: 'Inter', 'PingFang SC', -apple-system, sans-serif;
    color: #e8e6e3;
    display: flex; flex-direction: column; justify-content: space-between;
    overflow: hidden; position: relative;
}}
/* Top accent line */
.accent-line {{ position: absolute; top: 0; left: 0; width: 100%; height: 6px; background: {accent}; }}
/* Month number - large watermark */
.month-num {{
    position: absolute; top: 40px; right: 60px;
    font-size: 240px; font-weight: 900;
    color: {accent}; opacity: 0.12;
    line-height: 1; font-family: 'Inter', sans-serif;
}}
/* Title area */
.title-area {{ padding: 80px 80px 0; position: relative; z-index: 1; }}
.month-subtitle {{ font-size: 22px; font-weight: 500; color: {accent}; letter-spacing: 6px; text-transform: uppercase; margin-bottom: 24px; }}
.month-title {{ font-size: 72px; font-weight: 800; line-height: 1.15; white-space: pre-line; color: #f0efed; }}
.title-accent {{ color: {accent}; }}
/* Events area */
.events-area {{ padding: 60px 80px 100px; display: flex; flex-direction: column; gap: 44px; position: relative; z-index: 1; }}
.event {{ display: flex; align-items: flex-start; gap: 32px; }}
.event-num {{
    min-width: 180px; font-size: 36px; font-weight: 800; color: {accent};
    text-align: right; line-height: 1.1; letter-spacing: -0.5px;
}}
.event-body {{ flex: 1; }}
.event-label {{ font-size: 26px; font-weight: 600; color: #f0efed; margin-bottom: 6px; line-height: 1.3; }}
.event-detail {{ font-size: 20px; font-weight: 400; color: #989590; line-height: 1.4; }}
/* Footer */
.footer {{ padding: 0 80px 60px; font-size: 18px; color: #555; display: flex; justify-content: space-between; }}
.footer-brand {{ font-weight: 600; color: {accent}; }}
.footer-page {{ }}
</style></head>
<body>
<div class="accent-line"></div>
<div class="month-num">{card['month']}</div>
<div class="title-area">
    <div class="month-subtitle">{card['subtitle']}</div>
    <div class="month-title">{card['title']}</div>
</div>
<div class="events-area">{events_html}</div>
<div class="footer">
    <span class="footer-brand">2026 H1 AI 全景复盘</span>
    <span class="footer-page">{idx + 1} / 7</span>
</div>
</body></html>"""

def make_cover_html():
    return """<!DOCTYPE html>
<html lang="zh">
<head><meta charset="UTF-8">
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
* { margin:0; padding:0; box-sizing:border-box; }
body {
    width: 1080px; height: 1440px;
    background: #080c14;
    font-family: 'Inter', 'PingFang SC', -apple-system, sans-serif;
    color: #f0efed;
    display: flex; flex-direction: column; justify-content: center; align-items: center;
    text-align: center; position: relative; overflow: hidden;
}
/* Gradient ambient */
.ambient {
    position: absolute; width: 800px; height: 800px;
    border-radius: 50%; filter: blur(200px); opacity: 0.15;
}
.ambient-1 { background: #4da6ff; top: -200px; right: -100px; }
.ambient-2 { background: #cc5555; bottom: -200px; left: -100px; }
.content { position: relative; z-index: 1; padding: 0 80px; }
.eyebrow { font-size: 24px; font-weight: 600; letter-spacing: 10px; color: #989590; margin-bottom: 32px; text-transform: uppercase; }
.main-title { font-size: 88px; font-weight: 900; line-height: 1.1; margin-bottom: 24px; }
.main-title .gradient-text {
    background: linear-gradient(135deg, #4da6ff, #b366ff, #e64d4d, #e6994d);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text;
}
.subtitle { font-size: 30px; font-weight: 400; color: #787573; line-height: 1.5; margin-bottom: 60px; }
.divider { width: 200px; height: 1px; background: rgba(255,255,255,0.15); margin: 0 auto 60px; }
.stats { display: flex; gap: 60px; justify-content: center; }
.stat-num { font-size: 56px; font-weight: 800; color: #e8e6e3; }
.stat-label { font-size: 18px; color: #787573; margin-top: 8px; }
.footer-cover { position: absolute; bottom: 60px; font-size: 18px; color: #444; }
</style></head>
<body>
<div class="ambient ambient-1"></div>
<div class="ambient ambient-2"></div>
<div class="content">
    <div class="eyebrow">2026 MID-YEAR REVIEW</div>
    <div class="main-title">
        <span class="gradient-text">AI 上半年</span><br>
        <span>全景复盘</span>
    </div>
    <div class="subtitle">从技术爆炸到全面管制<br>180天 · 6个月 · 1个问题</div>
    <div class="divider"></div>
    <div class="stats">
        <div class="stat"><div class="stat-num">12</div><div class="stat-label">重磅发布</div></div>
        <div class="stat"><div class="stat-num">6</div><div class="stat-label">家巨头</div></div>
        <div class="stat"><div class="stat-num">1</div><div class="stat-label">条主线</div></div>
    </div>
</div>
<div class="footer-cover">@ AI News · 2026.07</div>
</body></html>"""

def screenshot(html_path, png_path):
    uri = Path(html_path).as_uri()
    subprocess.run([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless",
        f"--screenshot={png_path}",
        "--window-size=1080,1440",
        "--force-device-scale-factor=2",
        uri
    ], check=True, capture_output=True)
    size = os.path.getsize(png_path)
    print(f"  ✓ {png_path.name} ({size:,} bytes)")

def main():
    print("Generating H1 Review cards...\n")

    # Cover
    cover_html = OUT_DIR / "cover.html"
    cover_html.write_text(make_cover_html())
    print(f"  → {cover_html.name}")

    # Cards
    for i, card in enumerate(CARDS):
        card_html = OUT_DIR / f"card_{i+1:02d}.html"
        card_html.write_text(make_card_html(card, i))
        print(f"  → {card_html.name}: {card['title'].split(chr(10))[0]}")

    print(f"\n{len(CARDS) + 1} HTML files written to {OUT_DIR}")

    # Screenshot all
    print("\nScreenshooting...\n")
    for html_file in sorted(OUT_DIR.glob("card_*.html")):
        png_file = html_file.with_suffix(".png")
        screenshot(html_file, png_file)
    screenshot(OUT_DIR / "cover.html", OUT_DIR / "cover.png")

    # Clean up HTML files — keep only PNGs
    for f in OUT_DIR.glob("*.html"):
        f.unlink()

    print(f"\nDone! {len(list(OUT_DIR.glob('*.png')))} PNG files in {OUT_DIR}")

if __name__ == "__main__":
    main()
