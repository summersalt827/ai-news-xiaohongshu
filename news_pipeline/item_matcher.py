#!/usr/bin/env python3
"""Curate top AI news from all sources (email + web) into xiaobai card items.

Weekly mode (default): picks 6-8 best items from the last 7 days across all sources,
organized by category for Xiaohongshu publishing.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_utils import call_claude, parse_json_lenient

CURATE_PROMPT = """You are an AI news curator for Chinese Xiaohongshu readers. Today's date is {today}.

You will receive TWO sources of AI news:
1. Translated AI newsletters (from Substack) — covering the last 7 days
2. Web search snippets from Bing, ArXiv, Hacker News, Twitter

Your task: pick the BEST 6-8 AI news items from the last 7 days.

TIMELINESS RULES:
- Pick news from the last 7 days (since {week_ago})
- Skip anything older than 7 days
- Prioritize items with the most real-world impact

CATEGORY DISTRIBUTION (aim for this balance):
- 模型与研究 (Model & Research): 2-3 items — new models, benchmarks, papers, training techniques
- 产品与工具 (Product & Tools): 2 items — new AI products, features, developer tools, apps
- 行业与政策 (Industry & Policy): 1-2 items — funding, regulation, company moves, AI safety

Other rules:
- Prioritize impact and beginner-friendliness
- Mix sources: don't take all from the newsletter
- Avoid duplicate topics

Each item must be RICH in detail, suitable for a standalone Xiaohongshu card:

- category: one of "模型与研究", "产品与工具", "行业与政策"
- title: catchy Chinese headline, 10-20 chars, Xiaohongshu vibe
- summary: 2-3 sentences explaining WHAT happened in plain language — use analogies, avoid jargon
- detail: 3-4 sentences with MORE context — who built it, why now, how it works, what's the big deal. Add concrete numbers (parameters, price, speed, date) when available.
- why_care: 2 sentences on real-world impact — who benefits, what changes for ordinary people
- key_points: 3 bullet points for beginners to remember (each 15-25 chars, simple and memorable)
- emoji: one relevant emoji character
- source_note: short note like "来自 AI Newsletter" or "来自 ArXiv 最新论文"

Return ONLY a JSON array (no markdown, no explanation):
[
  {{"category": "...", "title": "...", "summary": "...", "detail": "...", "why_care": "...", "key_points": ["...", "...", "..."], "emoji": "...", "source_note": "..."}},
  ...6 to 8 items
]

IMPORTANT:
- Return 6-8 items (not 4)
- Write in simple, conversational Chinese
- detail field must be substantial (3-4 full sentences)
- Include concrete numbers/dates when available
- Avoid duplicate topics
- Follow the category distribution above
"""


def curate_from_all_sources(
    translated_text: str, web_items: list[dict]
) -> list[dict[str, str]]:
    """Pick 6-8 best AI news items from the last 7 days across all sources.

    Args:
        translated_text: translated email content
        web_items: list of dicts from scrape_broad_ai_news()

    Returns:
        list of 6-8 NewsItem dicts
    """
    # Format web items for the prompt
    web_lines = []
    for i, item in enumerate(web_items, 1):
        title = item.get("title", "")[:120]
        snippet = item.get("snippet", "")[:200]
        src = item.get("source", "web")
        web_lines.append(f"{i}. [{src}] {title}\n   {snippet}\n")
    web_text = "\n".join(web_lines)

    user_text = (
        f"# AI Newsletter (translated)\n\n{translated_text[:6000]}\n\n"
        f"# Web Sources\n\n{web_text[:10000]}"
    )

    today = date.today()
    today_str = today.strftime("%Y年%m月%d日")
    week_ago = (today - timedelta(days=7)).strftime("%Y年%m月%d日")
    prompt = CURATE_PROMPT.replace("{today}", today_str).replace("{week_ago}", week_ago)

    raw = call_claude(prompt, user_text, max_tokens=8192)
    if not raw:
        print("  [curator] Claude call failed, falling back to email-only")
        return _fallback_curate(translated_text)

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, list):
        print(f"  [curator] unexpected response, raw: {raw[:200]}")
        return _fallback_curate(translated_text)

    items: list[dict[str, str]] = []
    for item in parsed:
        item.setdefault("category", "")
        item.setdefault("title", "")
        item.setdefault("summary", "")
        item.setdefault("detail", item.get("summary", ""))
        item.setdefault("why_care", "")
        item.setdefault("key_points", [])
        item.setdefault("emoji", "📌")
        item.setdefault("source_note", "来自全网精选")
        item.setdefault("source_type", "curated")
        if item["title"].strip():
            items.append(item)

    # Weekly: aim for 6-8 items
    target = 8
    if len(items) < 6:
        extra = _fallback_curate(translated_text)
        needed = 6 - len(items)
        items.extend(extra[:needed])

    print(f"  [curator] selected {len(items)} items")
    return items[:target]


def _fallback_curate(translated_text: str) -> list[dict[str, str]]:
    """Extract items from email only as fallback."""
    today = date.today()
    week_ago = (today - timedelta(days=7)).strftime("%Y年%m月%d日")
    prompt = f"""Extract 6-8 key AI news stories from this newsletter into
beginner-friendly Chinese with rich detail. Pick from the last 7 days (since {week_ago}).
Return JSON array:
[{{"category": "模型与研究|产品与工具|行业与政策", "title": "...", "summary": "2-3 sentences what happened", "detail": "3-4 sentences with deeper context and numbers", "why_care": "...", "key_points": ["...", "...", "..."], "emoji": "...", "source_note": "来自 AI Newsletter"}}]"""

    raw = call_claude(prompt, translated_text[:6000], max_tokens=8192)
    if not raw:
        return []

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, list):
        return []

    items: list[dict[str, str]] = []
    for item in parsed:
        item.setdefault("category", "")
        item.setdefault("title", "")
        item.setdefault("summary", "")
        item.setdefault("detail", item.get("summary", ""))
        item.setdefault("why_care", "")
        item.setdefault("key_points", [])
        item.setdefault("emoji", "📌")
        item.setdefault("source_note", "来自 AI Newsletter")
        item.setdefault("source_type", "curated")
        if item["title"].strip():
            items.append(item)
    return items[:8]


def format_confirmation_prompt(
    ai_items: list[dict[str, str]], github_items: list[dict[str, str]]
) -> str:
    """Format AI + GitHub items for terminal confirmation."""
    lines = []
    lines.append(f"\n{'=' * 60}")
    lines.append(f"  🤖 AI 新闻周报 ({len(ai_items)}条) + ⭐ GitHub 开源 ({len(github_items)}条)")
    lines.append(f"{'=' * 60}")

    # Group AI items by category
    cat_order = {"模型与研究": 0, "产品与工具": 1, "行业与政策": 2}
    by_cat: dict[str, list] = {}
    for item in ai_items:
        cat = item.get("category", "行业与政策")
        by_cat.setdefault(cat, []).append(item)

    idx = 0
    for cat in ["模型与研究", "产品与工具", "行业与政策"]:
        cat_items = by_cat.get(cat, [])
        if not cat_items:
            continue
        lines.append(f"\n  ── {cat} ──")
        for item in cat_items:
            idx += 1
            emoji = item.get("emoji", "📌")
            title = item.get("title", "")
            source = item.get("source_note", "")
            lines.append(f"\n  [{idx}] {emoji} {title}")
            lines.append(f"      📍 {source}")
            summary = item.get("summary", "")
            if summary:
                lines.append(f"      {summary[:120]}")

    if github_items:
        lines.append(f"\n  {'─' * 56}")
        lines.append(f"  ⭐ GitHub Trending (本周)")
        lines.append(f"  {'─' * 56}")
        for item in github_items:
            idx += 1
            emoji = item.get("emoji", "⭐")
            title = item.get("title", "")
            excerpt = item.get("raw_excerpt", "")
            lines.append(f"\n  [{idx}] {emoji} {title}")
            if excerpt:
                lines.append(f"      {excerpt[:120]}")
            summary = item.get("summary", "")
            if summary:
                lines.append(f"      {summary[:120]}")

    lines.append(f"\n{'=' * 60}")
    lines.append("  Enter=全部确认  |  编号=移除(如: 2,5)  |  q=退出")
    lines.append(f"{'=' * 60}")
    return "\n".join(lines)


def parse_removals(cmd: str, total: int) -> set[int]:
    """Parse comma-separated removal indices from user input."""
    indices: set[int] = set()
    for part in cmd.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < total:
                indices.add(idx)
    return indices


# ═══════════════════════════════════════════════════════════════
# P1-2: Quality scoring — pre-publish virality check
# ═══════════════════════════════════════════════════════════════

SCORE_THRESHOLD = 28  # out of 40 — rewrite if below this

SCORE_PROMPT = """You are a Xiaohongshu content quality reviewer for an AI news account.

Score the following AI news card item on 4 dimensions (each 0-10):

1. **hook** — Does the title grab attention immediately? Is it punchy, specific, curiosity-driving?
2. **structure** — Is the summary clear for beginners? Are "what happened" / "dig deeper" / "why care" logically layered?
3. **cta** — Do the key_points end with a memorable takeaway that makes readers want to save/share?
4. **density** — Are there concrete numbers, dates, names, comparisons? Not just fluff.

Scoring guide:
- 8-10: Excellent, Xiaohongshu-ready
- 5-7: Decent but could be sharper
- 0-4: Weak, needs rewrite

Return ONLY a JSON object (no markdown, no explanation):
{"hook": N, "structure": N, "cta": N, "density": N, "total": N, "verdict": "ok"|"rewrite", "note": "one-line reason in Chinese"}
"""

REWRITE_PROMPT = """You are a Xiaohongshu content editor. Rewrite this AI news card to improve its quality.

Original item:
{original}

Issues to fix: {issues}

Make it:
- More punchy headline (10-20 chars, Xiaohongshu vibe)
- Beginner-friendly summary with concrete details
- Memorable key_points that feel like "aha moments"
- Add numbers, dates, names wherever possible

Return ONLY a JSON object with the same fields as the original:
{{"title": "...", "summary": "...", "detail": "...", "why_care": "...", "key_points": ["...", "..."], "emoji": "...", "source_note": "..."}}
"""


def score_item(item: dict) -> dict:
    """Score a single news item on 4 quality dimensions. Returns score dict."""
    title = item.get("title", "")
    summary = item.get("summary", "")
    detail = item.get("detail", "")
    why_care = item.get("why_care", "")

    user_text = (
        f"Title: {title}\n"
        f"Summary: {summary}\n"
        f"Detail: {detail}\n"
        f"Why care: {why_care}\n"
    )

    raw = call_claude(SCORE_PROMPT, user_text, max_tokens=512)
    if not raw:
        return {"hook": 5, "structure": 5, "cta": 5, "density": 5,
                "total": 20, "verdict": "ok", "note": "scoring failed, using default"}

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, dict):
        return {"hook": 5, "structure": 5, "cta": 5, "density": 5,
                "total": 20, "verdict": "ok", "note": "scoring parse failed"}

    total = (int(parsed.get("hook", 5)) + int(parsed.get("structure", 5)) +
             int(parsed.get("cta", 5)) + int(parsed.get("density", 5)))
    parsed["total"] = total
    parsed.setdefault("verdict", "rewrite" if total < SCORE_THRESHOLD else "ok")
    parsed.setdefault("note", "")
    return parsed


def rewrite_item(item: dict, score: dict) -> dict | None:
    """Rewrite a low-scoring item. Returns improved item or None on failure."""
    issues = score.get("note", "low quality score")
    original = (
        f"Title: {item.get('title', '')}\n"
        f"Summary: {item.get('summary', '')}\n"
        f"Detail: {item.get('detail', '')}\n"
        f"Why care: {item.get('why_care', '')}\n"
        f"Key points: {item.get('key_points', [])}\n"
    )
    prompt = REWRITE_PROMPT.replace("{original}", original).replace("{issues}", issues)

    raw = call_claude(prompt, "", max_tokens=4096)
    if not raw:
        return None

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, dict):
        return None

    for key in ("emoji", "source_note", "source_type", "category"):
        if key not in parsed and key in item:
            parsed[key] = item[key]

    return parsed


def score_and_rewrite(items: list[dict], max_rewrite_rounds: int = 2) -> list[dict]:
    """Score all items, rewrite those below threshold. Returns final item list.

    Each low-score item gets up to max_rewrite_rounds attempts.
    Prints a scoreboard to terminal.
    """
    if not items:
        return items

    print(f"\n  🎯 质量预判 — 评分 {len(items)} 条...")
    final_items: list[dict] = []
    scoreboard: list[tuple[str, int, str]] = []

    for i, item in enumerate(items):
        title = item.get("title", "?")
        score = score_item(item)
        total = score["total"]
        verdict = score["verdict"]

        rewrite_count = 0
        while verdict == "rewrite" and rewrite_count < max_rewrite_rounds:
            rewrite_count += 1
            print(f"    [{i+1}] 🔄 重写 ({total}/40): {title[:40]}")
            rewritten = rewrite_item(item, score)
            if rewritten:
                item = rewritten
                score = score_item(item)
                total = score["total"]
                verdict = score["verdict"]
            else:
                break

        item["_quality_score"] = score
        final_items.append(item)
        scoreboard.append((title, total, verdict))

    print(f"\n  {'─' * 52}")
    print(f"  {'#':<3} {'得分':<5} {'判定':<8} 标题")
    print(f"  {'─' * 52}")
    for i, (title, total, verdict) in enumerate(scoreboard, 1):
        icon = "✅" if verdict == "ok" else "⚠️"
        print(f"  {i:<3} {total:<5} {icon + ' ' + verdict:<8} {title[:40]}")
    print(f"  {'─' * 52}")
    avg = sum(s[1] for s in scoreboard) / len(scoreboard) if scoreboard else 0
    print(f"  平均分: {avg:.1f}/40\n")

    return final_items


# ═══════════════════════════════════════════════════════════════
# P1-3: Multi-platform caption generation
# ═══════════════════════════════════════════════════════════════

MULTI_CAPTION_PROMPT = """You are a social media editor. Given AI news items, write platform-optimized copy for each platform below.

Date: {date}
Number of items: {count}

Items:
{items}

Write copy for these platforms — keep it in a single JSON object:

1. **xiaohongshu** — Chinese, 小红书 style: emoji-rich, line-break heavy, warm tone, end with relevant hashtags (#AI新闻 #AI周报 etc)
2. **bilibili** — Chinese, B站 video description: longer, include chapter markers, mention "4K画质" and "设计文档风", 3-5 hashtags
3. **twitter** — Chinese + key English terms, X/Twitter thread style: 3 numbered tweets, punchy, include key stats/numbers
4. **newsletter** — Chinese, email newsletter style: professional but friendly, brief intro + bullet points of this week's highlights

Return ONLY a JSON object (no markdown):
{{"xiaohongshu": "...", "bilibili": "...", "twitter": "...", "newsletter": "..."}}
"""


def generate_multi_platform_captions(
    items: list[dict], date_str: str
) -> dict[str, str]:
    """Generate platform-specific captions for all items.

    Returns dict with keys: xiaohongshu, bilibili, twitter, newsletter
    """
    if not items:
        return {}

    # Format items for the prompt
    item_lines = []
    for i, item in enumerate(items, 1):
        item_lines.append(
            f"[{i}] {item.get('emoji', '')} {item.get('title', '')}\n"
            f"    {item.get('summary', '')}\n"
            f"    Key points: {item.get('key_points', [])}\n"
        )
    items_text = "\n".join(item_lines)

    prompt = (
        MULTI_CAPTION_PROMPT
        .replace("{date}", date_str)
        .replace("{count}", str(len(items)))
        .replace("{items}", items_text)
    )

    raw = call_claude(prompt, "", max_tokens=4096)
    if not raw:
        return {}

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, dict):
        return {}

    return {
        "xiaohongshu": parsed.get("xiaohongshu", ""),
        "bilibili": parsed.get("bilibili", ""),
        "twitter": parsed.get("twitter", ""),
        "newsletter": parsed.get("newsletter", ""),
    }
