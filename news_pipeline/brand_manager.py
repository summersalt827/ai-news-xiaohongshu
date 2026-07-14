#!/usr/bin/env python3
"""Brand profile manager — load, switch, and apply brand configurations.

Brands are JSON files in brands/ directory. Each brand defines:
  - visual tokens (colors, borders, shadows)
  - typography (fonts, sizes, weights)
  - card layout preferences
  - cover defaults
  - video preferences (BGM, TTS voice, timing)
  - social media settings (hashtags, tone)

Usage:
  python3 news_pipeline/brand_manager.py --list              # list all brands
  python3 news_pipeline/brand_manager.py --switch <id>       # set active brand
  python3 news_pipeline/brand_manager.py --current           # show active brand
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
BRANDS_DIR = PROJECT_DIR / "brands"
ACTIVE_BRAND_FILE = PROJECT_DIR / ".active_brand"


# ═══════════════════════════════════════════════════════════════
# Load / switch / list
# ═══════════════════════════════════════════════════════════════

def list_brands() -> list[dict]:
    """Return all available brand profiles sorted by name."""
    brands = []
    if BRANDS_DIR.is_dir():
        for f in sorted(BRANDS_DIR.glob("*.json")):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                data.setdefault("_filename", f.name)
                brands.append(data)
            except Exception:
                continue
    return sorted(brands, key=lambda b: b.get("_meta", {}).get("name", ""))


def get_brand(brand_id: str | None = None) -> dict | None:
    """Get a brand profile by id. If None, returns active brand or default."""
    if brand_id is None:
        brand_id = _active_brand_id()

    # Try exact filename match first
    fname = f"{brand_id}.json"
    path = BRANDS_DIR / fname
    if not path.is_file():
        # Search by _meta.id
        for b in list_brands():
            if b.get("_meta", {}).get("id") == brand_id:
                path = BRANDS_DIR / b["_filename"]
                break

    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
    return None


def get_active_brand() -> dict:
    """Get the currently active brand profile. Falls back to first default brand."""
    active_id = _active_brand_id()
    brand = get_brand(active_id) if active_id else None
    if brand:
        return brand

    # Fallback: first brand with default:true
    for b in list_brands():
        if b.get("_meta", {}).get("default"):
            return b

    # Last resort: first brand
    brands = list_brands()
    return brands[0] if brands else {}


def switch_brand(brand_id: str) -> dict | None:
    """Switch active brand. Returns the new brand profile or None if not found."""
    brand = get_brand(brand_id)
    if brand:
        ACTIVE_BRAND_FILE.write_text(brand_id)
        print(f"  ✅ 已切换到品牌: {brand['_meta']['name']}")
    else:
        print(f"  ❌ 品牌 '{brand_id}' 不存在")
        print(f"  可用品牌: {[b['_meta']['id'] for b in list_brands()]}")
    return brand


# ═══════════════════════════════════════════════════════════════
# Token extraction helpers — for use by renderers
# ═══════════════════════════════════════════════════════════════

def visual_tokens(brand: dict | None = None) -> dict:
    """Get visual CSS tokens for the given brand (or active brand)."""
    b = brand or get_active_brand()
    return b.get("visual", {})


def typography_tokens(brand: dict | None = None) -> dict:
    """Get typography tokens."""
    b = brand or get_active_brand()
    return b.get("typography", {})


def social_settings(brand: dict | None = None) -> dict:
    """Get social media settings (hashtags, tone)."""
    b = brand or get_active_brand()
    return b.get("social", {})


def video_settings(brand: dict | None = None) -> dict:
    """Get video preferences."""
    b = brand or get_active_brand()
    return b.get("video", {})


def card_config(brand: dict | None = None) -> dict:
    """Get card layout configuration."""
    b = brand or get_active_brand()
    return b.get("card", {})


# ═══════════════════════════════════════════════════════════════
# Brand-aware content generation helpers
# ═══════════════════════════════════════════════════════════════

def get_xhs_hashtags(brand: dict | None = None) -> str:
    """Get space-separated Xiaohongshu hashtags for the brand."""
    tags = social_settings(brand).get("xhs_hashtags", [])
    return " ".join(tags)


def get_bgm_paths(brand: dict | None = None) -> list[str]:
    """Get preferred BGM file paths for the brand."""
    b = brand or get_active_brand()
    prefs = video_settings(b).get("bgm_preference", [])
    bgm_dir = PROJECT_DIR / "bgm"
    paths = []
    for pref in prefs:
        candidate = bgm_dir / pref
        if candidate.is_file():
            paths.append(str(candidate))
    # Fallback: any mp3 in bgm/
    if not paths and bgm_dir.is_dir():
        mp3s = sorted(bgm_dir.glob("*.mp3"))
        if mp3s:
            paths.append(str(mp3s[0]))
    return paths


def get_tts_voice(brand: dict | None = None) -> str:
    """Get preferred TTS voice name for the brand."""
    b = brand or get_active_brand()
    return video_settings(b).get("tts_voice", "xiaoxiao")


# ═══════════════════════════════════════════════════════════════
# Internal
# ═══════════════════════════════════════════════════════════════

def _active_brand_id() -> str | None:
    if ACTIVE_BRAND_FILE.is_file():
        return ACTIVE_BRAND_FILE.read_text().strip()
    return None


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--list" in sys.argv:
        print("\n  可用品牌:")
        for b in list_brands():
            active = "✅" if b["_meta"]["id"] == _active_brand_id() else "  "
            default = " (默认)" if b["_meta"].get("default") else ""
            print(f"  {active} {b['_meta']['id']:<25} {b['_meta']['name']}{default}")
            print(f"       {b['_meta']['description']}")
    elif "--switch" in sys.argv:
        idx = sys.argv.index("--switch")
        if idx + 1 < len(sys.argv):
            switch_brand(sys.argv[idx + 1])
    elif "--current" in sys.argv:
        brand = get_active_brand()
        if brand:
            name = brand["_meta"]["name"]
            visual = brand.get("visual", {})
            print(f"  当前品牌: {name}")
            print(f"  主色: {visual.get('primary', '?')}")
            print(f"  强调色: {visual.get('accent', '?')}")
            print(f"  标签: {get_xhs_hashtags(brand)[:80]}...")
    else:
        print(__doc__)
