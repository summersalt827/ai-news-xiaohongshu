#!/usr/bin/env python3
"""YouTube → 小红书图文卡片：优先 YouTube 字幕 → Claude 蒸馏 → 卡片生成

Workflow (prefers auto-captions, ~5s):
  1. yt-dlp 下载 YouTube 自动字幕（英文优先）
  2. Claude 蒸馏为 4 张卡片 JSON
  3. 渲染 HTML 卡片 + Playwright 截图

Fallback: if captions unavailable, download audio + Whisper transcribe.

Usage:
    python3 youtube_to_xhs.py <youtube_url>
    python3 youtube_to_xhs.py <youtube_url> --auto-publish
    python3 youtube_to_xhs.py <youtube_url> --force-whisper
    python3 youtube_to_xhs.py <youtube_url> --skip-download --audio /path/to/audio.mp3

Output goes to xiaohongshu/<YYYY-MM-DD>, same format as AI News daily cards.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

# Ensure both news_pipeline and xhs_publish are importable
_SCRIPT_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SCRIPT_DIR.parent
sys.path.insert(0, str(_SCRIPT_DIR))            # for claude_utils
sys.path.insert(0, str(_PROJECT_ROOT / "xhs_publish"))  # for render_combined

from claude_utils import call_claude, parse_json_lenient
from render_combined import save_cards_and_cover, screenshot_htmls

# ── System prompt for Claude distillation ──────────────────────────

SYSTEM_PROMPT = """你是一个专业的内容编辑，负责把 YouTube 视频逐字稿精炼成小红书风格的 AI 科普卡片。

## 任务

从逐字稿中提炼 4 条核心知识点或观点，每条按以下 JSON 输出：

```json
[
  {
    "emoji": "🤖",
    "title": "简短有力的标题（15字以内）",
    "summary": "用大白话解释这条内容在说什么。像跟朋友聊天一样自然，避免术语。（2-3句）",
    "detail": "更深入的解释，包含原视频中的具体数据、案例或技术细节。让读者觉得「学到了」。（3-4句）",
    "why_care": "这个内容对普通人有什么影响？和日常生活或工作有什么关系？（2-3句）",
    "key_points": ["记住点1", "记住点2", "记住点3"],
    "source_note": "YouTube · <视频主题关键词>"
  }
]
```

## 规则

1. 必须提炼 4 条，覆盖视频中最有价值的内容，不要重复
2. 语言面向 AI 小白，用生活类比和具体例子说明复杂概念
3. emoji 要贴合内容，一条一个不同的 emoji
4. key_points 每条 20 字以内，朗朗上口
5. key_points 输出为 JSON 数组，不要用 \n 分隔的字符串"""

# ── Download ────────────────────────────────────────────────────────

YT_DLP_BASE = [
    "yt-dlp",
    "--js-runtimes", "deno",
    "--remote-components", "ejs:github",
    "--cookies-from-browser", "firefox",
]


def _get_video_info(url: str) -> dict[str, str]:
    """Fetch video title and channel without downloading."""
    cmd = [*YT_DLP_BASE, "--print", "%(title)s||%(uploader)s||%(description)s", "--no-download", url]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return {"title": "", "uploader": "", "description": ""}
    parts = result.stdout.strip().split("||", 2)
    return {
        "title": parts[0] if len(parts) > 0 else "",
        "uploader": parts[1] if len(parts) > 1 else "",
        "description": parts[2][:500] if len(parts) > 2 else "",
    }


def download_audio(url: str, output_dir: Path) -> tuple[Path, dict[str, str]]:
    """Download best audio from YouTube. Returns (audio_path, video_info)."""
    info = _get_video_info(url)
    title = info.get("title", "video")

    safe_title = "".join(c for c in title if c not in r'<>:"/\|?*')[:80]
    output_template = str(output_dir / f"{safe_title}.%(ext)s")

    cmd = [
        *YT_DLP_BASE,
        "-f", "bestaudio[ext=m4a]/bestaudio",
        "-o", output_template,
        "--no-playlist",
        url,
    ]
    subprocess.run(cmd, check=True, capture_output=True)

    audio_files = sorted(output_dir.glob("*.mp3"), key=os.path.getmtime, reverse=True)
    if not audio_files:
        audio_files = sorted(output_dir.glob("*.m4a"), key=os.path.getmtime, reverse=True)
    if not audio_files:
        raise FileNotFoundError("yt-dlp 下载完成但未找到音频文件")
    return audio_files[0], info


# ── YouTube captions (fast path) ────────────────────────────────────

def _clean_vtt(text: str) -> str:
    """Strip VTT timestamps, metadata, and tags; return plain text."""
    # Remove header
    text = re.sub(r'^WEBVTT.*?\n\n', '', text, count=1, flags=re.S)
    # Remove cue IDs like "1\n" before timestamps
    text = re.sub(r'^\d+\n', '', text, flags=re.M)
    # Remove timestamps lines
    text = re.sub(r'^\d{2}:\d{2}:\d{2}\.\d{3} --> .*$', '', text, flags=re.M)
    # Remove <c> tags and other VTT tags
    text = re.sub(r'<[^>]+>', '', text)
    # Remove alignment/style metadata lines
    text = re.sub(r'^NOTE .*$', '', text, flags=re.M)
    text = re.sub(r'^Kind:.*$', '', text, flags=re.M)
    text = re.sub(r'^Language:.*$', '', text, flags=re.M)
    # Collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    lines = [l.strip() for l in text.split('\n')]
    lines = [l for l in lines if l]
    return '\n'.join(lines)


def download_youtube_captions(url: str, output_dir: Path) -> str | None:
    """Try to download YouTube auto-captions. Returns transcript text or None."""
    output_template = str(output_dir / "%(title)s.%(ext)s")

    cmd = [
        *YT_DLP_BASE,
        "--write-auto-subs",
        "--sub-lang", "en,en-US,en-GB",
        "--skip-download",
        "--sub-format", "vtt",
        "-o", output_template,
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        return None

    vtt_files = sorted(output_dir.glob("*.en.vtt"), key=os.path.getmtime, reverse=True)
    if not vtt_files:
        # Try other language variants
        vtt_files = sorted(output_dir.glob("*.vtt"), key=os.path.getmtime, reverse=True)

    if not vtt_files:
        return None

    raw = vtt_files[0].read_text(encoding="utf-8")
    return _clean_vtt(raw)


# ── Transcribe (fallback) ───────────────────────────────────────────

def transcribe_with_whisper(audio_path: Path, output_dir: Path, model: str = "medium",
                           language: str | None = None) -> str:
    """Transcribe audio using local Whisper. Auto-detects language by default."""
    cmd = [
        "whisper",
        str(audio_path),
        "--model", model,
        "--output_dir", str(output_dir),
        "--output_format", "txt",
    ]
    if language:
        cmd.extend(["--language", language])
    subprocess.run(cmd, check=True)

    txt_files = sorted(output_dir.glob("*.txt"), key=os.path.getmtime, reverse=True)
    if not txt_files:
        raise FileNotFoundError("Whisper 转录完成但未找到输出文件")
    return txt_files[0].read_text(encoding="utf-8")


# ── Distill ─────────────────────────────────────────────────────────


def distill_to_cards(transcript: str, video_info: dict[str, str]) -> list[dict]:
    """Use Claude to distill transcript into 4 card dicts."""
    title = video_info.get("title", "")
    uploader = video_info.get("uploader", "")
    desc = video_info.get("description", "")

    user_text = f"""视频标题：{title}
频道：{uploader}
简介：{desc}

逐字稿：
{transcript[:25000]}"""

    response = call_claude(SYSTEM_PROMPT, user_text, max_tokens=8192, timeout=180)
    if not response:
        raise RuntimeError("Claude API 调用失败，请检查 ANTHROPIC_API_KEY 环境变量")

    cards = parse_json_lenient(response)
    if not cards or not isinstance(cards, list):
        raise RuntimeError(f"Claude 返回格式无法解析，原始响应前 200 字：\n{response[:200]}")

    return cards


# ── Main ────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="YouTube 视频 → 小红书图文卡片（4张卡片 + 封面）"
    )
    parser.add_argument("url", nargs="?", help="YouTube 视频链接")
    parser.add_argument("--output-dir", "-o", help="输出目录（默认 xiaohongshu/<今天日期>）")
    parser.add_argument("--whisper-model", default="medium",
                        choices=["tiny", "base", "small", "medium", "large"],
                        help="Whisper 模型大小（默认 medium，仅 fallback 时使用）")
    parser.add_argument("--language", default=None,
                        help="Whisper 语言代码，如 zh/en/ja。默认自动检测")
    parser.add_argument("--force-whisper", action="store_true",
                        help="强制使用 Whisper 转录，跳过 YouTube 字幕")
    parser.add_argument("--auto-publish", action="store_true",
                        help="生成完毕后自动打开小红书创作者中心")
    parser.add_argument("--skip-download", action="store_true", help="跳过下载步骤")
    parser.add_argument("--skip-transcribe", action="store_true", help="跳过转录步骤")
    parser.add_argument("--audio", help="已有音频文件路径（配合 --skip-download）")
    parser.add_argument("--transcript", help="已有逐字稿文件路径（配合 --skip-transcribe）")
    args = parser.parse_args()

    if not args.url and not args.audio and not args.transcript:
        parser.error("必须提供 YouTube URL，或 --audio/--transcript")

    today = date.today().isoformat()
    output_dir = Path(args.output_dir) if args.output_dir else _PROJECT_ROOT / "xiaohongshu" / today
    output_dir.mkdir(parents=True, exist_ok=True)

    work_dir = Path(tempfile.mkdtemp(prefix="yt_xhs_"))
    print(f"📁 工作目录: {work_dir}")
    print(f"📁 输出目录: {output_dir}")

    try:
        # ── Step 1: Download ──
        if args.skip_download:
            if not args.audio:
                parser.error("--skip-download 需要配合 --audio 使用")
            audio_path = Path(args.audio)
            if not audio_path.exists():
                sys.exit(f"音频文件不存在: {audio_path}")
            video_info = {"title": audio_path.stem, "uploader": "", "description": ""}
            print(f"⏭️  跳过下载，使用已有音频: {audio_path.name}")
        else:
            print("⬇️  正在获取视频信息...")
            video_info = _get_video_info(args.url)
            print(f"   📺 {video_info.get('title', '未知标题')}")
            print(f"   🎙️  {video_info.get('uploader', '未知频道')}")

        # ── Step 2: Get transcript (captions first, Whisper fallback) ──
        if args.skip_transcribe:
            if not args.transcript:
                parser.error("--skip-transcribe 需要配合 --transcript 使用")
            transcript_path = Path(args.transcript)
            if not transcript_path.exists():
                sys.exit(f"逐字稿文件不存在: {transcript_path}")
            transcript = transcript_path.read_text(encoding="utf-8")
            print(f"⏭️  跳过转录，使用已有文本 ({len(transcript)} 字)")
        elif args.force_whisper:
            # ── Whisper path ──
            if args.skip_download:
                pass  # audio already available
            else:
                print("⬇️  正在下载音频...")
                audio_path, video_info = download_audio(args.url, work_dir)
                print(f"   ✅ 下载完成: {audio_path.name}")

            lang_note = f", 语言: {args.language}" if args.language else ""
            print(f"🎙️  正在用 Whisper ({args.whisper_model}{lang_note}) 转录...")
            transcript = transcribe_with_whisper(audio_path, work_dir, args.whisper_model, args.language)
            print(f"   ✅ 转录完成 ({len(transcript)} 字)")
        else:
            # ── Fast path: try YouTube captions ──
            print("🔍 正在下载 YouTube 自动字幕...")
            transcript = download_youtube_captions(args.url, work_dir)

            if transcript and len(transcript) > 200:
                print(f"   ✅ 字幕获取成功 ({len(transcript)} 字)")
            else:
                # ── Fallback: download audio + Whisper ──
                print("   ⚠️  字幕不可用，fallback 到 Whisper 转录...")
                print("⬇️  正在下载音频...")
                audio_path, video_info = download_audio(args.url, work_dir)
                print(f"   ✅ 下载完成: {audio_path.name}")

                print(f"🎙️  正在用 Whisper ({args.whisper_model}) 转录...")
                transcript = transcribe_with_whisper(audio_path, work_dir, args.whisper_model, args.language)
                print(f"   ✅ 转录完成 ({len(transcript)} 字)")

        # ── Step 3: Distill ──
        print("🧠 正在用 Claude 蒸馏内容为 4 张卡片...")
        cards = distill_to_cards(transcript, video_info)
        cards = cards[:4]
        for i, c in enumerate(cards, 1):
            print(f"   {i}. {c.get('emoji', '📌')} {c.get('title', '?')}")
        print(f"   ✅ 提炼完成 ({len(cards)} 条)")

        # ── Step 4: Generate HTML ──
        print("🎨 正在生成卡片 HTML...")
        card_paths, cover_path, caption_path = save_cards_and_cover(
            cards, output_dir, today
        )
        print(f"   ✅ {len(card_paths)} 张卡片 + 封面 + 文案已生成")

        # ── Step 5: Screenshot ──
        print("📸 正在截图 (1080×1440 @2x)...")
        all_html = [cover_path] + card_paths
        png_paths = screenshot_htmls(all_html, output_dir)

        if png_paths:
            print(f"   ✅ 生成 {len(png_paths)} 张 PNG")
            for p in png_paths:
                print(f"      {p.name}")
        else:
            print("   ⚠️  Playwright 截图失败，但 HTML 文件已生成")
            print("   你可以手动用浏览器打开 HTML 截图")

        # ── Summary ──
        print()
        print("=" * 56)
        print("✅ 全部完成！")
        print(f"   输出目录: {output_dir}")
        print(f"   封面: {output_dir}/{today}_cover.png" if png_paths else f"   封面: {cover_path}")
        print(f"   文案: {caption_path}")
        print(f"   卡片数: {len(cards)}")
        print("=" * 56)

        # ── Optional: Auto-publish ──
        if args.auto_publish:
            print()
            print("🚀 正在启动小红书自动发布...")
            publish_script = _PROJECT_ROOT / "xhs_publish" / "publish_xiaohongshu_auto.py"
            if publish_script.exists():
                subprocess.Popen(
                    [sys.executable, str(publish_script), today],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                print("   浏览器将打开，请手动点击发布按钮")
            else:
                print(f"   ⚠️  找不到发布脚本: {publish_script}")

    finally:
        # Cleanup temp dir
        shutil.rmtree(work_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
