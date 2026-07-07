"""H1 Review video compositing — XHS short (9:16) + B站 long (16:9).

Uses Zhipu GLM-TTS for natural Chinese narration, FFmpeg for compositing.
"""
from __future__ import annotations

import subprocess, tempfile, os, shutil, json
from pathlib import Path

# Add parent to path for zhipu_tts import
import sys
sys.path.insert(0, str(Path(__file__).parent))
from zhipu_tts import generate_narration

PROJECT = Path(__file__).parent.parent
CARD_DIR = PROJECT / "xiaohongshu" / "2026-H1-review"
BGM_DIR = PROJECT / "bgm"
FFMPEG = shutil.which("ffmpeg") or str(
    Path.home() / "Library/Application Support/bilibili/ffmpeg/ffmpeg"
)

# ——— XHS Short Video Segments ———
# Each: (image_file, narration_text, duration_buffer_sec)
XHS_SEGMENTS = [
    ("cover.png",
     "2026上半年AI到底发生了什么？6个月，12次重磅发布，1条主线。"),
    ("card_01.png",
     "1月，黄仁勋说物理AI的ChatGPT时刻到了。OpenAI和Cerebras，100亿美元，750兆瓦，AI史上最大的单笔交易。xAI融了200亿，Meta开源核武器亮相。"),
    ("card_02.png",
     "2月，马斯克974亿美元要买OpenAI。Altman说：不如我买Twitter。Claude Opus 4.6发布，100万token上下文。Seedance 2.0炸场，1080p，5秒，一镜到底。"),
    ("card_03.png",
     "3月，Claude Code拿下SWE-bench 80%。GitHub Copilot改定价，开发者跑光了。DeepSeek V4融资500亿，首次跑在华为昇腾上。"),
    ("card_04.png",
     "4月，Opus 4.7炸榜，SWE-bench 87.6%，史上最高。DeepSeek V4开源，1.6万亿参数。但Mythos的预览已经埋下了管制的导火索。"),
    ("card_05.png",
     "5月，特朗普签了EO 14409。NSA分级审查，DOJ优先起诉AI犯罪。Cerebras IPO估值冲到950亿。法律进场了。"),
    ("card_06.png",
     "6月，保险箱锁上了。Mythos 5发布当天就被全球下架。SpaceX 600亿美元买下Cursor。GPT-5.6跑出91.9%，但只有20家能用。"),
    ("card_07.png",
     "180天。2家被锁。1个问题。下半年的AI，不是能做多强，而是，你能用到多强。"),
]

BGM_FILE = BGM_DIR / "mixkit_132.mp3"
ZHIPU_VOICE = "chuichui"
ZHIPU_SPEED = 2.0
FPS = 30


def run(cmd, **kw):
    subprocess.run(cmd, check=True, **kw)


def generate_tts(text: str, out_path: Path) -> float:
    """Generate TTS audio using Zhipu GLM-TTS (chuichui voice, 2x speed)."""
    wav_path = out_path.with_suffix(".wav")
    generate_narration(text, wav_path, voice=ZHIPU_VOICE)
    # Convert to mp3 for smaller size
    run([FFMPEG, "-y", "-i", str(wav_path), "-ac", "1", "-ar", "22050",
         "-b:a", "64k", str(out_path)], capture_output=True)
    wav_path.unlink(missing_ok=True)
    # Get duration
    result = subprocess.run(
        [FFMPEG, "-i", str(out_path)], capture_output=True, text=True)
    for line in result.stderr.split("\n"):
        if "Duration" in line:
            dur_str = line.split("Duration: ")[1].split(",")[0].strip()
            parts = dur_str.split(":")
            return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    return 5.0


def compose_video(aspect: str, segments: list, output: Path, bgm_vol: float = 0.06):
    """Compose video from image + TTS segments with BGM."""
    w, h = (1080, 1920) if aspect == "9:16" else (1920, 1080)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)
        concat_file = tmp / "concat.txt"
        filter_file = tmp / "filter.txt"
        audio_inputs = []
        video_inputs = []
        concat_lines = []

        # Generate TTS + video clips for each segment
        for i, (img_name, text) in enumerate(segments):
            img_path = CARD_DIR / img_name
            if not img_path.exists():
                print(f"  ⚠ Missing: {img_name}, skipping")
                continue

            # TTS
            tts_path = tmp / f"tts_{i:02d}.mp3"
            dur = generate_tts(text, tts_path)
            dur += 0.5  # small buffer after each segment
            print(f"  Segment {i+1}: {dur:.1f}s — {text[:40]}...")

            # Create video clip: image + zoom effect + TTS audio
            clip_path = tmp / f"clip_{i:02d}.mp4"
            # Ken Burns slow zoom: start at scale 1.0, end at 1.08
            zoom_filter = (
                f"scale={w*2}:{h*2},"
                f"zoompan=z='min(zoom+0.0008,1.08)':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={FPS}"
            )
            run([
                FFMPEG, "-y",
                "-loop", "1", "-i", str(img_path),
                "-i", str(tts_path),
                "-filter_complex",
                f"[0:v]{zoom_filter},format=yuv420p[v];[v][1:a]concat=n=1:v=1:a=1",
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                "-c:a", "aac", "-b:a", "128k",
                "-pix_fmt", "yuv420p",
                str(clip_path)
            ], capture_output=True)

            video_inputs.extend(["-i", str(clip_path)])
            concat_lines.append(f"[{i}:v][{i}:a]")

        if not concat_lines:
            print("No segments generated!")
            return

        # Write concat filter
        concat_inputs = " ".join(concat_lines)
        filter_content = f"{concat_inputs}concat=n={len(concat_lines)}:v=1:a=1[outv][outa]"
        filter_file.write_text(filter_content)

        # Build ffmpeg command
        cmd = [FFMPEG, "-y"] + video_inputs

        # Add BGM if available
        if BGM_FILE.exists():
            cmd += ["-stream_loop", "-1", "-i", str(BGM_FILE)]
            filter_content = (
                f"{concat_inputs}concat=n={len(concat_lines)}:v=1:a=1[mainv][maina];"
                f"[{len(concat_lines)}:a]volume={bgm_vol},afade=t=in:d=1.5,afade=t=out:st=999:d=3[bgm];"
                f"[maina][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout];"
                f"[mainv]null[vout]"
            )
            filter_file.write_text(filter_content)
            map_opts = ["-map", "[vout]", "-map", "[aout]"]
        else:
            map_opts = ["-map", "[outv]", "-map", "[outa]"]

        cmd += [
            "-filter_complex_script", str(filter_file),
        ] + map_opts + [
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            str(output)
        ]

        print(f"\n  Composing {aspect} video → {output.name}...")
        run(cmd, capture_output=True)
        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"  ✓ {output.name} ({size_mb:.1f} MB)")


def main():
    print("=== H1 Review Video Compositing ===\n")

    # ——— XHS Short Video (9:16) ———
    print("[XHS] Short video (9:16, ~105s)...")
    out_xhs = CARD_DIR / "2026-H1-review_xhs_9x16.mp4"
    compose_video("9:16", XHS_SEGMENTS, out_xhs, bgm_vol=0.06)
    print(f"\n  → {out_xhs}\n")

    print("Done!")


if __name__ == "__main__":
    main()
