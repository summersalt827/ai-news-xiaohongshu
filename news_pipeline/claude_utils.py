#!/usr/bin/env python3
"""Shared Claude API helper — multi-endpoint failover with retry + circuit breaker.

Reads up to 3 sets of API credentials from environment variables.
Tries each endpoint in order; on failure, retries with exponential backoff,
then falls through to the next endpoint.  Returns empty string only
when all endpoints are exhausted.

Circuit breaker: after 5 consecutive failures on an endpoint, it is skipped
for 60s to avoid hammering a degraded service.

Endpoint config:
  Primary:   ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL / ANTHROPIC_MODEL
  Fallback:  ANTHROPIC_API_KEY_2 / ANTHROPIC_BASE_URL_2 / ANTHROPIC_MODEL_2
  Fallback:  ANTHROPIC_API_KEY_3 / ANTHROPIC_BASE_URL_3 / ANTHROPIC_MODEL_3
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any

from circuit_breaker import get_breaker


def _build_endpoints() -> list[dict[str, str]]:
    """Build ordered endpoint list from environment variables."""
    endpoints: list[dict[str, str]] = []
    for suffix in ("", "_2", "_3"):
        key = os.environ.get(f"ANTHROPIC_API_KEY{suffix}", "")
        base = os.environ.get(
            f"ANTHROPIC_BASE_URL{suffix}",
            "https://api.anthropic.com",
        )
        model = os.environ.get(
            f"ANTHROPIC_MODEL{suffix}",
            "claude-sonnet-4-6",
        )
        if key:
            endpoints.append({"key": key, "base_url": base, "model": model})
    return endpoints


def call_claude(
    system_prompt: str,
    user_text: str,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """Call Claude API with multi-endpoint failover, exponential backoff, circuit breaker.

    Chain: endpoint-1 → retry(exp backoff) → endpoint-2 → retry → endpoint-3 → retry → "".
    Returns empty string only when ALL endpoints are exhausted.
    Each endpoint has its own circuit breaker — tripped endpoints are skipped.
    """
    endpoints = _build_endpoints()
    if not endpoints:
        return ""

    payload: dict[str, Any] = {
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_text}],
    }

    base_delay = 2.0  # seconds

    for i, ep in enumerate(endpoints):
        label = ep["base_url"].split("//")[-1].split("/")[0][:25]

        # Check circuit breaker for this endpoint
        cb = get_breaker(f"claude:{label}")
        if not cb.allow_call():
            print(
                f"  [claude] endpoint {i+1} ({label}) circuit OPEN "
                f"({cb.stats['consecutive_failures']} failures, skipping)"
            )
            continue

        api_url = f"{ep['base_url'].rstrip('/')}/v1/messages"

        for attempt in range(3):  # initial + 2 retries with exponential backoff
            if attempt > 0:
                delay = base_delay * (2 ** (attempt - 1))  # 2s, 4s
                print(
                    f"  [claude] endpoint {i+1} ({label}) "
                    f"retry {attempt}/{2} in {delay:.0f}s..."
                )
                time.sleep(delay)

            try:
                req_payload = {**payload, "model": ep["model"]}
                data = json.dumps(req_payload, ensure_ascii=False).encode("utf-8")
                req = urllib.request.Request(
                    api_url,
                    data=data,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "x-api-key": ep["key"],
                        "anthropic-version": "2023-06-01",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))

                parts: list[str] = []
                for block in body.get("content", []):
                    if block.get("type") == "text":
                        parts.append(block["text"])
                    elif block.get("type") == "thinking":
                        continue
                result = "\n\n".join(parts)

                cb.on_success()
                if i > 0:
                    print(f"  [claude] recovered on endpoint {i+1} ({label})")
                return result

            except Exception as exc:
                tag = f"retry {attempt}/{2}" if attempt > 0 else "attempt 1"
                print(
                    f"  [claude] endpoint {i+1} ({label}) {tag} failed: {exc}"
                )
                cb.on_failure()
                if i < len(endpoints) - 1 or attempt < 2:
                    continue  # try next retry or next endpoint

    return ""


def parse_json_lenient(raw: str) -> list | dict | None:
    """Parse potentially malformed JSON from LLM output.
    Handles both objects {...} and arrays [...].
    """
    import re
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*\n?", "", raw)
    raw = re.sub(r"\n?```\s*$", "", raw)

    # Try direct parse first
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Extract first JSON array or object
    m_arr = re.search(r"\[.*\]", raw, re.DOTALL)
    m_obj = re.search(r"\{.*\}", raw, re.DOTALL)

    if m_arr:
        # Prefer array if it starts earlier or object doesn't exist
        if not m_obj or m_arr.start() <= m_obj.start():
            raw = m_arr.group(0)
        else:
            raw = m_obj.group(0)
    elif m_obj:
        raw = m_obj.group(0)

    # Fix trailing commas
    raw = re.sub(r",\s*}", "}", raw)
    raw = re.sub(r",\s*]", "]", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None
