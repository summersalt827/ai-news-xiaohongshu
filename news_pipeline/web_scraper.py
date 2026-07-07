#!/usr/bin/env python3
"""Broad web scraping for AI news — independent of email content.

Sources:
  - Bing search (broad queries + source-specific)
  - Hacker News (Algolia API — free, no auth)
  - Reddit r/MachineLearning, r/artificial, r/singularity, r/LocalLLaMA
  - Twitter/X (via Nitter + Bing site:x.com fallback)
  - ArXiv cs.AI / cs.CL / cs.LG (API — free, no auth)
  - Official blogs: OpenAI, Anthropic, DeepMind, Meta, Mistral
  - Tech media: TechCrunch, The Verge, Ars Technica, Wired, VentureBeat
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
from datetime import date, timedelta
import urllib.request
import xml.etree.ElementTree as ET

os.environ.setdefault("no_proxy", "*")

# ── AI relevance keywords ─────────────────────────────────────

AI_RELEVANCE_KW = [
    "ai ", "artificial intelligence", "machine learning", "deep learning",
    "llm", "large language model", "gpt", "claude", "gemini", "openai",
    "anthropic", "deepseek", "qwen", "transformer model",
    "人工智能", "大模型", "深度学习", "机器学习",
    "agi", "ai agent", "copilot", "chatbot",
    "model release", "benchmark", "ai funding", "ai startup",
    "multimodal", "generative ai", "diffusion model",
    "大语言模型", "训练", "推理框架", "算力",
]

NON_AI_DOMAINS = {"iciba.com", "baike.baidu.com", "zhihu.com/question", "zhuanlan.zhihu.com"}

# ── Broad Bing search queries (date injected at runtime) ──────

def _get_broad_queries() -> list[str]:
    today = date.today()
    ds = today.strftime("%B %d %Y")  # e.g. June 18 2026
    ds_short = today.strftime("%B %Y")
    yesterday = (today - timedelta(days=1)).strftime("%B %d %Y")
    return [
        f"AI news today {ds}",
        f"AI news {yesterday}",
        f"latest AI breakthrough {ds_short}",
        f"new AI model release {ds}",
        f"AI startup funding news {today.year}",
        f"AI regulation policy update {today.year}",
        f"best new AI tools released {ds_short}",
        f"OpenAI Anthropic Google AI news {ds}",
    ]

def _get_source_queries() -> list[str]:
    today = date.today()
    ds = today.strftime("%B %Y")
    return [
        "site:techcrunch.com AI news",
        "site:theverge.com AI artificial intelligence",
        "site:arstechnica.com AI machine learning",
        "site:wired.com AI news",
        "site:venturebeat.com AI news",
        "site:openai.com blog release",
        "site:anthropic.com research blog",
        "site:deepmind.google blog AI",
        "site:ai.meta.com blog",
        "site:mistral.ai blog news",
    ]

# ── Shared request helper ─────────────────────────────────────

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def _clean_html(text: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&ensp;", " ", text)
    text = re.sub(r"&#\d+;", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    return text.strip()


# ═══════════════════════════════════════════════════════════════
# Source 1: Bing Search
# ═══════════════════════════════════════════════════════════════

def _search_bing(query: str, num_results: int = 3) -> list[dict]:
    """Search Bing and return structured results with title, snippet, url."""
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&setlang=en&mkt=en-US"
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [bing] search failed for '{query[:60]}': {exc}")
        return []

    results: list[dict] = []

    # Primary: extract b_algo result blocks
    algo_blocks = re.findall(
        r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>',
        html, re.DOTALL | re.IGNORECASE,
    )
    for block in algo_blocks:
        title_match = re.search(
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            block, re.DOTALL | re.IGNORECASE,
        )
        if not title_match:
            continue

        result_url = title_match.group(1)
        if "bing.com" in result_url or "microsoft.com/bing" in result_url:
            continue

        title = _clean_html(title_match.group(2))
        if len(title) < 10:
            continue

        snippet = ""
        snippet_match = re.search(
            r'<(?:p|div)[^>]*class="[^"]*?(?:b_lineclamp|b_caption|b_snippet)[^"]*"[^>]*>(.*?)</(?:p|div)>',
            block, re.DOTALL | re.IGNORECASE,
        )
        if snippet_match:
            snippet = _clean_html(snippet_match.group(1))
        else:
            p_match = re.search(r'<p[^>]*>(.*?)</p>', block, re.DOTALL)
            if p_match:
                snippet = _clean_html(p_match.group(1))

        # Inline filter
        skip_kw = ["dictionary", "wiki", "爱词霸", "wikipedia", "iciba", "baike"]
        if any(kw in title.lower() for kw in skip_kw):
            continue
        if any(kw in result_url.lower() for kw in skip_kw):
            continue
        url_lower = result_url.lower()
        if any(bad in url_lower for bad in NON_AI_DOMAINS):
            continue

        combined = f"{title} {snippet}".lower()
        if not any(kw in combined for kw in AI_RELEVANCE_KW):
            continue

        results.append({"title": title, "snippet": snippet or title, "url": result_url, "source": "bing"})

    # Fallback: h2+link
    if not results:
        for match in re.finditer(
            r'<h[23][^>]*>\s*<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            result_url = match.group(1)
            if "bing.com" in result_url:
                continue
            title = _clean_html(match.group(2))
            if len(title) > 10:
                results.append({"title": title, "snippet": title, "url": result_url, "source": "bing"})

    # Last resort: b_lineclamp snippets
    if not results:
        for match in re.finditer(
            r'<(?:p|div)[^>]*class="[^"]*?(?:b_lineclamp|b_caption|b_snippet)[^"]*"[^>]*>(.*?)</(?:p|div)>',
            html, re.DOTALL | re.IGNORECASE,
        ):
            text = _clean_html(match.group(1))
            if len(text) > 40:
                results.append({"title": text[:120], "snippet": text, "url": "", "source": "bing"})

    return results[:num_results]


# ═══════════════════════════════════════════════════════════════
# Source 2: Hacker News (Algolia API)
# ═══════════════════════════════════════════════════════════════

def _fetch_hackernews(query: str = "AI", hours_back: int = 48, limit: int = 10) -> list[dict]:
    """Search HN stories via Algolia API. Free, no auth required."""
    since_ts = int(time.time()) - hours_back * 3600
    url = (
        f"https://hn.algolia.com/api/v1/search_by_date"
        f"?query={urllib.parse.quote(query)}"
        f"&tags=story"
        f"&numericFilters=created_at_i%3E{since_ts}"
        f"&hitsPerPage={limit}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [hn] API failed: {exc}")
        return []

    results: list[dict] = []
    for hit in data.get("hits", []):
        title = hit.get("title", "")
        url_str = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
        points = hit.get("points", 0)
        comments = hit.get("num_comments", 0)

        if points < 5:  # skip low-signal posts
            continue

        results.append({
            "title": title,
            "snippet": f"👍 {points} pts | 💬 {comments} comments",
            "url": url_str,
            "source": "hackernews",
        })

    return results[:limit]


# ═══════════════════════════════════════════════════════════════
# Source 3: Reddit (JSON API)
# ═══════════════════════════════════════════════════════════════

_REDDIT_SUBREDDITS = [
    "MachineLearning",
    "artificial",
    "singularity",
    "LocalLLaMA",
]


def _fetch_reddit_subreddit(subreddit: str, limit: int = 8) -> list[dict]:
    """Fetch hot posts from a subreddit via Reddit JSON API. Free, no auth."""
    url = f"https://www.reddit.com/r/{subreddit}/hot.json?limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": f"ai-news-fetcher/1.0 ({_USER_AGENT})"})

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [reddit] r/{subreddit} failed: {exc}")
        return []

    results: list[dict] = []
    for child in data.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title", "")
        selftext = post.get("selftext", "")[:300]
        ups = post.get("ups", 0)
        comments = post.get("num_comments", 0)
        permalink = "https://www.reddit.com" + post.get("permalink", "")
        url_str = post.get("url", permalink)

        if ups < 10:  # skip low-signal
            continue

        snippet = selftext.strip() if selftext.strip() else title
        results.append({
            "title": title,
            "snippet": f"r/{subreddit} | 👍 {ups} | 💬 {comments} | {snippet[:150]}",
            "url": url_str if "reddit.com" not in url_str else permalink,
            "source": "reddit",
        })

    return results


def _fetch_reddit_ai() -> list[dict]:
    """Fetch AI-related posts from multiple subreddits."""
    all_results: list[dict] = []
    for sub in _REDDIT_SUBREDDITS:
        results = _fetch_reddit_subreddit(sub, limit=6)
        all_results.extend(results)
    return all_results


# ═══════════════════════════════════════════════════════════════
# Source 4: Twitter/X (via Nitter + Bing site:x.com fallback)
# ═══════════════════════════════════════════════════════════════

_NITTER_INSTANCES = [
    "https://nitter.net",
    "https://nitter.privacydev.net",
]


def _fetch_nitter(query: str = "AI news", limit: int = 8) -> list[dict]:
    """Search tweets via Nitter (Twitter mirror). No auth required."""
    for instance in _NITTER_INSTANCES:
        url = f"{instance}/search?f=tweets&q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except Exception:
            continue  # try next instance

        results: list[dict] = []
        # Nitter tweet containers: div.tweet-content, div.tweet-body
        tweet_blocks = re.findall(
            r'<div[^>]*class="[^"]*tweet-content[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html, re.DOTALL,
        )
        for block in tweet_blocks[:limit]:
            text = _clean_html(block)
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > 20:
                results.append({
                    "title": text[:120],
                    "snippet": text,
                    "url": f"{instance}/search?q={urllib.parse.quote(query)}",
                    "source": "twitter",
                })

        if results:
            return results

    return []


def _fetch_twitter_via_bing() -> list[dict]:
    """Fallback: search Twitter/X content via Bing site:x.com."""
    queries = [
        "site:x.com AI news today",
        "site:twitter.com AI news today",
        'site:x.com "AI" "model" release',
    ]
    results: list[dict] = []
    for q in queries:
        for item in _search_bing(q, num_results=3):
            item["source"] = "twitter"
            results.append(item)
    return results


def _fetch_twitter() -> list[dict]:
    """Try Nitter first, fall back to Bing site:x.com."""
    results = _fetch_nitter("AI news", limit=8)
    if not results:
        print("  [twitter] Nitter unavailable, falling back to Bing site:x.com")
        results = _fetch_twitter_via_bing()
    return results


# ═══════════════════════════════════════════════════════════════
# Source 5: ArXiv (API — free, no auth)
# ═══════════════════════════════════════════════════════════════

_ARXIV_CATEGORIES = ["cs.AI", "cs.CL", "cs.LG", "cs.CV"]


def _fetch_arxiv(max_results: int = 10) -> list[dict]:
    """Fetch latest AI papers from ArXiv API. Returns Atom XML, parsed here."""
    cats = "+OR+".join(f"cat:{c}" for c in _ARXIV_CATEGORIES)
    url = (
        f"http://export.arxiv.org/api/query"
        f"?search_query={cats}"
        f"&sortBy=submittedDate&sortOrder=descending"
        f"&max_results={max_results}"
    )

    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            xml_data = resp.read().decode("utf-8")
    except Exception as exc:
        print(f"  [arxiv] API failed: {exc}")
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    try:
        root = ET.fromstring(xml_data)
    except ET.ParseError as exc:
        print(f"  [arxiv] XML parse error: {exc}")
        return []

    results: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        title_el = entry.find("atom:title", ns)
        summary_el = entry.find("atom:summary", ns)
        url_el = entry.find("atom:id", ns)
        published_el = entry.find("atom:published", ns)

        title = title_el.text.strip() if title_el is not None and title_el.text else ""
        summary = summary_el.text.strip() if summary_el is not None and summary_el.text else ""
        paper_url = url_el.text.strip() if url_el is not None and url_el.text else ""
        published = published_el.text[:10] if published_el is not None and published_el.text else ""

        # Clean title (ArXiv titles often have line breaks)
        title = re.sub(r"\s+", " ", title)

        # Extract authors
        authors = []
        for author_el in entry.findall("atom:author", ns):
            name_el = author_el.find("atom:name", ns)
            if name_el is not None and name_el.text:
                authors.append(name_el.text)
        first_author = authors[0] if authors else ""

        if len(title) < 10:
            continue

        snippet = summary[:250]
        if first_author:
            snippet = f"👤 {first_author} | 📅 {published} | {snippet}"

        results.append({
            "title": title,
            "snippet": snippet,
            "url": paper_url,
            "source": "arxiv",
        })

    return results


# ═══════════════════════════════════════════════════════════════
# Main entry
# ═══════════════════════════════════════════════════════════════

def scrape_broad_ai_news() -> list[dict]:
    """Scrape AI news from all sources: Bing + HN + Reddit + Twitter + ArXiv.

    Returns list of dicts with: title, snippet, url, source, source_label
    """
    all_results: list[dict] = []
    seen_urls: set[str] = set()

    def _add(item: dict) -> None:
        key = item.get("url") or item["title"]
        if key and key not in seen_urls:
            seen_urls.add(key)
            all_results.append(item)

    # ── Bing: broad + source-specific queries ──
    for query in _get_broad_queries():
        for item in _search_bing(query, num_results=2):
            item["source_label"] = f"bing: {query[:40]}"
            _add(item)

    for query in _get_source_queries():
        for item in _search_bing(query, num_results=2):
            item["source_label"] = f"bing: {query[:40]}"
            _add(item)

    # ── Hacker News ──
    print("  [hn] fetching...")
    try:
        for item in _fetch_hackernews("AI", hours_back=48, limit=10):
            item["source_label"] = "hackernews"
            _add(item)
    except Exception as exc:
        print(f"  [hn] failed (non-blocking): {exc}")

    # ── Reddit ──
    print("  [reddit] fetching...")
    try:
        for item in _fetch_reddit_ai():
            item["source_label"] = "reddit"
            _add(item)
    except Exception as exc:
        print(f"  [reddit] failed (non-blocking): {exc}")

    # ── Twitter/X ──
    print("  [twitter] fetching...")
    try:
        for item in _fetch_twitter():
            item["source_label"] = "twitter"
            _add(item)
    except Exception as exc:
        print(f"  [twitter] failed (non-blocking): {exc}")

    # ── ArXiv ──
    print("  [arxiv] fetching...")
    try:
        for item in _fetch_arxiv(max_results=8):
            item["source_label"] = "arxiv"
            _add(item)
    except Exception as exc:
        print(f"  [arxiv] failed (non-blocking): {exc}")

    print(f"  [scraper] raw total: {len(all_results)} items")

    # Final quality filter
    filtered = _filter_relevant(all_results)
    print(f"  [scraper] after filter: {len(filtered)} items")
    return filtered


def _filter_relevant(results: list[dict]) -> list[dict]:
    """Post-filter: keep only AI-relevant results, deduplicate by URL."""
    seen: set[str] = set()
    out: list[dict] = []
    bad_domains = {
        "iciba.com", "baike.baidu.com", "zhihu.com/question",
        "zhuanlan.zhihu.com", "cp.baidu.com/landing",
    }
    bad_keywords = [
        "词典", "百科", "翻译_音标", "是什么意思", "英语单词",
        "dictionary", "wikipedia", "wiki/",
    ]

    for item in results:
        url = item.get("url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")

        key = url or title
        if key in seen:
            continue
        seen.add(key)

        if any(d in url.lower() for d in bad_domains):
            continue

        combined = f"{title} {snippet}"
        if any(kw in combined for kw in bad_keywords):
            continue

        # For social sources (hn, reddit, twitter), skip AI relevance check
        # since the subreddit/query already filtered by topic
        source = item.get("source", "")
        if source in ("hackernews", "reddit", "twitter", "arxiv"):
            out.append(item)
            continue

        # For bing results, require AI signal
        if any(kw in combined.lower() for kw in AI_RELEVANCE_KW):
            out.append(item)

    return out


if __name__ == "__main__":
    results = scrape_broad_ai_news()
    print(f"\n{'='*60}")
    print(f"Total unique results: {len(results)}")
    print(f"{'='*60}")
    for i, r in enumerate(results, 1):
        src = r.get("source", "?")
        print(f"\n[{i}] [{src}] {r['title'][:100]}")
        print(f"    {r['snippet'][:180]}")
        if r.get("url"):
            print(f"    🔗 {r['url'][:120]}")
