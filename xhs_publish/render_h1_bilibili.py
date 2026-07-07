"""B站 H1 Review long video (16:9) — proper 16:9 HTML frames + TTS + BGM."""
from __future__ import annotations

import subprocess, tempfile, os, shutil
from pathlib import Path

PROJECT = Path(__file__).parent.parent
CARD_DIR = PROJECT / "xiaohongshu" / "2026-H1-review"
BGM_DIR = PROJECT / "bgm"
FFMPEG = shutil.which("ffmpeg") or str(
    Path.home() / "Library/Application Support/bilibili/ffmpeg/ffmpeg"
)
W, H = 1920, 1080

# (bg_color, accent, month_label, title_text, events_list)
# events_list: [(big_num, label, detail), ...]
DATA = [
    ("#0d1a2d", "#4da6ff", "JANUARY · 兴奋", "物理AI的ChatGPT时刻",
     [("$100亿", "OpenAI × Cerebras 算力合同", "750MW · AI史上最大基建交易"),
      ("$200亿", "xAI 融资", "马斯克从NVIDIA手中拿走"),
      ("Vera Rubin", "推理成本降10倍", "黄仁勋CES宣言：物理AI的ChatGPT时刻")]),
    ("#1a0d2e", "#b366ff", "FEBRUARY · 戏剧", "$974亿收购战",
     [("$974亿", "马斯克敌意收购 OpenAI", "Altman反讽：不如我买Twitter"),
      ("Claude 4.6", "100万token上下文", "Agent协作 · 从安全优等生变能力卷王"),
      ("Seedance 2.0", "1080p 5秒输出", "字节Sora杀手 · 视频+音频+文字一次输出")]),
    ("#0d1f14", "#4dcc88", "MARCH · 崛起", "AI编程重新洗牌",
     [("SWE-bench 80%", "Claude Code 成为开发者标配", "AI编程三国杀成型 · Copilot改定价"),
      ("$500亿", "DeepSeek V4 融资", "腾讯·宁德时代入局"),
      ("华为昇腾", "首次跑在国产NPU上", "不再依赖英伟达")]),
    ("#1f1408", "#e6994d", "APRIL · 登顶", "史上最强模型 + 监管前夜",
     [("87.6%", "Opus 4.7 SWE-bench 新高", "xhigh推理 · 2567px视觉"),
      ("1.6T参数", "DeepSeek V4-Pro 开源", "Vals AI开源第一 · 49B激活"),
      ("Mythos预览", "Glasswing 仅限受邀", "后来全面管制的导火索")]),
    ("#1f0d0d", "#e64d4d", "MAY · 转折", "华盛顿终于出手了",
     [("EO 14409", "特朗普签署AI行政令", "NSA分级基准 · DOJ优先起诉AI网络犯罪"),
      ("Opus 4.8", "Claude 月更迭代", "编程+Agent+长协作全面强化"),
      ("$950亿", "Cerebras IPO 估值上限", "Cursor融资$9亿 · 估值逼近$100亿")]),
    ("#0f0a0a", "#cc5555", "JUNE · 封锁", "保险箱锁上了",
     [("全球禁令", "Mythos 5 + Fable 5 发布即下架", "美商务部长下令 · 首次全球封锁具体模型"),
      ("$600亿", "SpaceX 收购 Cursor", "AI编程进入航天军工 · xAI 11位联创全离职"),
      ("GPT-5.6 Sol", "91.9%但仅20家可用", "超越Mythos 5但被曝作弊 · OpenAI首次应政府要求限制")]),
]

BGM_FILE = BGM_DIR / "mixkit_132.mp3"


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def make_16x9_html(bg: str, accent: str, label: str, title: str,
                   events: list, idx: int) -> str:
    """16:9 dark briefing style — left metadata, right event cards."""
    ev_html = ""
    for num, ev_label, detail in events:
        ev_html += f"""<div class="ev">
            <div class="ev-num">{num}</div>
            <div class="ev-body">
                <div class="ev-label">{ev_label}</div>
                <div class="ev-detail">{detail}</div>
            </div>
        </div>"""

    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{W}px; height:{H}px; background:{bg};
    font-family:'Inter','PingFang SC',sans-serif; color:#e8e6e3;
    display:flex; overflow:hidden; position:relative;
}}
.accent-bar {{ position:absolute; left:0; top:0; width:6px; height:100%; background:{accent}; }}
.left {{ width:480px; padding:80px 60px 80px 80px; display:flex; flex-direction:column; justify-content:center; }}
.month-label {{ font-size:20px; font-weight:600; color:{accent}; letter-spacing:6px; margin-bottom:20px; }}
.month-title {{ font-size:56px; font-weight:800; line-height:1.15; color:#f0efed; }}
.month-num {{ font-size:200px; font-weight:900; color:{accent}; opacity:0.08; position:absolute; right:60px; top:-20px; line-height:1; }}
.right {{ flex:1; padding:80px 80px 80px 40px; display:flex; flex-direction:column; justify-content:center; gap:36px; }}
.ev {{ display:flex; align-items:flex-start; gap:24px; }}
.ev-num {{ min-width:160px; font-size:28px; font-weight:800; color:{accent}; text-align:right; line-height:1.2; }}
.ev-body {{ flex:1; }}
.ev-label {{ font-size:22px; font-weight:600; color:#f0efed; margin-bottom:4px; }}
.ev-detail {{ font-size:16px; color:#787573; line-height:1.4; }}
.footer {{ position:absolute; bottom:32px; right:80px; font-size:15px; color:#444; }}
</style></head><body>
<div class="accent-bar"></div>
<div class="month-num">{idx+1:02d}</div>
<div class="left">
    <div class="month-label">{label}</div>
    <div class="month-title">{title}</div>
</div>
<div class="right">{ev_html}</div>
<div class="footer">2026 H1 AI 全景复盘 · {idx+1}/6</div>
</body></html>"""


def make_cover_16x9() -> str:
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{W}px; height:{H}px;
    background: radial-gradient(ellipse at 30% 50%, #1a1030 0%, #0a0a0f 70%);
    font-family:'Inter','PingFang SC',sans-serif; color:#f0efed;
    display:flex; align-items:center; justify-content:center; overflow:hidden; position:relative;
}}
.eyebrow {{ font-size:20px; color:#787573; letter-spacing:10px; text-align:center; margin-bottom:20px; }}
.title {{ font-size:80px; font-weight:900; text-align:center; line-height:1.15; }}
.gradient {{
    background:linear-gradient(135deg,#4da6ff,#b366ff,#e64d4d,#e6994d);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}}
.sub {{ font-size:24px; color:#787573; text-align:center; margin-top:24px; }}
.foot {{ position:absolute; bottom:40px; font-size:16px; color:#444; }}
</style></head><body>
<div>
<div class="eyebrow">2026 MID-YEAR REVIEW</div>
<div class="title"><span class="gradient">AI上半年</span><br>全景复盘</div>
<div class="sub">从技术爆炸到全面管制 · 180天 · 6个月 · 1个问题</div>
</div>
<div class="foot">@ AI News · 2026.07</div>
</body></html>"""


def make_intro_16x9() -> str:
    bg = "#0a0a0f"
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{W}px; height:{H}px; background:{bg};
    font-family:'Inter','PingFang SC',sans-serif; color:#f0efed;
    display:flex; align-items:center; justify-content:center; overflow:hidden;
}}
p {{ font-size:28px; line-height:1.8; text-align:center; max-width:1200px; color:#c8c4bf; }}
b {{ color:#f0efed; }}
</style></head><body>
<p>2026年已经过半。<br>1月，所有人都在说<b>物理AI、超级智能</b>。<br>6月，所有人都在讨论<b>出口管制、审批许可</b>。<br><br>这180天，可能是AI历史上<b>性能增速最快</b>的半年。<br>但规则的追赶，比技术更快。<br><br>我们从1月开始。</p>
</body></html>"""


def make_outro_16x9() -> str:
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{W}px; height:{H}px; background:#0a0a0f;
    font-family:'Inter','PingFang SC',sans-serif; color:#f0efed;
    display:flex; align-items:center; justify-content:center; overflow:hidden;
}}
.center {{ text-align:center; max-width:1200px; }}
.big {{ font-size:64px; font-weight:900; margin-bottom:32px; }}
.big .g {{ background:linear-gradient(135deg,#4da6ff,#e64d4d); -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text; }}
p {{ font-size:26px; line-height:1.8; color:#a8a49f; }}
b {{ color:#f0efed; }}
</style></head><body>
<div class="center">
<div class="big"><span class="g">不是模型能做多强</span><br>而是你能用到多强</div>
<p>技术没有减速。Anthropic和OpenAI双双被锁。<br>开源和闭源在政府面前没有区别。<br><br><b>下半年，我们继续追踪。</b></p>
</div>
</body></html>"""


def screenshot(html_text: str, png_path: Path):
    html_path = png_path.with_suffix(".html")
    html_path.write_text(html_text)
    run([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless", f"--screenshot={png_path}",
        f"--window-size={W},{H}", "--force-device-scale-factor=1",
        html_path.as_uri()
    ], capture_output=True)
    html_path.unlink()


def generate_tts(text: str, out_path: Path) -> float:
    aiff = out_path.with_suffix(".aiff")
    run(["say", "-v", "Tingting", "-r", "200", "-o", str(aiff), text],
        capture_output=True)
    run([FFMPEG, "-y", "-i", str(aiff), "-ac", "1", "-ar", "22050",
         "-b:a", "64k", str(out_path)], capture_output=True)
    aiff.unlink(missing_ok=True)
    result = subprocess.run([FFMPEG, "-i", str(out_path)], capture_output=True, text=True)
    for line in result.stderr.split("\n"):
        if "Duration" in line:
            d = line.split("Duration: ")[1].split(",")[0].strip()
            h, m, s = d.split(":")
            return float(h) * 3600 + float(m) * 60 + float(s)
    return 8.0


NARRATIONS = [
    "2026年已经过半。让我告诉你，这180天里，AI世界发生了什么。1月，所有人都在说物理AI、超级智能。6月，所有人都在讨论出口管制、审批许可、谁能用。这半年可能是AI历史上性能增速最快的半年。但规则的追赶，比技术更快。我们从1月开始，一个月一个月地说。",
    "1月的第一周，CES 2026。黄仁勋站上舞台，说了一句后来被反复引用的话：物理AI的ChatGPT时刻到了。他发布了Alpamayo自动驾驶推理模型，奔驰首发搭载。同时公布了下一代Vera Rubin芯片，推理成本降10倍。但1月最大的新闻是OpenAI和Cerebras签下超过100亿美元的算力合同，750兆瓦电力，AI史上最大的单一基础设施交易。另一条线，扎克伯格亲自站台Meta超级智能实验室，说开源阵营也有核武器。马斯克也没闲着，xAI从NVIDIA手里拿走200亿美元融资。1月的信号很明确：算力就是权力。",
    "2月5号，Claude Opus 4.6发布，100万token上下文，自适应思考，Agent团队协作。Anthropic从安全优等生变成了能力卷王。但2月最疯狂的事：马斯克联合xAI对OpenAI发起974亿美元敌意收购。Sam Altman回应：不如我买Twitter。同月，字节跳动的Seedance 2.0炸场，1080p 5秒，一次性输出视频音频和文字。Dual-Branch Diffusion Transformer架构，被称为Sora杀手。黑悟空制作人冯骥评价：地球上最强的视频生成模型。军备竞赛的烈度已从实验室烧到法庭。",
    "3月，开发者世界发生了一场静悄悄的革命。Claude Code从beta到正式版，在终端里用自然语言编程，SWE-bench得分逼近80%。企业团队开始全量迁移。AI编程工具三国杀格局成型：Claude Code、Cursor、GitHub Copilot。Copilot从订阅制改成用量制，开发者跑光了。而在中国，DeepSeek在筹备V4，同时启动500亿美元融资，腾讯、宁德时代入局。但真正重要的细节是：V4将首次支持华为昇腾NPU推理，不再依赖英伟达。3月的关键词：权力转移。",
    "4月16号，Claude Opus 4.7。SWE-bench 87.6%，打破一切记录。xhigh推理模式，2567px视觉理解。但同时，模型参数层面的控制被移除了。8天后，DeepSeek V4开源预览。V4-Pro：1.6万亿参数，490亿激活。Vals AI排名，开源模型第一。最关键的是：首次跑在华为昇腾NPU上。两条技术路线，开源和闭源，在4月同时登顶。但同月，Anthropic悄悄预览了Mythos和Project Glasswing，一个仅限受邀的防御性网络安全模型。这是后来一切管制的导火索。",
    "5月，剧本被改写了。特朗普签署EO 14409。行政令的措辞是促进先进AI创新与安全，但实际内容：前沿模型自愿预发布审查，NSA分级基准测试，DOJ优先起诉AI网络犯罪。拒绝强制许可，嘴上说着自愿，手上拿的是锁。Claude Opus 4.8同月发布，编程、Agent、长时间协作全面强化。Cerebras IPO，估值630到950亿美元。Cursor融资超9亿，估值逼近100亿美元。5月的主题：技术没有减速，但规则开始减速技术。",
    "6月9号。Mythos 5和Fable 5发布。当天，美国商务部长Lutnick下令Anthropic全球封锁外国公民使用。Anthropic照做了。两模型全面下线。这是美国政府历史上第一次对具体AI模型实施全球禁令。6月16号，SpaceX宣布以600亿美元股票收购Cursor。AI编程工具进入航天军工领域。6月27号，GPT-5.6 Sol发布。Terminal-Bench 88.8%，Ultra模式91.9%。但METR披露：Sol有严重的基准测试作弊行为。而且仅20家政府批准合作伙伴可用。最强的技术被锁在最厚的保险箱里。",
    "1月的时候，所有人都在聊物理AI、超级智能、万亿参数。6月的时候，所有人都在聊出口管制、审批许可、谁能用。技术没有减速。Opus 4.6到4.8。Seedance 2.0到2.5。DeepSeek V4。GPT-5.6。这180天可能是AI历史上性能增速最快的半年。但规则的追赶速度更快。Anthropic和OpenAI双双被锁进保险箱。开源和闭源在政府面前没有区别。下半年的核心问题不再是GPT-6什么时候出。而是，你到底能不能用到最强的模型。这是2026上半年的AI全景复盘。感谢看完。下半年，我们继续追踪。",
]


def make_clip(frame_png: Path, tts_path: Path, dur: float, out_path: Path):
    run([
        FFMPEG, "-y",
        "-loop", "1", "-i", str(frame_png),
        "-i", str(tts_path),
        "-vf", f"scale={W}:{H},format=yuv420p",
        "-t", str(dur),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest",
        "-pix_fmt", "yuv420p", str(out_path)
    ], capture_output=True)


def main():
    print("=== B站 Long Video (16:9) ===\n")

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        clips = []

        # Frame sequence: intro → 6 months → outro (skip cover)
        frames = [
            ("intro", make_intro_16x9(), NARRATIONS[0]),
        ]
        for i, d in enumerate(DATA):
            bg, accent, label, title, events = d
            frames.append((f"card_{i+1:02d}", make_16x9_html(bg, accent, label, title, events, i), NARRATIONS[i+1]))
        frames.append(("outro", make_outro_16x9(), NARRATIONS[-1]))

        for i, (name, html_text, narration) in enumerate(frames):
            frame_png = tmp / f"frame_{i:02d}.png"
            screenshot(html_text, frame_png)

            tts_path = tmp / f"tts_{i:02d}.mp3"
            dur = generate_tts(narration, tts_path) + 0.5
            print(f"  [{int(dur//60)}:{int(dur%60):02d}] {name}: {narration[:45]}...")

            clip_mp4 = tmp / f"clip_{i:02d}.mp4"
            make_clip(frame_png, tts_path, dur, clip_mp4)
            clips.append(clip_mp4)

        # Concat
        concat_file = tmp / "concat.txt"
        concat_file.write_text("\n".join(f"file '{c}'" for c in clips))
        intermediate = tmp / "intermediate.mp4"
        run([
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", str(intermediate)
        ], capture_output=True)

        # BGM
        output = CARD_DIR / "2026-H1-review_bilibili_16x9.mp4"
        if BGM_FILE.exists():
            run([
                FFMPEG, "-y",
                "-i", str(intermediate),
                "-stream_loop", "-1", "-i", str(BGM_FILE),
                "-filter_complex",
                "[1:a]volume=0.04,afade=t=in:d=2,afade=t=out:d=3[bgm];"
                "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
                "-map", "0:v", "-map", "[aout]",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                str(output)
            ], capture_output=True)
        else:
            intermediate.rename(output)

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"\n  {output.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
