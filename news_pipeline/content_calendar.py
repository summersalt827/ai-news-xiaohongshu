#!/usr/bin/env python3
"""Content calendar — schedule, view, and manage AI content publishing.

Recurring slots:
  - Every Sunday 20:03 — AI News 周报 (cron-triggered)

Manual slots:
  - AI Skills 深度 — manually scheduled per date

Storage: xiaohongshu/content_calendar.json

Usage:
  python3 news_pipeline/content_calendar.py                    # show upcoming
  python3 news_pipeline/content_calendar.py --add <date> <brand> [note]
  python3 news_pipeline/content_calendar.py --remove <date>
  python3 news_pipeline/content_calendar.py --month 2026-07    # month view
  python3 news_pipeline/content_calendar.py --publish <date>   # mark as published
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CALENDAR_PATH = PROJECT_DIR / "xiaohongshu" / "content_calendar.json"


# ═══════════════════════════════════════════════════════════════
# Calendar data
# ═══════════════════════════════════════════════════════════════

def _load() -> dict:
    if CALENDAR_PATH.is_file():
        try:
            return json.loads(CALENDAR_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"slots": [], "recurring": [], "published": []}


def _save(data: dict) -> None:
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ═══════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════

def add_slot(pub_date: str, brand_id: str, note: str = "") -> dict:
    """Schedule a content slot for a specific date.

    Args:
        pub_date: YYYY-MM-DD
        brand_id: brand id (e.g. 'ai-skills-deep')
        note: optional description
    """
    data = _load()

    # Remove existing slot for same date
    data["slots"] = [s for s in data["slots"] if s["date"] != pub_date]

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from brand_manager import get_brand
    brand = get_brand(brand_id)
    brand_name = brand["_meta"]["name"] if brand else brand_id

    slot = {
        "date": pub_date,
        "brand_id": brand_id,
        "brand_name": brand_name,
        "note": note,
        "status": "scheduled",
        "created": datetime.now().isoformat(),
    }
    data["slots"].append(slot)
    data["slots"].sort(key=lambda s: s["date"])
    _save(data)
    print(f"  📅 已排期: {pub_date} — {brand_name}" + (f" ({note})" if note else ""))
    return slot


def remove_slot(pub_date: str) -> bool:
    """Remove a scheduled slot."""
    data = _load()
    before = len(data["slots"])
    data["slots"] = [s for s in data["slots"] if s["date"] != pub_date]
    if len(data["slots"]) < before:
        _save(data)
        print(f"  🗑️  已移除: {pub_date}")
        return True
    print(f"  ⚠️  未找到排期: {pub_date}")
    return False


def mark_published(pub_date: str) -> None:
    """Mark a slot as published."""
    data = _load()
    for slot in data["slots"]:
        if slot["date"] == pub_date:
            slot["status"] = "published"
            slot["published_at"] = datetime.now().isoformat()
    data["published"].append(pub_date)
    _save(data)
    print(f"  ✅ 已发布: {pub_date}")


def get_upcoming(days: int = 14) -> list[dict]:
    """Get upcoming scheduled content for the next N days."""
    data = _load()
    today = date.today()
    end = today + timedelta(days=days)

    upcoming = []
    for slot in data["slots"]:
        try:
            slot_date = date.fromisoformat(slot["date"])
            if today <= slot_date <= end and slot.get("status") != "published":
                upcoming.append(slot)
        except ValueError:
            continue
    return upcoming


def get_month_view(year: int, month: int) -> str:
    """Generate a formatted month calendar view."""
    data = _load()
    slots_by_date: dict[str, list] = {}
    for slot in data["slots"]:
        d = slot["date"]
        slots_by_date.setdefault(d, []).append(slot)

    # Add recurring Sunday slots
    first_day = date(year, month, 1)
    if month == 12:
        last_day = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        last_day = date(year, month + 1, 1) - timedelta(days=1)

    lines = [f"\n  📅 {year}年{month}月 — 内容日历", f"  {'─' * 50}"]
    current = first_day
    while current <= last_day:
        d_str = current.isoformat()
        weekday = ["一", "二", "三", "四", "五", "六", "日"][current.weekday()]
        marker = "📰" if current.weekday() == 6 else "  "  # Sunday marker

        if d_str in slots_by_date:
            for slot in slots_by_date[d_str]:
                status_icon = "✅" if slot.get("status") == "published" else "📋"
                lines.append(
                    f"  {marker} {d_str} ({weekday}) {status_icon} "
                    f"{slot.get('brand_name', '?')}"
                    + (f" — {slot['note']}" if slot.get("note") else "")
                )
        elif current.weekday() == 6:
            lines.append(f"  {marker} {d_str} ({weekday}) 🔄 AI News 周报 (自动)")

        current += timedelta(days=1)

    return "\n".join(lines)


def get_next_sunday() -> str:
    """Return next Sunday's date as YYYY-MM-DD."""
    today = date.today()
    days_until_sunday = (6 - today.weekday()) % 7
    if days_until_sunday == 0:
        days_until_sunday = 7  # if today is Sunday, next week
    return (today + timedelta(days=days_until_sunday)).isoformat()


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--add" in sys.argv:
        idx = sys.argv.index("--add")
        if idx + 2 < len(sys.argv):
            pub_date = sys.argv[idx + 1]
            brand_id = sys.argv[idx + 2]
            note = sys.argv[idx + 3] if idx + 3 < len(sys.argv) else ""
            add_slot(pub_date, brand_id, note)
    elif "--remove" in sys.argv:
        idx = sys.argv.index("--remove")
        if idx + 1 < len(sys.argv):
            remove_slot(sys.argv[idx + 1])
    elif "--publish" in sys.argv:
        idx = sys.argv.index("--publish")
        if idx + 1 < len(sys.argv):
            mark_published(sys.argv[idx + 1])
    elif "--month" in sys.argv:
        idx = sys.argv.index("--month")
        if idx + 1 < len(sys.argv):
            parts = sys.argv[idx + 1].split("-")
            if len(parts) == 2:
                print(get_month_view(int(parts[0]), int(parts[1])))
    else:
        # Default: show upcoming
        upcoming = get_upcoming(14)
        if upcoming:
            print(f"\n  📅 未来 14 天内容计划:")
            print(f"  {'─' * 50}")
            for slot in upcoming:
                status = {"scheduled": "📋", "published": "✅"}.get(slot.get("status", ""), "  ")
                print(
                    f"  {status} {slot['date']}  {slot.get('brand_name', '?')}"
                    + (f" — {slot['note']}" if slot.get("note") else "")
                )
        else:
            print("  📅 未来 14 天无排期内容")
            next_sun = get_next_sunday()
            print(f"  🔄 下一个周报: {next_sun} (自动)")
