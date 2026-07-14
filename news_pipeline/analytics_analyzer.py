#!/usr/bin/env python3
"""AI-powered analytics analyzer — reads collected XHS data, generates optimization report.

Usage:
  python3 news_pipeline/analytics_analyzer.py                    # analyze all available data
  python3 news_pipeline/analytics_analyzer.py --weeks 2          # analyze last 2 weeks
  python3 news_pipeline/analytics_analyzer.py --update-preferences # also update preferences.md

Output: xiaohongshu/analytics/report-YYYY-WXX.md
"""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
ANALYTICS_DIR = PROJECT_DIR / "xiaohongshu" / "analytics"
PREFERENCES_PATH = PROJECT_DIR / ".claude" / "preferences.md"

ANALYSIS_PROMPT = """你是一个内容策略分析师。以下是 AI 新闻自媒体「AI 速览」在小红书的发布数据。

请从以下几个维度分析，用中文输出 Markdown 格式报告：

## 选题表现排名
按选题类型排名，列出平均互动率（(点赞+收藏+评论)/阅读量）。

## 选题建议
基于数据，下一周应该：
- 多选什么类型的话题？
- 少选或不选什么类型？
- GitHub 项目类的比例是否要调整？

## 标题优化
什么样的标题形式效果好？（带数字、带问号、直述句等）

## 发布时间建议
哪天发效果好？什么时段？

## 趋势变化
对比上期数据，上升/下降的指标有哪些？

## 一句话周报总结
一句话概括本周数据表现。

---

输出格式要求：
1. 用 ## 做章节标题
2. 建议部分用「✅ 继续」「⬆️ 增加」「⬇️ 减少」「🆕 尝试」标注
3. 最后输出一个 `PREFERENCES_UPDATE` 代码块，内容是更新到 .claude/preferences.md 的「本周选题偏好」部分
   - 格式为 Markdown 列表，每条一个偏好规则
   - 不要包含其他内容，只要列表

---

以下是收集到的数据：
"""


def _load_analytics_data(weeks: int = 4) -> list[dict]:
    """Load all analytics JSON files from the last N weeks."""
    if not ANALYTICS_DIR.exists():
        return []

    cutoff = date.today() - timedelta(weeks=weeks)
    files = sorted(ANALYTICS_DIR.glob("*.json"))
    data = []
    for f in files:
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
            fetch_date = raw.get("fetch_date", "")
            if fetch_date:
                d = date.fromisoformat(fetch_date)
                if d >= cutoff:
                    data.append(raw)
        except Exception:
            continue
    return data


def _summarize_for_claude(analytics_data: list[dict]) -> str:
    """Convert raw analytics data into a compact summary for Claude analysis."""
    parts = []
    parts.append(f"共 {len(analytics_data)} 天数据\n")

    for entry in analytics_data:
        parts.append(f"--- 日期: {entry.get('fetch_date', 'unknown')} ---")
        data = entry.get("data", {})

        if isinstance(data, dict):
            posts = data.get("posts", data.get("notes", data.get("list", [])))
            if isinstance(posts, list):
                for p in posts[:20]:
                    if isinstance(p, dict):
                        parts.append(
                            f"  - {p.get('title', p.get('display_title', '?'))[:60]} "
                            f"| 阅读:{p.get('views', p.get('view_count', '?'))} "
                            f"| 点赞:{p.get('likes', p.get('like_count', '?'))} "
                            f"| 收藏:{p.get('saves', p.get('collect_count', '?'))} "
                            f"| 评论:{p.get('comments', p.get('comment_count', '?'))} "
                            f"| 分享:{p.get('shares', p.get('share_count', '?'))}"
                        )
            else:
                parts.append(json.dumps(data, ensure_ascii=False, indent=2)[:3000])
        else:
            parts.append(str(data)[:3000])

    return "\n".join(parts)


def run_analysis(weeks: int = 2, update_preferences: bool = False) -> str | None:
    """Run Claude-powered analytics analysis.

    Returns the markdown report string, or None on failure.
    """
    data = _load_analytics_data(weeks)
    if not data:
        print("[analyzer] no analytics data found. Run analytics.py first.")
        return None

    print(f"[analyzer] loaded {len(data)} days of analytics data")

    summary = _summarize_for_claude(data)
    if len(summary) < 100:
        print("[analyzer] not enough data for meaningful analysis")
        return None

    # Call Claude for analysis
    from news_pipeline.claude_utils import call_claude

    user_text = ANALYSIS_PROMPT + "\n" + summary
    response = call_claude("", user_text, max_tokens=4096, timeout=180)

    if not response:
        print("[analyzer] Claude call failed")
        return None

    # Determine week label for filename
    today = date.today()
    year, week_num, _ = today.isocalendar()
    week_label = f"{year}-W{week_num:02d}"

    report_path = ANALYTICS_DIR / f"report-{week_label}.md"
    report_path.write_text(response, encoding="utf-8")
    print(f"[analyzer] report saved to {report_path}")

    # Extract PREFERENCES_UPDATE block if present
    if update_preferences and "PREFERENCES_UPDATE" in response:
        _apply_preferences_update(response)

    return response


def _apply_preferences_update(report: str):
    """Extract PREFERENCES_UPDATE block from report and merge into preferences.md."""
    import re

    match = re.search(
        r"```PREFERENCES_UPDATE\s*\n(.*?)```", report, re.DOTALL
    )
    if not match:
        print("[analyzer] no PREFERENCES_UPDATE block found in report")
        return

    update_content = match.group(1).strip()
    if not update_content:
        return

    # Read existing preferences
    existing = ""
    if PREFERENCES_PATH.exists():
        existing = PREFERENCES_PATH.read_text(encoding="utf-8")

    # Replace or append the weekly preferences section
    section_header = "## 本周选题偏好"
    new_date = date.today().isoformat()
    new_section = f"{section_header}（AI 自动更新于 {new_date}）\n{update_content}"

    if section_header in existing:
        # Replace existing section
        parts = re.split(rf"^{section_header}.*$", existing, flags=re.MULTILINE)
        if len(parts) >= 2:
            # Find end of section (next ## header or EOF)
            rest = parts[1]
            next_section = re.search(r"^## ", rest, re.MULTILINE)
            if next_section:
                existing = parts[0] + new_section + "\n\n" + rest[next_section.start():]
            else:
                existing = parts[0] + new_section + "\n"
    else:
        existing = existing.rstrip() + "\n\n" + new_section + "\n"

    PREFERENCES_PATH.write_text(existing, encoding="utf-8")
    print(f"[analyzer] preferences.md updated with new content preferences")


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="AI analytics analyzer")
    parser.add_argument("--weeks", type=int, default=2, help="weeks of data to analyze")
    parser.add_argument(
        "--update-preferences", action="store_true",
        help="update .claude/preferences.md with recommendations",
    )
    args = parser.parse_args()

    report = run_analysis(weeks=args.weeks, update_preferences=args.update_preferences)
    if report:
        print(report)
    else:
        print("Analysis failed", file=sys.stderr)
        sys.exit(1)
