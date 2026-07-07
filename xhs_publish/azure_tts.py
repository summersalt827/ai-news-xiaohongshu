#!/usr/bin/env python3
"""Azure TTS narration — drop-in replacement for macOS say command.

Uses Azure Cognitive Services Speech SDK with neural voices.
zh-CN-XiaoxiaoNeural is the most popular female voice (same as Edge TTS 晓晓).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FFMPEG_PATH = str(
    Path.home() / "Library/Application Support/bilibili/ffmpeg/ffmpeg"
)
if not Path(FFMPEG_PATH).is_file():
    FFMPEG_PATH = "ffmpeg"

# ---- Config ----

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"        # 晓晓 — 活泼、清晰
ALT_VOICES = {
    "xiaoxiao": "zh-CN-XiaoxiaoNeural",        # 晓晓 — 活泼女声
    "yunxi":    "zh-CN-YunxiNeural",           # 云希 — 男声，播客风
    "xiaoyi":   "zh-CN-XiaoyiNeural",          # 晓伊 — 温柔女声
    "yunjian":  "zh-CN-YunjianNeural",         # 云健 — 男声，新闻风
    "xiaochen": "zh-CN-XiaochenNeural",        # 晓辰 — 冷静女声
}

# ---- Public API ----

def get_key_region() -> tuple[str, str]:
    """Read Azure Speech key & region from env or config file."""
    key = os.environ.get("AZURE_SPEECH_KEY", "")
    region = os.environ.get("AZURE_SPEECH_REGION", "eastasia")
    if not key:
        config_file = Path.home() / ".azure_tts_key"
        if config_file.exists():
            lines = config_file.read_text().strip().splitlines()
            key = lines[0].strip() if lines else ""
            if len(lines) > 1:
                region = lines[1].strip()
    return key, region


def generate_narration(text: str, output_path: Path, voice: str = DEFAULT_VOICE) -> Path:
    """Generate MP3 narration with Azure TTS. Returns path to .mp3 file.

    Args:
        text: Chinese text to speak
        output_path: output .mp3 file path
        voice: Azure voice name, e.g. zh-CN-XiaoxiaoNeural
    """
    import azure.cognitiveservices.speech as speechsdk

    key, region = get_key_region()
    if not key:
        raise RuntimeError(
            "AZURE_SPEECH_KEY not set. Put key in ~/.azure_tts_key or env var."
        )

    speech_config = speechsdk.SpeechConfig(subscription=key, region=region)
    speech_config.speech_synthesis_voice_name = voice
    speech_config.set_speech_synthesis_output_format(
        speechsdk.SpeechSynthesisOutputFormat.Audio48Khz192KBitRateMonoMp3
    )

    # Use in-memory synthesis then write to file
    synthesizer = speechsdk.SpeechSynthesizer(speech_config=speech_config, audio_config=None)
    result = synthesizer.speak_text_async(text).get()

    if result.reason == speechsdk.ResultReason.SynthesizingAudioCompleted:
        with open(output_path, "wb") as f:
            f.write(result.audio_data)
        return output_path
    else:
        cancellation = result.cancellation_details
        raise RuntimeError(
            f"Azure TTS failed: {result.reason} — "
            f"{cancellation.error_code}: {cancellation.error_details}"
        )


def generate_narration_aac(text: str, output_aac: Path, voice: str = DEFAULT_VOICE) -> Path:
    """Generate AAC narration (ffmpeg converts mp3 → aac). Compatible with render_video."""
    mp3_path = output_aac.with_suffix(".mp3")
    generate_narration(text, mp3_path, voice=voice)
    # Convert MP3 → AAC
    subprocess.run([
        FFMPEG_PATH, "-y", "-i", str(mp3_path),
        "-c:a", "aac", "-b:a", "128k", str(output_aac),
    ], capture_output=True, text=True, timeout=30)
    mp3_path.unlink(missing_ok=True)
    return output_aac
