#!/usr/bin/env python3
"""Zhipu (智谱) GLM-TTS narration adapter.

Uses Zhipu's TTS API with voices like tongtong, xiaochen.
No credit card needed — register with phone number at open.bigmodel.cn
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.request
from pathlib import Path

FFMPEG_PATH = str(
    Path.home() / "Library/Application Support/bilibili/ffmpeg/ffmpeg"
)
if not Path(FFMPEG_PATH).is_file():
    FFMPEG_PATH = "ffmpeg"

# ---- Config ----

API_BASE = "https://open.bigmodel.cn/api/paas/v4/audio/speech"
DEFAULT_VOICE = "chuichui"   # 锤锤 — 可爱风格
DEFAULT_MODEL = "glm-tts"

# ---- Public API ----

def get_key() -> str:
    """Read Zhipu API key from env or config file."""
    key = os.environ.get("ZHIPU_API_KEY", "")
    if not key:
        config_file = Path.home() / ".zhipu_tts_key"
        if config_file.exists():
            key = config_file.read_text().strip()
    return key


def generate_narration(text: str, output_path: Path,
                       voice: str = DEFAULT_VOICE,
                       model: str = DEFAULT_MODEL) -> Path:
    """Generate WAV narration via Zhipu TTS. Returns path to .wav file.

    Args:
        text: Chinese text (max ~1024 chars)
        output_path: output .wav file path
        voice: tongtong/xiaochen/chuichui
        model: glm-tts (default)
    """
    api_key = get_key()
    if not api_key:
        raise RuntimeError(
            "ZHIPU_API_KEY not set. Put key in ~/.zhipu_tts_key or env var."
        )

    payload = json.dumps({
        "model": model,
        "input": text,
        "voice": voice,
        "response_format": "wav",
        "speed": 2.0,
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        API_BASE,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            audio_data = resp.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Zhipu TTS failed ({exc.code}): {error_body}")

    output_path.write_bytes(audio_data)
    return output_path


def generate_narration_aac(text: str, output_aac: Path,
                           voice: str = DEFAULT_VOICE) -> Path:
    """Generate AAC narration (wav → aac via ffmpeg)."""
    wav_path = output_aac.with_suffix(".wav")
    generate_narration(text, wav_path, voice=voice)
    subprocess.run([
        FFMPEG_PATH, "-y", "-i", str(wav_path),
        "-c:a", "aac", "-b:a", "128k", str(output_aac),
    ], capture_output=True, text=True, timeout=30)
    wav_path.unlink(missing_ok=True)
    return output_aac
