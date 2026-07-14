#!/usr/bin/env python3
"""Feedback loop — close the gap between prediction and performance.

Three components:
  1. publish_log  — records every publish with quality scores
  2. score-vs-performance comparison — matches pre-publish scores to actual engagement
  3. preference update — feeds learnings back to .claude/preferences.md

Usage:
  python3 news_pipeline/feedback_loop.py --log <date>     # record a publish
  python3 news_pipeline/feedback_loop.py --compare         # score vs perf report
  python3 news_pipeline/feedback_loop.py --update-prefs    # update preferences.md
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
LOG_PATH = PROJECT_DIR / "xiaohongshu" / "publish_log.json"
ANALYTICS_DIR = PROJECT_DIR / "xiaohongshu" / "analytics"
PREFERENCES_PATH = PROJECT_DIR / ".claude" / "preferences.md"


# ═══════════════════════════════════════════════════════════════
# 1. Publish logger
# ═══════════════════════════════════════════════════════════════

def log_publish(date_str: str, items: list[dict], platform_captions: dict | None = None) -> dict:
    """Record a publish event with quality scores and platform info.

    Args:
        date_str: publish date YYYY-MM-DD
        items: list of published items (each should have _quality_score)
        platform_captions: optional multi-platform caption dict

    Returns the saved log entry.
    """
    log = _load_log()

    entry = {
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "item_count": len(items),
        "items": [],
        "platforms": list(platform_captions.keys()) if platform_captions else [],
        "avg_score": 0,
    }

    total_score = 0
    for item in items:
        score = item.get("_quality_score", {})
        item_record = {
            "title": item.get("title", ""),
            "category": item.get("category", ""),
            "emoji": item.get("emoji", ""),
            "source_note": item.get("source_note", ""),
            "quality_score": score.get("total", 0),
            "scores": {
                "hook": score.get("hook", 0),
                "structure": score.get("structure", 0),
                "cta": score.get("cta", 0),
                "density": score.get("density", 0),
            },
            "verdict": score.get("verdict", "ok"),
        }
        entry["items"].append(item_record)
        total_score += score.get("total", 0)

    if items:
        entry["avg_score"] = round(total_score / len(items), 1)

    # Deduplicate by date — replace existing entry for same date
    log = [e for e in log if e.get("date") != date_str]
    log.append(entry)
    log.sort(key=lambda e: e["date"], reverse=True)

    _save_log(log)
    print(f"  [feedback] logged publish {date_str}: {len(items)} items, avg {entry['avg_score']}/40")
    return entry


# ═══════════════════════════════════════════════════════════════
# 2. Score vs performance comparison
# ═══════════════════════════════════════════════════════════════

def compare_scores_to_performance() -> str | None:
    """Match pre-publish quality scores with analytics data. Returns Markdown report or None."""
    log = _load_log()
    analytics = _load_analytics()

    if not log:
        print("  [feedback] no publish log found")
        return None
    if not analytics:
        print("  [feedback] no analytics data found (run analytics.py first)")
        return None

    lines = [
        "# 质量预判 vs 实际表现 — 对比报告",
        f"\n生成于 {date.today()}",
        "\n## 数据概览\n",
    ]

    matched = 0
    overrated = 0  # high score, low engagement
    underrated = 0  # low score, high engagement

    for entry in log[-10:]:  # last 10 publishes
        pub_date = entry["date"]
        pub_avg = entry.get("avg_score", 0)

        # Find matching analytics
        a_data = analytics.get(pub_date, {})
        engagement = a_data.get("engagement_rate", 0) if a_data else 0

        if engagement:
            matched += 1
            # Engagement rate typically < 0.1 — normalize to 0-40 scale
            engagement_scaled = min(engagement * 400, 40)

            delta = engagement_scaled - pub_avg
            if delta < -5:
                overrated += 1
                flag = "🔴 高估"
            elif delta > 5:
                underrated += 1
                flag = "🟢 低估"
            else:
                flag = "⚪ 吻合"

            lines.append(
                f"| {pub_date} | {pub_avg}/40 | {engagement:.2%} | "
                f"{engagement_scaled:.0f}/40 | {delta:+.1f} | {flag} |"
            )

    if matched == 0:
        lines.append("_暂无匹配数据 — 需要先跑 analytics.py 采集互动数据_\n")
    else:
        lines.insert(3, "| 日期 | 预判分 | 互动率 | 实际表现 | 偏差 | 判定 |")
        lines.insert(4, "|------|--------|--------|----------|------|------|")
        lines.append(f"\n**匹配 {matched} 条**: 高估 {overrated} | 低估 {underrated} | 吻合 {matched - overrated - underrated}\n")

    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# 3. Preference update
# ═══════════════════════════════════════════════════════════════

PREF_UPDATE_PROMPT = """You are a content strategist. Based on recent publish log data, suggest updates to content preferences.

Recent publish log:
{log_data}

For each suggestion, output:
- category: which content category to adjust
- action: "more" | "less" | "keep"
- reason: one-line reason based on quality scores or engagement data

Return ONLY a JSON array:
[{{"category": "...", "action": "...", "reason": "..."}}]
"""


def update_preferences() -> str | None:
    """Analyze publish log and suggest preference updates. Returns suggestion text."""
    log = _load_log()
    if not log:
        print("  [feedback] no publish log to analyze")
        return None

    # Format recent log for analysis
    log_lines = []
    for entry in log[:10]:
        log_lines.append(f"- {entry['date']}: avg score {entry.get('avg_score', 0)}/40, {entry.get('item_count', 0)} items")
        for item in entry.get("items", []):
            log_lines.append(
                f"  [{item['category']}] {item['title'][:40]} "
                f"→ {item['quality_score']}/40 (hook:{item['scores']['hook']} "
                f"struct:{item['scores']['structure']} cta:{item['scores']['cta']} "
                f"density:{item['scores']['density']})"
            )

    prompt = PREF_UPDATE_PROMPT.replace("{log_data}", "\n".join(log_lines))

    # Call Claude via shared util
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from claude_utils import call_claude, parse_json_lenient

    raw = call_claude(prompt, "", max_tokens=2048)
    if not raw:
        return None

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, list):
        return None

    # Format as preferences section
    lines = ["\n## 本周选题偏好（AI 自动更新）\n"]
    for rec in parsed:
        action_icon = {"more": "⬆️ 增加", "less": "⬇️ 减少", "keep": "✅ 保持"}.get(
            rec.get("action", "keep"), "✅ 保持"
        )
        lines.append(
            f"- {action_icon} **{rec.get('category', '')}**: "
            f"{rec.get('reason', '')}"
        )
    lines.append(f"\n_自动更新于 {date.today()}_\n")

    suggestion = "\n".join(lines)

    # Append to preferences.md
    _update_preferences_file(suggestion)

    return suggestion


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _load_log() -> list[dict]:
    if LOG_PATH.is_file():
        try:
            return json.loads(LOG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def _save_log(log: list[dict]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")


def _load_analytics() -> dict[str, dict]:
    """Load all analytics JSON files, keyed by date."""
    result: dict[str, dict] = {}
    if not ANALYTICS_DIR.is_dir():
        return result
    for f in sorted(ANALYTICS_DIR.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            date_key = f.stem  # e.g., "2026-07-13"
            # Extract engagement metrics
            notes = data.get("notes", []) if isinstance(data, dict) else data
            if isinstance(notes, list):
                total_likes = sum(n.get("likes", 0) for n in notes)
                total_saves = sum(n.get("saves", 0) for n in notes)
                total_comments = sum(n.get("comments", 0) for n in notes)
                total_views = sum(n.get("views", 0) for n in notes)
                engagement = (total_likes + total_saves + total_comments) / max(total_views, 1)
            else:
                engagement = 0
            result[date_key] = {
                "engagement_rate": engagement,
                "views": total_views if isinstance(notes, list) else 0,
                "likes": total_likes if isinstance(notes, list) else 0,
                "saves": total_saves if isinstance(notes, list) else 0,
                "comments": total_comments if isinstance(notes, list) else 0,
            }
        except Exception:
            continue
    return result


def _update_preferences_file(suggestion: str) -> None:
    """Append or update the preferences suggestion block in preferences.md."""
    if not PREFERENCES_PATH.is_file():
        return

    content = PREFERENCES_PATH.read_text(encoding="utf-8")

    # Remove old auto-updated section
    marker = "## 本周选题偏好（AI 自动更新"
    lines = content.split("\n")
    new_lines = []
    skip = False
    for line in lines:
        if marker in line:
            skip = True
            continue
        if skip:
            if line.startswith("## ") or line.startswith("# "):
                skip = False
                new_lines.append(line)
            continue
        new_lines.append(line)

    # Append new suggestion
    new_lines.append(suggestion)
    PREFERENCES_PATH.write_text("\n".join(new_lines), encoding="utf-8")
    print(f"  [feedback] preferences.md updated")


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--compare" in sys.argv:
        report = compare_scores_to_performance()
        if report:
            print(report)
    elif "--update-prefs" in sys.argv:
        result = update_preferences()
        if result:
            print(result)
    elif "--log" in sys.argv:
        print("  Use log_publish() from fetch_ai_news.py")
    else:
        print(__doc__)
