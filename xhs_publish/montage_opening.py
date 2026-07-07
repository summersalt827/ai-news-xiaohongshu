"""Generate montage opening clip for H1 review video."""
import subprocess, tempfile, os, shutil
from pathlib import Path

PROJECT = Path(__file__).parent.parent
CARD_DIR = PROJECT / "xiaohongshu" / "2026-H1-review"
FFMPEG = shutil.which("ffmpeg") or str(
    Path.home() / "Library/Application Support/bilibili/ffmpeg/ffmpeg"
)
W, H = 1080, 1920

# Flash frames: (text, accent_color, bg_color, duration_sec)
FLASHES = [
    ("$100亿", "#4da6ff", "#0d1a2d", 0.35),
    ("$974亿", "#b366ff", "#1a0d2e", 0.35),
    ("87.6%", "#4dcc88", "#0d1f14", 0.35),
    ("1.6T", "#e6994d", "#1f1408", 0.35),
    ("EO 14409", "#e64d4d", "#1f0d0d", 0.35),
    ("$600亿", "#cc5555", "#0f0a0a", 0.35),
]

TITLE_FRAME_DUR = 1.5

def make_flash_html(text: str, accent: str, bg: str) -> str:
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@900&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{W}px; height:{H}px; background:{bg};
    display:flex; align-items:center; justify-content:center;
    font-family:'Inter','PingFang SC',sans-serif; overflow:hidden;
}}
.num {{ font-size:160px; font-weight:900; color:{accent}; letter-spacing:-2px; }}
</style></head><body><div class="num">{text}</div></body></html>"""

def make_title_html() -> str:
    return f"""<!DOCTYPE html><html lang="zh"><head><meta charset="UTF-8"><style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{
    width:{W}px; height:{H}px;
    background: linear-gradient(135deg, #0d1a2d 0%, #1a0d2e 30%, #1f0d0d 60%, #0f0a0a 100%);
    display:flex; flex-direction:column; align-items:center; justify-content:center;
    font-family:'Inter','PingFang SC',sans-serif; overflow:hidden;
    gap: 24px;
}}
.eyebrow {{ font-size:28px; color:#787573; letter-spacing:8px; font-weight:400; }}
.title {{
    font-size:88px; font-weight:900; line-height:1.15; text-align:center;
    background: linear-gradient(135deg,#4da6ff,#b366ff,#e64d4d,#e6994d);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
}}
.sub {{ font-size:26px; color:#787573; font-weight:400; }}
</style></head><body>
<div class="eyebrow">2026 MID-YEAR REVIEW</div>
<div class="title">AI 上半年<br>全景复盘</div>
<div class="sub">从技术爆炸到全面管制</div>
</body></html>"""

def screenshot(html_path: Path, png_path: Path):
    subprocess.run([
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "--headless", f"--screenshot={png_path}",
        "--window-size=1080,1440", "--force-device-scale-factor=2",
        html_path.as_uri()
    ], check=True, capture_output=True)

def generate_montage(output: Path):
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        clip_files = []

        # Generate flash frames
        for i, (text, accent, bg, dur) in enumerate(FLASHES):
            html_path = tmp / f"flash_{i:02d}.html"
            png_path = tmp / f"flash_{i:02d}.png"
            mp4_path = tmp / f"flash_{i:02d}.mp4"
            html_path.write_text(make_flash_html(text, accent, bg))
            screenshot(html_path, png_path)
            # Create video clip from image
            subprocess.run([
                FFMPEG, "-y", "-loop", "1", "-i", str(png_path),
                "-t", str(dur),
                "-vf", f"scale={W}:{H},format=yuv420p",
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
                "-pix_fmt", "yuv420p", str(mp4_path)
            ], check=True, capture_output=True)
            clip_files.append(mp4_path)
            print(f"  Flash {i+1}: {text} ({dur}s)")

        # Title frame
        title_html = tmp / "title.html"
        title_png = tmp / "title.png"
        title_mp4 = tmp / "title.mp4"
        title_html.write_text(make_title_html())
        screenshot(title_html, title_png)
        subprocess.run([
            FFMPEG, "-y", "-loop", "1", "-i", str(title_png),
            "-t", str(TITLE_FRAME_DUR),
            "-vf", f"scale={W}:{H},format=yuv420p",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-pix_fmt", "yuv420p", str(title_mp4)
        ], check=True, capture_output=True)
        clip_files.append(title_mp4)
        print(f"  Title frame ({TITLE_FRAME_DUR}s)")

        # Concat all clips
        concat_file = tmp / "concat.txt"
        concat_file.write_text("\n".join(f"file '{f}'" for f in clip_files))
        subprocess.run([
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-pix_fmt", "yuv420p", str(output)
        ], check=True, capture_output=True)

        size_mb = os.path.getsize(output) / 1024 / 1024
        print(f"\n  ✓ Montage: {output.name} ({size_mb:.1f} MB)")

def prepend_montage(montage: Path, main_video: Path, output: Path):
    """Prepend montage to main video — simple concat."""
    mtg_dur = sum(d for _, _, _, d in FLASHES) + TITLE_FRAME_DUR

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # Step 1: Add silent audio to montage + fade-out video at the end
        mtg_with_audio = tmp / "montage_silent.mp4"
        subprocess.run([
            FFMPEG, "-y",
            "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=mono",
            "-i", str(montage),
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18",
            "-c:a", "aac", "-b:a", "64k",
            "-shortest",
            str(mtg_with_audio)
        ], check=True, capture_output=True)

        # Step 2: Simple concat with concat demuxer
        concat_file = tmp / "concat.txt"
        concat_file.write_text(
            f"file '{mtg_with_audio}'\n"
            f"file '{main_video}'\n"
        )
        subprocess.run([
            FFMPEG, "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file),
            "-c:v", "libx264", "-preset", "fast", "-crf", "22",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p", str(output)
        ], check=True, capture_output=True)

    size_mb = os.path.getsize(output) / 1024 / 1024
    print(f"  ✓ Final: {output.name} ({size_mb:.1f} MB)")

def main():
    print("=== Montage Opening ===\n")
    montage = CARD_DIR / "montage_opening.mp4"
    generate_montage(montage)

    main_video = CARD_DIR / "2026-H1-review_xhs_9x16.mp4"
    final = CARD_DIR / "2026-H1-review_xhs_9x16_final.mp4"
    print(f"\n=== Prepending to main video ===\n")
    prepend_montage(montage, main_video, final)
    print(f"\nDone! → {final}")

if __name__ == "__main__":
    main()
