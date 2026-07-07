#!/usr/bin/env python3
"""YouTube 内容蒸馏器 — 一个命令，一个链接，4张卡片。

这是 youtube_to_xhs.py 的简化入口，专门面向「我只想蒸馏一个视频」的场景。

用法:
    python3 distill.py https://www.youtube.com/watch?v=xxxxx
    python3 distill.py https://youtu.be/xxxxx --output ~/Desktop/my-cards
    python3 distill.py https://www.youtube.com/watch?v=xxxxx --force-whisper

安装:
    # 1. Python 依赖
    pip install -r requirements.txt

    # 2. 系统工具 (macOS)
    brew install yt-dlp ffmpeg
    pipx install openai-whisper    # 可选，视频无字幕时用

    # 3. 设置 API key
    export ANTHROPIC_API_KEY=sk-ant-xxx

输出:
    xiaohongshu/<日期>/ 下生成 4 张卡片 PNG + 封面 + 文案
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# 确保项目模块可导入
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR / "news_pipeline"))
sys.path.insert(0, str(_SCRIPT_DIR / "xhs_publish"))


def _check_deps():
    """检查命令行工具是否可用。"""
    for cmd in ["yt-dlp"]:
        if subprocess.run(["which", cmd], capture_output=True).returncode != 0:
            print(f"❌ 缺少系统依赖: {cmd}")
            print(f"   请运行: brew install {cmd}")
            sys.exit(1)


def main():
    _check_deps()

    # 把控制权交给 youtube_to_xhs，保留所有命令行参数
    from news_pipeline.youtube_to_xhs import main as yt_main

    yt_main()


if __name__ == "__main__":
    main()
