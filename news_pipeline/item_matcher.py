#!/usr/bin/env python3
"""Curate top AI news from all sources (email + web) into xiaobai card items.

Single Claude call picks the best 4 items across all sources, formatted
in beginner-friendly Chinese for Xiaohongshu publishing.
"""

from __future__ import annotations

import random
import sys
from datetime import date
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_utils import call_claude, parse_json_lenient

CURATE_PROMPT = """You are an AI news curator for Chinese Xiaohongshu readers. Today's date is {today}.

You will receive TWO sources of AI news:
1. A translated AI newsletter (from Substack) — the email itself is from the last 24h
2. Web search snippets from Bing, ArXiv, Hacker News, Twitter

Your task: pick the BEST 4 AI news items from ALL sources combined.

CRITICAL — TIMELINESS RULES:
- ONLY pick news that happened in the last 24 hours (since yesterday)
- Skip anything older than 24h, even if interesting
- The email newsletter is from the last 24h, so items from it are timely
- For web sources, check the date/snippet — if it mentions a date older than yesterday, SKIP it
- ArXiv papers from today or yesterday are OK
- If you're unsure about recency, skip it

Other rules:
- Prioritize impact and beginner-friendliness
- Mix sources: don't take all 4 from the newsletter

Each item must be RICH in detail, suitable for a standalone Xiaohongshu card:

- title: catchy Chinese headline, 10-20 chars, Xiaohongshu vibe
- summary: 2-3 sentences explaining WHAT happened in plain language — use analogies, avoid jargon
- detail: 3-4 sentences with MORE context — who built it, why now, how it works, what's the big deal. Add concrete numbers (parameters, price, speed, date) when available.
- why_care: 2 sentences on real-world impact — who benefits, what changes for ordinary people
- key_points: 3 bullet points for beginners to remember (each 15-25 chars, simple and memorable)
- emoji: one relevant emoji character
- source_note: short note like "来自 AI Newsletter" or "来自 ArXiv 最新论文"

Return ONLY a JSON array (no markdown, no explanation):
[
  {"title": "...", "summary": "...", "detail": "...", "why_care": "...", "key_points": ["...", "...", "..."], "emoji": "...", "source_note": "..."},
  ...exactly 4 items
]

IMPORTANT:
- Return EXACTLY 4 items — no more, no less
- Write in simple, conversational Chinese
- detail field must be substantial (3-4 full sentences)
- Include concrete numbers/dates when available
- Avoid duplicate topics
- ONLY pick from the last 24 hours
"""


def curate_from_all_sources(
    translated_text: str, web_items: list[dict]
) -> list[dict[str, str]]:
    """Pick the 4 best AI news items from email + web sources combined.

    Args:
        translated_text: translated email content
        web_items: list of dicts from scrape_broad_ai_news()

    Returns:
        list of 4 NewsItem dicts: {title, summary, why_care, emoji, source_note, source_type}
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
        f"# AI Newsletter (translated)\n\n{translated_text[:4000]}\n\n"
        f"# Web Sources\n\n{web_text[:8000]}"
    )

    today_str = date.today().strftime("%Y年%m月%d日")
    prompt = CURATE_PROMPT.replace("{today}", today_str)
    raw = call_claude(prompt, user_text, max_tokens=8192)
    if not raw:
        print("  [curator] Claude call failed, falling back to email-only")
        return _fallback_curate(translated_text)

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, list):
        print(f"  [curator] unexpected response, raw: {raw[:200]}")
        return _fallback_curate(translated_text)

    items: list[dict[str, str]] = []
    for item in parsed[:4]:
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

    if len(items) < 4:
        # Pad with fallback
        extra = _fallback_curate(translated_text)
        needed = 4 - len(items)
        items.extend(extra[:needed])

    print(f"  [curator] selected {len(items)} items")
    return items[:4]


def _fallback_curate(translated_text: str) -> list[dict[str, str]]:
    """Extract items from email only as fallback."""
    prompt = """Extract 4 key AI news stories from this newsletter into
beginner-friendly Chinese with rich detail. Return JSON array:
[{"title": "...", "summary": "2-3 sentences what happened", "detail": "3-4 sentences with deeper context and numbers", "why_care": "...", "key_points": ["...", "...", "..."], "emoji": "...", "source_note": "来自 AI Newsletter"}]"""

    raw = call_claude(prompt, translated_text[:4000], max_tokens=4096)
    if not raw:
        return []

    parsed = parse_json_lenient(raw)
    if not parsed or not isinstance(parsed, list):
        return []

    items: list[dict[str, str]] = []
    for item in parsed:
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
    return items[:4]


def format_confirmation_prompt(
    ai_items: list[dict[str, str]], github_items: list[dict[str, str]]
) -> str:
    """Format 4 AI + N GitHub items for terminal confirmation."""
    lines = []
    lines.append(f"\n{'=' * 60}")
    lines.append(f"  🤖 AI 新闻 ({len(ai_items)}条) + ⭐ GitHub 开源项目 ({len(github_items)}条)")
    lines.append(f"{'=' * 60}")

    for i, item in enumerate(ai_items, 1):
        emoji = item.get("emoji", "📌")
        title = item.get("title", "")
        source = item.get("source_note", "")
        lines.append(f"\n  [{i}] {emoji} {title}")
        lines.append(f"      📍 {source}")
        summary = item.get("summary", "")
        if summary:
            lines.append(f"      {summary[:120]}")

    if github_items:
        lines.append(f"\n  {'─' * 56}")
        lines.append(f"  ⭐ GitHub Trending")
        lines.append(f"  {'─' * 56}")
        offset = len(ai_items)
        for i, item in enumerate(github_items, 1):
            emoji = item.get("emoji", "⭐")
            title = item.get("title", "")
            excerpt = item.get("raw_excerpt", "")
            lines.append(f"\n  [{offset + i}] {emoji} {title}")
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
