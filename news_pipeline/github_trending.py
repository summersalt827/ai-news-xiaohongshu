#!/usr/bin/env python3
"""Fetch trending GitHub repositories created in the last 24 hours.

Uses GitHub Search API to find repos with highest star count among
recently created projects, then distills them into xiaobai card format.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from claude_utils import call_claude, parse_json_lenient

os.environ.setdefault("no_proxy", "*")

DISTILL_PROMPT = """You are a curator for Chinese Xiaohongshu readers. Below is a list of
GitHub repositories that are trending (fastest star growth in 24 hours).

For the TOP repository, write a DETAILED card:
1. title: catchy Chinese headline, 10-20 chars, Xiaohongshu style
2. summary: 4-5 sentences explaining:
   - What this project does (in simple Chinese, use analogies)
   - What specific problem it solves
   - Who would find it useful
   - How to get started (briefly)
3. why_care: 2 sentences on why ordinary people should care, practical use cases
4. emoji: one relevant emoji
5. raw_excerpt: "⭐ stars: X | 🔧 language: Y | 📦 project: owner/name"

Return ONLY a JSON array with 1 item (the best repo):
[{"title": "...", "summary": "...", "why_care": "...", "emoji": "...", "raw_excerpt": "..."}]"""


def _fetch_github_trending_raw() -> list[dict]:
    """Fetch repos created in last 24h with most stars from GitHub Search API."""
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    # GitHub search: repos created since yesterday, sorted by stars
    query = f"created:>={yesterday} stars:>=3"
    url = (
        f"https://api.github.com/search/repositories"
        f"?q={urllib.request.quote(query)}"
        f"&sort=stars&order=desc&per_page=10"
    )

    token = os.environ.get("GITHUB_TOKEN", "")
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "ai-news-fetcher/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    req = urllib.request.Request(url, headers=headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [github] Search API failed: {exc}")
        return []

    repos: list[dict] = []
    for item in body.get("items", []):
        repos.append({
            "full_name": item.get("full_name", ""),
            "description": item.get("description") or "",
            "stars": item.get("stargazers_count", 0),
            "language": item.get("language") or "unknown",
            "url": item.get("html_url", ""),
            "created_at": item.get("created_at", ""),
            "topics": item.get("topics", []),
        })

    return repos


def _fetch_ossinsight_trending() -> list[dict]:
    """Fallback: fetch trending repos from ossinsight.io API.

    Returns list of dicts compatible with _fetch_github_trending_raw.
    """
    try:
        url = (
            "https://api.ossinsight.io/v1/collections/trending_repo"
            "?period=past_24_hours&limit=10"
        )
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ai-news-fetcher/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [github] ossinsight fetch failed: {exc}")
        return []

    repos: list[dict] = []
    for item in body.get("data", []):
        repo = item.get("repo", {})
        repos.append({
            "full_name": repo.get("name", ""),
            "description": repo.get("description") or "",
            "stars": repo.get("stars", 0),
            "language": repo.get("language") or "unknown",
            "url": f"https://github.com/{repo.get('name', '')}",
            "created_at": "",
            "topics": [],
        })
    return repos


def fetch_trending_repos() -> list[dict]:
    """Main entry: fetch trending repos from GitHub + ossinsight fallback.

    Returns list of dicts with: full_name, description, stars, language, url
    """
    repos = _fetch_github_trending_raw()

    if not repos:
        print("  [github] GitHub API returned 0 results, trying ossinsight...")
        repos = _fetch_ossinsight_trending()
        if not repos:
            print("  [github] ossinsight also returned 0 results")

    # Deduplicate by full_name
    seen: set[str] = set()
    unique: list[dict] = []
    for r in repos:
        if r["full_name"] and r["full_name"] not in seen:
            seen.add(r["full_name"])
            unique.append(r)

    print(f"  [github] {len(unique)} unique trending repos")
    return unique[:8]


def format_github_for_claude(repos: list[dict]) -> str:
    """Format repos list as readable text for Claude distillation."""
    lines = []
    for i, r in enumerate(repos, 1):
        stars = f"{r['stars']:,}" if isinstance(r["stars"], int) else str(r["stars"])
        lines.append(
            f"{i}. **{r['full_name']}**\n"
            f"   ⭐ {stars} stars  |  Language: {r['language']}\n"
            f"   {r['description'][:300]}\n"
            f"   URL: {r['url']}\n"
        )
    return "\n".join(lines)


def distill_github_items(repos: list[dict]) -> list[dict[str, str]]:
    """Distill trending repos into xiaobai card items via Claude.

    Returns list of NewsItem dicts with source_type="github".
    """
    if not repos:
        return []

    repos_text = format_github_for_claude(repos)

    raw = call_claude(DISTILL_PROMPT, repos_text, max_tokens=4096)
    if not raw:
        print("  [github] distillation failed, using raw data")
        return _fallback_github_items(repos)

    parsed = parse_json_lenient(raw)
    if not parsed:
        print(f"  [github] JSON parse failed, using fallback. Raw: {raw[:200]}")
        return _fallback_github_items(repos)

    items: list[dict[str, str]] = []
    for item in parsed:
        item["source_type"] = "github"
        item.setdefault("title", "")
        item.setdefault("summary", "")
        item.setdefault("why_care", "")
        item.setdefault("emoji", "⭐")
        item.setdefault("raw_excerpt", "")
        if item["title"].strip():
            items.append(item)

    return items[:1]


def _fallback_github_items(repos: list[dict]) -> list[dict[str, str]]:
    """Generate basic items from repo data without Claude."""
    items: list[dict[str, str]] = []
    for r in repos[:5]:
        name = r["full_name"]
        desc = (r.get("description") or "No description")[:200]
        stars = f"{r['stars']:,}" if isinstance(r["stars"], int) else str(r["stars"])
        language = r.get("language", "unknown")

        items.append({
            "source_type": "github",
            "title": name.split("/")[-1] if "/" in name else name,
            "summary": desc,
            "why_care": f'GitHub 上最近很火的开源项目，{stars} 人已收藏',
            "emoji": "⭐",
            "raw_excerpt": f"⭐ {stars} stars | Language: {language}",
        })
    return items


def pick_best_github(repos: list[dict]) -> list[dict[str, str]]:
    """Return exactly 1 best GitHub item, or empty list."""
    items = distill_github_items(repos)
    return items[:1]


def format_github_confirmation(items: list[dict[str, str]]) -> str:
    """Format GitHub items for terminal confirmation display."""
    lines = [f"\n{'─' * 58}"]
    lines.append(f"  ⭐ GitHub Trending (24h star增速最快) — {len(items)} 条")
    lines.append(f"{'─' * 58}")

    for i, item in enumerate(items, 1):
        emoji = item.get("emoji", "⭐")
        title = item.get("title", "")
        excerpt = item.get("raw_excerpt", "")[:100]
        lines.append(f"  [{i}] {emoji} {title}")
        if excerpt:
            lines.append(f"      {excerpt}")
        summary = item.get("summary", "")
        if summary:
            lines.append(f"      {summary[:120]}")

    lines.append(f"\n{'─' * 58}")
    lines.append("  Enter=全部确认  |  编号=移除该条 (如: 2,4)  |  q=取消GitHub部分")
    lines.append(f"{'─' * 58}")
    return "\n".join(lines)


if __name__ == "__main__":
    repos = fetch_trending_repos()
    print(f"\nFound {len(repos)} trending repos:")
    for r in repos:
        print(f"  {r['full_name']} — ⭐ {r['stars']} — {r['language']}")
