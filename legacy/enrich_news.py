#!/usr/bin/env python3
"""Enrich AI News with external search results from Bing — official blogs, benchmarks,
KOLs, media, and open-source community views. Feeds distiller with angles the email missed.

Pipeline:
  1. extract_sources_via_claude() — Claude extracts topics + search queries per source layer
  2. enrich_from_web() — Bing search each query, collect snippets
  3. summarize_enrichment() — Claude picks new angles vs the email
  4. enrich() — main entry, wrapped in try/except, never blocks the pipeline
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from typing import Any

os.environ.setdefault("no_proxy", "*")  # VPN proxy breaks TLS to direct China-accessible APIs

SOURCE_LAYERS: dict[str, str] = {
    "official": "anthropic blog OR openai blog OR google deepmind blog OR meta ai blog",
    "benchmarks": "artificial analysis OR lmsys OR weights & biases OR benchmarks",
    "kol": "simon willison OR ethan mollick OR dan shipper OR jeremy howard OR AI influencer",
    "media": "the verge OR techcrunch OR wired OR ars technica",
    "opensource": "cohere blog OR mistral blog OR open source AI",
}

BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


# ── Claude API helper ───────────────────────────────────────────

def _call_claude(system_prompt: str, user_text: str, max_tokens: int = 2048) -> str:
    if not API_KEY:
        return ""

    payload = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_text}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    api_url = f"{BASE_URL.rstrip('/')}/v1/messages"

    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [enrich] Claude API call failed: {exc}")
        return ""

    parts: list[str] = []
    for block in body.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n\n".join(parts)


# ── JSON parsing ────────────────────────────────────────────────

def _parse_json_lenient(raw: str) -> dict | None:
    raw = raw.strip()
    # strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)
    # extract first JSON object
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        raw = m.group(0)
    # fix trailing commas (common LLM mistake)
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


# ── Bing search ─────────────────────────────────────────────────

def _search_bing(query: str, num_results: int = 3) -> list[str]:
    url = f"https://www.bing.com/search?q={urllib.parse.quote(query)}&setlang=en&mkt=en-US"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9,zh-CN;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"  [enrich] Bing search failed for '{query[:60]}': {exc}")
        return []

    snippets: list[str] = []
    # Bing snippet containers
    for match in re.finditer(
        r'<(?:p|div)[^>]*class="[^"]*?(?:b_lineclamp|b_caption|b_snippet)[^"]*"[^>]*>(.*?)</(?:p|div)>',
        html, re.DOTALL | re.IGNORECASE,
    ):
        text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
        text = re.sub(r"&amp;", "&", text)
        text = re.sub(r"&lt;", "<", text)
        text = re.sub(r"&gt;", ">", text)
        text = re.sub(r"&quot;", '"', text)
        text = re.sub(r"&#\d+;", "", text)
        if len(text) > 40:
            snippets.append(text)

    # fallback: any <p> tag
    if not snippets:
        for match in re.finditer(r"<p[^>]*>(.*?)</p>", html, re.DOTALL):
            text = re.sub(r"<[^>]+>", "", match.group(1)).strip()
            text = re.sub(r"&amp;", "&", text)
            text = re.sub(r"&lt;", "<", text)
            text = re.sub(r"&gt;", ">", text)
            text = re.sub(r"&quot;", '"', text)
            text = re.sub(r"&#\d+;", "", text)
            if len(text) > 50:
                snippets.append(text)

    return snippets[:num_results]


# ── Step 1: Claude extracts topics → search queries ─────────────

_EXTRACT_TEMPLATE = """\
Analyze this AI news and output a single JSON object.

{ "topics": ["cn_topic_1", "cn_topic_2"], "queries": { "official": ["site:company.com specific model or event name announcement"], "benchmarks": ["model name benchmark results comparison"], "kol": ["company or model name AI influencer reaction"], "media": ["specific event or model name tech news coverage"], "opensource": ["model or event name open source community reaction"] } }

Rules:
- 2 Chinese topics, each <=15 characters, capturing the core events
- Search query per source type: short English (4-8 words), use SPECIFIC model/product names, use site: operator for official sources
- Example query: "Anthropic Fable 5 suspended national security June 2026"
- Output the JSON object ONLY, no markdown fences, no explanation

--- AI NEWS ---
"""


def extract_sources_via_claude(translated_text: str, subject: str = "") -> dict[str, Any]:
    text = translated_text[:4000]
    if subject and subject not in text:
        text = f"Subject: {subject}\n\n{text}"

    user_prompt = _EXTRACT_TEMPLATE + text

    raw = _call_claude(
        "Respond with exactly one JSON object. No markdown. No extra text.",
        user_prompt,
        max_tokens=1024,
    )
    if not raw:
        return {"topics": [], "queries": {}}

    result = _parse_json_lenient(raw)
    if result is None:
        print(f"  [enrich] non-JSON response: {raw[:250]}")
        return {"topics": [], "queries": {}}

    if "topics" not in result or "queries" not in result:
        print(f"  [enrich] unexpected keys: {list(result.keys())}")
        return {"topics": [], "queries": {}}

    return result


# ── Step 2: Web search ──────────────────────────────────────────

def enrich_from_web(queries_dict: dict[str, list[str] | str]) -> dict[str, list[str]]:
    all_results: dict[str, list[str]] = {}

    for layer, queries in queries_dict.items():
        # 兼容 Claude 返回字符串而非数组
        qlist: list[str] = [queries] if isinstance(queries, str) else queries

        source_hint = SOURCE_LAYERS.get(layer, "")
        layer_results: list[str] = []

        for q in qlist[:2]:
            if len(q) < 10:  # 跳过太短的无效查询
                continue
            full_query = f"{q} {source_hint}" if source_hint else q
            snippets = _search_bing(full_query, num_results=2)
            layer_results.extend(snippets)

        if layer_results:
            all_results[layer] = layer_results

    return all_results


# ── Step 3: Claude summarizes new angles ────────────────────────

def summarize_enrichment(
    search_results: dict[str, list[str]], translated_text: str
) -> str:
    if not search_results:
        return ""

    layer_labels = {
        "official": "Official blogs",
        "benchmarks": "Benchmarks & evals",
        "kol": "KOL opinions",
        "media": "Tech media",
        "opensource": "Open source community",
    }
    parts: list[str] = []
    for layer, snippets in search_results.items():
        label = layer_labels.get(layer, layer)
        parts.append(f"### {label}")
        for i, s in enumerate(snippets[:5], 1):
            parts.append(f"{i}. {s[:300]}")
        parts.append("")

    search_text = "\n".join(parts)

    prompt = (
        "You analyze AI news. Below is the newsletter content and external search "
        "results. Search results may be partial or noisy — extract whatever useful "
        "information you can find. Identify any interesting angles, data points, or "
        "context that adds to the newsletter.\n\n"
        "If the search results are sparse, summarize what little you find. "
        "If they are completely empty, say 'no additional context found'. "
        "Write in Chinese, 2-4 paragraphs max, <=4 sentences each."
    )

    user_text = (
        f"# Newsletter\n\n{translated_text[:3000]}\n\n"
        f"# External Search\n\n{search_text[:4000]}"
    )

    result = _call_claude(prompt, user_text, max_tokens=1024)
    return result.strip() if result else ""


# ── Main entry ──────────────────────────────────────────────────

def enrich(translated_text: str, subject: str = "") -> str:
    if not API_KEY:
        return ""

    try:
        print("  [enrich] extracting topics...")
        sources = extract_sources_via_claude(translated_text, subject)

        if not sources.get("queries"):
            print("  [enrich] no topics extracted, skip")
            return ""

        topics = sources.get("topics", [])
        n_queries = sum(len(v) for v in sources["queries"].values())
        print(f"  [enrich] topics: {topics}  ({n_queries} queries)")

        print("  [enrich] searching external sources...")
        search_results = enrich_from_web(sources["queries"])

        if not search_results:
            print("  [enrich] no search results, skip")
            return ""

        n_snippets = sum(len(v) for v in search_results.values())
        print(f"  [enrich] {n_snippets} snippets, summarizing...")
        summary = summarize_enrichment(search_results, translated_text)

        if summary:
            print(f"  [enrich] summary: {len(summary)} chars")
        return summary

    except Exception as exc:
        print(f"  [enrich] failed (non-blocking): {exc}")
        return ""
