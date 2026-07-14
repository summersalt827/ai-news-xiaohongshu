#!/usr/bin/env python3
"""Competitive analysis — track rivals, extract patterns, generate intelligence.

Competitor profiles stored in xiaohongshu/competitors.json.
Analysis reports stored in xiaohongshu/competitive-reports/.

Usage:
  python3 news_pipeline/competitive_tracker.py --add <platform> <name> <url>
  python3 news_pipeline/competitive_tracker.py --list
  python3 news_pipeline/competitive_tracker.py --analyze
  python3 news_pipeline/competitive_tracker.py --report
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
COMPETITORS_PATH = PROJECT_DIR / "xiaohongshu" / "competitors.json"
REPORTS_DIR = PROJECT_DIR / "xiaohongshu" / "competitive-reports"

# ═══════════════════════════════════════════════════════════════
# Competitor profile management
# ═══════════════════════════════════════════════════════════════

def _load_competitors() -> list[dict]:
    if COMPETITORS_PATH.is_file():
        try:
            return json.loads(COMPETITORS_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return []


def _save_competitors(competitors: list[dict]) -> None:
    COMPETITORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    COMPETITORS_PATH.write_text(json.dumps(competitors, ensure_ascii=False, indent=2), encoding="utf-8")


def add_competitor(platform: str, name: str, url: str, niche: str = "") -> dict:
    """Add a competitor to track.

    Args:
        platform: xiaohongshu | bilibili | youtube | twitter
        name: account name
        url: profile URL
        niche: content niche (e.g. 'AI新闻', 'AI工具测评')
    """
    competitors = _load_competitors()

    profile = {
        "id": f"{platform}:{name}",
        "platform": platform,
        "name": name,
        "url": url,
        "niche": niche,
        "added": date.today().isoformat(),
        "last_checked": None,
        "post_count": 0,
        "avg_engagement": 0,
        "top_topics": [],
        "notes": "",
    }

    # Update existing or add new
    for i, c in enumerate(competitors):
        if c["id"] == profile["id"]:
            competitors[i].update(profile)
            _save_competitors(competitors)
            print(f"  🔄 已更新: {name} ({platform})")
            return competitors[i]

    competitors.append(profile)
    _save_competitors(competitors)
    print(f"  ➕ 已添加: {name} ({platform})")
    return profile


def list_competitors() -> list[dict]:
    """List all tracked competitors."""
    return _load_competitors()


# ═══════════════════════════════════════════════════════════════
# Analysis — extract patterns from competitor data
# ═══════════════════════════════════════════════════════════════

COMPETITIVE_ANALYSIS_PROMPT = """You are a competitive intelligence analyst for an AI news content creator.

Analyze the following competitors and their recent content. For each competitor, identify:

1. **Content mix** — What topics do they cover? What's their niche?
2. **Posting cadence** — How often do they post? Any patterns (day of week, time)?
3. **Hook style** — How do they structure their titles/hooks? What patterns repeat?
4. **Engagement drivers** — What content types get the most interaction?
5. **Weakness / gap** — What are they NOT covering that we could?

Competitor data:
{competitor_data}

Return a JSON array (one per competitor):
[
  {{"name": "...", "platform": "...",
    "content_mix": ["topic1", "topic2"],
    "cadence": "weekly|daily|irregular",
    "hook_style": "...",
    "top_performer": "what works best for them",
    "gap": "what they're missing",
    "threat_level": "low|medium|high",
    "actionable": "one thing we should do in response"
  }}
]
"""


def analyze_competitors() -> str | None:
    """Analyze all tracked competitors using Claude. Returns Markdown report."""
    competitors = _load_competitors()
    if not competitors:
        print("  [competitive] no competitors tracked yet")
        return None

    print(f"  [competitive] analyzing {len(competitors)} competitors...")

    # Format competitor data for the prompt
    comp_lines = []
    for c in competitors:
        comp_lines.append(
            f"- {c['name']} ({c['platform']}): {c.get('niche', 'AI content')}\n"
            f"  URL: {c.get('url', '')}\n"
            f"  Posts tracked: {c.get('post_count', 0)}\n"
            f"  Avg engagement: {c.get('avg_engagement', 0)}\n"
            f"  Top topics: {c.get('top_topics', [])}\n"
        )

    prompt = COMPETITIVE_ANALYSIS_PROMPT.replace("{competitor_data}", "\n".join(comp_lines))

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from claude_utils import call_claude, parse_json_lenient

    raw = call_claude(prompt, "", max_tokens=4096)
    if not raw:
        return None

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, list):
        return None

    # Generate Markdown report
    today_str = date.today().isoformat()
    lines = [
        f"# 竞品分析报告 — {today_str}",
        f"\n分析了 {len(parsed)} 个竞品账号。\n",
    ]

    for i, comp in enumerate(parsed, 1):
        threat_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴"}.get(
            comp.get("threat_level", "low"), "⚪"
        )
        lines.append(f"## {i}. {comp.get('name', '?')} ({comp.get('platform', '?')}) {threat_emoji}")
        lines.append(f"\n**内容方向**: {', '.join(comp.get('content_mix', []))}")
        lines.append(f"\n**发布节奏**: {comp.get('cadence', '?')}")
        lines.append(f"\n**标题风格**: {comp.get('hook_style', '?')}")
        lines.append(f"\n**爆款模式**: {comp.get('top_performer', '?')}")
        lines.append(f"\n**内容缺口**: {comp.get('gap', '?')}")
        lines.append(f"\n**应对建议**: {comp.get('actionable', '?')}")
        lines.append("")

    report = "\n".join(lines)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / f"competitive-report-{today_str}.md"
    report_path.write_text(report, encoding="utf-8")
    print(f"  [competitive] report saved: {report_path}")

    return report


# ═══════════════════════════════════════════════════════════════
# Quick scan — check competitor recent posts
# ═══════════════════════════════════════════════════════════════

def quick_scan(brand_id: str | None = None) -> dict:
    """Quick scan of competitor landscape for a specific brand context.

    Returns a summary dict with: total_competitors, platforms, niches, report_path
    """
    competitors = _load_competitors()
    if not competitors:
        return {"total_competitors": 0}

    platforms = {}
    niches = {}
    for c in competitors:
        plat = c.get("platform", "unknown")
        platforms[plat] = platforms.get(plat, 0) + 1
        for topic in c.get("top_topics", []):
            niches[topic] = niches.get(topic, 0) + 1

    return {
        "total_competitors": len(competitors),
        "platforms": platforms,
        "niches": dict(sorted(niches.items(), key=lambda x: x[1], reverse=True)[:10]),
        "active_tracking": sum(1 for c in competitors if c.get("avg_engagement", 0) > 0),
    }


# ═══════════════════════════════════════════════════════════════
# Pattern extraction — what can we learn?
# ═══════════════════════════════════════════════════════════════

def extract_patterns() -> dict:
    """Extract actionable patterns from competitor data (no Claude needed)."""
    competitors = _load_competitors()
    patterns = {
        "publishing_days": {},
        "common_topics": {},
        "platforms_used": {},
        "high_engagement_niches": [],
    }

    for c in competitors:
        plat = c.get("platform", "?")
        patterns["platforms_used"][plat] = patterns["platforms_used"].get(plat, 0) + 1

        if c.get("avg_engagement", 0) > 0.05:
            patterns["high_engagement_niches"].append({
                "name": c["name"],
                "platform": plat,
                "niche": c.get("niche", ""),
                "avg_engagement": c["avg_engagement"],
            })

        for topic in c.get("top_topics", []):
            patterns["common_topics"][topic] = patterns["common_topics"].get(topic, 0) + 1

    patterns["common_topics"] = dict(
        sorted(patterns["common_topics"].items(), key=lambda x: x[1], reverse=True)
    )
    patterns["high_engagement_niches"].sort(
        key=lambda x: x["avg_engagement"], reverse=True
    )

    return patterns


# ═══════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    if "--add" in sys.argv:
        idx = sys.argv.index("--add")
        if idx + 3 < len(sys.argv):
            platform = sys.argv[idx + 1]
            name = sys.argv[idx + 2]
            url = sys.argv[idx + 3]
            niche = sys.argv[idx + 4] if idx + 4 < len(sys.argv) else ""
            add_competitor(platform, name, url, niche)
        else:
            print("  Usage: --add <platform> <name> <url> [niche]")
    elif "--list" in sys.argv:
        competitors = list_competitors()
        if competitors:
            print(f"\n  🔍 追踪 {len(competitors)} 个竞品:")
            print(f"  {'─' * 55}")
            for c in competitors:
                plat = c.get("platform", "?")
                name = c.get("name", "?")
                niche = c.get("niche", "")
                posts = c.get("post_count", 0)
                eng = c.get("avg_engagement", 0)
                print(
                    f"  [{plat:<12}] {name:<20} {niche:<15} "
                    f"posts:{posts:<4} eng:{eng:.1%}"
                )
        else:
            print("  暂无竞品数据。用 --add 添加。")
    elif "--analyze" in sys.argv:
        report = analyze_competitors()
        if report:
            print(report)
    elif "--report" in sys.argv:
        summary = quick_scan()
        print(f"\n  竞品概览: {summary.get('total_competitors', 0)} 个账号")
        print(f"  平台分布: {summary.get('platforms', {})}")
        print(f"  热门话题: {list(summary.get('niches', {}).keys())[:5]}")
        print(f"  活跃追踪: {summary.get('active_tracking', 0)}")
    elif "--patterns" in sys.argv:
        patterns = extract_patterns()
        print(f"\n  📊 竞品模式分析:")
        print(f"  平台分布: {patterns.get('platforms_used', {})}")
        print(f"  高频话题: {list(patterns.get('common_topics', {}).keys())[:5]}")
        print(f"  高互动niche: {len(patterns.get('high_engagement_niches', []))}个")
    else:
        print(__doc__)
