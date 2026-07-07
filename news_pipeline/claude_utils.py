#!/usr/bin/env python3
"""Shared Claude API helper — single implementation used by all modules."""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

_ANTHROPIC_BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
_ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
_ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")


def call_claude(
    system_prompt: str,
    user_text: str,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """Call Claude API and return the text response.

    Returns empty string on any failure — callers should handle gracefully.
    """
    if not _ANTHROPIC_API_KEY:
        return ""

    payload: dict[str, Any] = {
        "model": _ANTHROPIC_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_text}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    api_url = f"{_ANTHROPIC_BASE_URL.rstrip('/')}/v1/messages"

    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "x-api-key": _ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"  [claude] API call failed: {exc}")
        return ""

    parts: list[str] = []
    for block in body.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
        elif block.get("type") == "thinking":
            continue
    return "\n\n".join(parts)


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
