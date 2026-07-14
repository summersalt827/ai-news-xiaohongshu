#!/usr/bin/env python3
"""XHS post performance scraper — reuses .playwright-data/ login session.

Usage:
  python3 news_pipeline/analytics.py                   # fetch today
  python3 news_pipeline/analytics.py --date 2026-07-12 # fetch specific date
  python3 news_pipeline/analytics.py --headless        # run without showing browser

Output: xiaohongshu/analytics/YYYY-MM-DD.json
"""

from __future__ import annotations

import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
XHS_DIR = PROJECT_DIR / "xiaohongshu"
USER_DATA_DIR = PROJECT_DIR / ".playwright-data"
ANALYTICS_DIR = XHS_DIR / "analytics"

# Common XHS creator dashboard URLs to try
CREATOR_HOME = "https://creator.xiaohongshu.com"
CREATOR_CENTER = "https://creator.xiaohongshu.com/creator/center"
CONTENT_MANAGE = "https://creator.xiaohongshu.com/creator/center/manage"
NOTE_ANALYSIS = "https://creator.xiaohongshu.com/creator/center/note-analysis"
DATA_CENTER = "https://creator.xiaohongshu.com/creator/center/data-center"

# Known analytics API patterns to intercept
ANALYTICS_API_PATTERNS = [
    "note-analysis", "data-center", "statistics", "analytics",
    "creator/center", "creator/data", "edith.xiaohongshu.com",
    "note/stats", "post/stats", "content/stats",
]


def _scrape_via_api_intercept() -> dict | None:
    """Try to capture analytics data by intercepting XHR requests."""
    from playwright.sync_api import sync_playwright

    captured_responses: list[dict] = []
    dashboard_data: dict | None = None

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = ctx.new_page()

        # Intercept responses to capture analytics API calls
        def on_response(response):
            url = response.url
            if any(pattern in url for pattern in ANALYTICS_API_PATTERNS):
                try:
                    body = response.json()
                    captured_responses.append({"url": url, "body": body})
                except Exception:
                    pass

        page.on("response", on_response)

        # Navigate directly to note analysis page for best data
        urls_to_try = [NOTE_ANALYSIS, CONTENT_MANAGE, CREATOR_CENTER]
        for url in urls_to_try:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                continue
            time.sleep(5)

            # Check if redirected to login
            if "login" in page.url.lower() or "passport" in page.url.lower():
                print("  [analytics] login required, run publish_xiaohongshu_auto.py --login-only first")
                ctx.close()
                return None

            # Wait for XHR to settle — note analysis takes longer to load
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            time.sleep(3)

        ctx.close()

    if not captured_responses:
        print("  [analytics] no API responses captured")
        return None

    print(f"  [analytics] captured {len(captured_responses)} API responses")

    # Extract useful data from captured responses
    account_summary: dict = {}
    note_details: list[dict] = []
    note_base: list[dict] = []

    for cr in captured_responses:
        url = cr["url"]
        body = cr["body"]
        data = body.get("data", body)

        if "account/base" in url or "livedata/overview" in url:
            if isinstance(data, dict):
                seven = data.get("seven", {})
                if seven:
                    account_summary = {
                        "seven_day_views": seven.get("view_count", 0),
                        "seven_day_likes": seven.get("like_count", 0),
                        "seven_day_collects": seven.get("collect_count", 0),
                        "seven_day_comments": seven.get("comment_count", 0),
                        "seven_day_shares": seven.get("share_count", 0),
                        "seven_day_new_followers": seven.get("rise_fans_count", 0),
                        "avg_view_time_sec": seven.get("view_time_avg", 0),
                        "home_views": seven.get("home_view_count", 0),
                    }
                    print(f"    -> account: {account_summary['seven_day_views']} views, "
                          f"{account_summary['seven_day_likes']} likes, "
                          f"+{account_summary['seven_day_new_followers']} fans")
        elif "note_detail" in url or "note/base" in url or "create_guidance" in url:
            if isinstance(data, dict):
                # create_guidance returns a list
                items_list = data.get("note_details", data.get("notes", data.get("list", [])))
                if isinstance(items_list, list) and items_list:
                    for item in items_list:
                        if isinstance(item, dict):
                            note = {
                                "note_id": item.get("note_id", item.get("id", "")),
                                "title": item.get("display_title", item.get("title", "")),
                                "views": item.get("view_count", item.get("reads", 0)),
                                "likes": item.get("like_count", item.get("liked_count", 0)),
                                "collects": item.get("collect_count", item.get("favored_count", 0)),
                                "comments": item.get("comment_count", 0),
                                "shares": item.get("share_count", 0),
                                "publish_time": item.get("time", item.get("create_time", "")),
                            }
                            if note["note_id"] and note["note_id"] not in {n["note_id"] for n in note_details}:
                                note_details.append(note)
                                print(f"    -> note: {note['title'][:40]} | views={note['views']} likes={note['likes']}")

                # Single note detail
                note_id = data.get("note_id", data.get("id", ""))
                if note_id and note_id not in {n["note_id"] for n in note_details}:
                    note = {
                        "note_id": note_id,
                        "title": data.get("display_title", data.get("title", "")),
                        "views": data.get("view_count", data.get("reads", 0)),
                        "likes": data.get("like_count", data.get("liked_count", 0)),
                        "collects": data.get("collect_count", data.get("favored_count", 0)),
                        "comments": data.get("comment_count", 0),
                        "shares": data.get("share_count", 0),
                        "publish_time": data.get("time", data.get("create_time", "")),
                    }
                    note_details.append(note)
                    print(f"    -> note: {note['title'][:40]} | views={note['views']} likes={note['likes']}")
        elif "leaderboard" in url:
            if isinstance(data, dict):
                items = data.get("list", data.get("items", data.get("recommend", [])))
                if isinstance(items, list):
                    for item in items:
                        if isinstance(item, dict):
                            note = {
                                "note_id": item.get("note_id", item.get("id", "")),
                                "title": item.get("display_title", item.get("title", "")),
                                "views": item.get("view_count", item.get("reads", 0)),
                                "likes": item.get("like_count", item.get("liked_count", 0)),
                                "collects": item.get("collect_count", item.get("favored_count", 0)),
                                "comments": item.get("comment_count", 0),
                                "shares": item.get("share_count", 0),
                                "publish_time": item.get("time", item.get("create_time", "")),
                            }
                            if note["note_id"] and note["note_id"] not in {n["note_id"] for n in note_details}:
                                note_details.append(note)
                                print(f"    -> note(leaderboard): {note['title'][:40]} | views={note['views']}")

    # Fallback: if no per-note data, try to extract from any response
    if not note_details:
        for cr in captured_responses:
            body = cr["body"]
            # Try to find posts/notes array in the response
            for key in ["note_details", "notes", "posts", "list", "items"]:
                items = body.get("data", body).get(key, [])
                if isinstance(items, list) and items:
                    for item in items[:30]:
                        if isinstance(item, dict):
                            note_details.append({
                                "note_id": item.get("note_id", item.get("id", "")),
                                "title": item.get("display_title", item.get("title", "")),
                                "views": item.get("view_count", item.get("reads", 0)),
                                "likes": item.get("like_count", item.get("liked_count", 0)),
                                "collects": item.get("collect_count", item.get("favored_count", 0)),
                                "comments": item.get("comment_count", 0),
                                "shares": item.get("share_count", 0),
                                "publish_time": item.get("time", item.get("create_time", "")),
                            })
                    break
            if note_details:
                break

    result = {
        "account_summary": account_summary,
        "note_details": note_details,
        "_endpoints_found": [cr["url"].split("api/")[-1].split("?")[0][:80] for cr in captured_responses],
    }
    return result


def _scrape_via_dom(page) -> dict:
    """Fallback: scrape what's visible on the page DOM."""
    posts = []

    # Try common card/row selectors for post lists
    selectors = [
        ".note-item", ".post-item", ".content-item",
        "[class*='note']", "[class*='post-card']", "[class*='content-card']",
        "tr[class*='row']", ".table-row",
        "[class*='list-item']",
    ]

    for selector in selectors:
        items = page.locator(selector)
        count = items.count()
        if count > 0:
            print(f"  [analytics] found {count} items with '{selector}'")
            for i in range(min(count, 30)):
                try:
                    text = items.nth(i).inner_text()
                    posts.append({"index": i, "raw_text": text[:200]})
                except Exception:
                    continue
            if posts:
                break

    return {"posts": posts, "scrape_method": "dom_fallback"}


def fetch_analytics(target_date: str | None = None, headless: bool = False) -> Path | None:
    """Fetch XHS post analytics and save to JSON.

    Args:
        target_date: date string YYYY-MM-DD, defaults to today.
        headless: run browser without UI.

    Returns: Path to saved JSON file, or None on failure.
    """
    if target_date is None:
        target_date = date.today().isoformat()

    ANALYTICS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ANALYTICS_DIR / f"{target_date}.json"

    print(f"[analytics] fetching data for {target_date}...")

    # Strategy 1: API interception
    try:
        data = _scrape_via_api_intercept()
        if data:
            result = {
                "fetch_date": target_date,
                "fetch_time": datetime.now().isoformat(),
                "source": "api_intercept",
                "data": data,
            }
            out_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"  [analytics] saved to {out_path}")
            return out_path
    except Exception as exc:
        print(f"  [analytics] API intercept failed: {exc}")

    # Strategy 2: DOM scraping fallback with individual page navigation
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            ctx = p.chromium.launch_persistent_context(
                str(USER_DATA_DIR),
                headless=headless,
                channel="chrome",
                viewport={"width": 1440, "height": 900},
                locale="zh-CN",
            )
            page = ctx.new_page()
            page.goto(CONTENT_MANAGE, wait_until="domcontentloaded", timeout=20000)
            time.sleep(3)

            if "login" in page.url.lower():
                print("  [analytics] login required")
                ctx.close()
                return None

            dom_data = _scrape_via_dom(page)
            ctx.close()

    except ImportError:
        print("  [analytics] playwright not available for DOM scraping")
        dom_data = {"posts": [], "scrape_method": "unavailable"}

    result = {
        "fetch_date": target_date,
        "fetch_time": datetime.now().isoformat(),
        "source": "dom_scrape",
        "data": dom_data,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [analytics] saved to {out_path} (DOM fallback)")
    return out_path


# ── CLI ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="XHS analytics scraper")
    parser.add_argument("--date", help="target date (YYYY-MM-DD), default today")
    parser.add_argument("--headless", action="store_true", help="run headless")
    args = parser.parse_args()

    result = fetch_analytics(target_date=args.date, headless=args.headless)
    if result:
        print(f"Done: {result}")
    else:
        print("Failed to fetch analytics", file=sys.stderr)
        sys.exit(1)
