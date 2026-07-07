#!/usr/bin/env python3
"""从 163 邮箱拉取标题含 "AI news" 的邮件，翻译后推送到飞书并生成展示内容。

流程:
  1. 连接 163 IMAP，搜索标题含 "AI news" 的未读邮件
  2. 提取正文，调用 Claude API 中英互译
  3. 生成 Markdown 存档 + HTML 展示页 + 小红书图文
  4. HTML 复制到 public/ 目录供 Vercel 部署
  5. 推送摘要 + HTML 链接到飞书

环境变量:
  EMAIL_163_USER     - 163 邮箱地址
  EMAIL_163_PASS     - 163 IMAP 授权码（非登录密码）
  ANTHROPIC_API_KEY  - Claude API key，用于翻译
  VERCEL_URL         - (可选) Vercel 部署域名，默认 https://claude-test.vercel.app
"""

from __future__ import annotations

import email
import imaplib
import json
import os
import re

os.environ["no_proxy"] = "*"  # 禁用系统代理，直连（走 Clash Verge 代理反而 TLS 握手失败）
import shutil
import ssl
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from email.header import decode_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path

# 项目路径 — fetch_ai_news.py 在 news_pipeline/ 下，PROJECT_DIR 指向上级
PROJECT_DIR = Path(__file__).resolve().parent.parent  # ai-news-xiaohongshu 根目录
sys.path.insert(0, str(PROJECT_DIR))  # 让 xhs_publish/ 模块可导入
CLAUDE_TEST = Path.home() / "Desktop" / "claude-test"  # claude-test 项目
DAILY_DIR = PROJECT_DIR / "daily"
LOG_DIR = PROJECT_DIR / "logs"
XHS_DIR = PROJECT_DIR / "xiaohongshu"
PUBLIC_DIR = CLAUDE_TEST / "public" / "ai-news"

# 飞书 Webhook
FEISHU_WEBHOOK = os.environ.get("FEISHU_WEBHOOK", "")

# Vercel 部署地址
VERCEL_URL = os.environ.get("VERCEL_URL", "https://claude-test-blush.vercel.app")

# 163 IMAP
IMAP_HOST = "imap.163.com"
IMAP_PORT = 993
SEARCH_SUBJECT = "[AINews]"

# 额外搜索的文件夹和条件
EXTRA_FOLDERS = [
    '"&Xn9USpCuTvY-"',   # 广告邮件
    '"&i6KWBZCuTvY-"',   # 订阅邮件
    '"&V4NXPpCuTvY-"',   # 垃圾邮件
]
EXTRA_SUBJECTS = ["AI news", "AI News", "[AINews]", "AINews"]

# ── 邮件正文提取 ────────────────────────────────────────────

class _HTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    @property
    def text(self) -> str:
        return "".join(self._parts)


def _decode_header_value(value: str) -> str:
    parts: list[str] = []
    for fragment, charset in decode_header(value):
        if isinstance(fragment, bytes):
            charset = charset or "utf-8"
            try:
                parts.append(fragment.decode(charset, errors="replace"))
            except LookupError:
                parts.append(fragment.decode("utf-8", errors="replace"))
        else:
            parts.append(fragment)
    return "".join(parts)


def _extract_body(msg: email.message.Message) -> str:
    text_parts: list[str] = []
    html_parts: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if content_type == "text/plain":
                text_parts.append(text)
            elif content_type == "text/html":
                html_parts.append(text)
    else:
        content_type = msg.get_content_type()
        try:
            payload = msg.get_payload(decode=True)
            if payload:
                charset = msg.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
                if content_type == "text/plain":
                    text_parts.append(text)
                elif content_type == "text/html":
                    html_parts.append(text)
        except Exception:
            pass

    if text_parts:
        return "\n".join(text_parts)
    if html_parts:
        stripper = _HTMLStripper()
        stripper.feed("\n".join(html_parts))
        return stripper.text.strip()
    return ""


def _clean_body(text: str) -> str:
    lines = text.splitlines()
    cleaned: list[str] = []
    blank_count = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith(">") and len(stripped) < 200:
            continue
        if stripped == "":
            blank_count += 1
            if blank_count <= 2:
                cleaned.append("")
        else:
            blank_count = 0
            cleaned.append(stripped)
    return "\n".join(cleaned).strip()


# ── Claude 翻译 ─────────────────────────────────────────────

def translate_with_claude(text: str, subject: str = "") -> str:
    """调用 Claude API 翻译。

    Twitter Recap 邮件：纯中文摘要，不引用原文。
    其他邮件：中英对照格式。
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    base_url = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

    if not api_key:
        return "[未配置 ANTHROPIC_API_KEY，跳过翻译]\n\n" + text

    is_twitter_recap = "twitter recap" in subject.lower()

    if is_twitter_recap:
        system_prompt = (
            "你是专业AI行业翻译与分析助手。这是一份 Twitter/X 上 AI 领域热门推文的每周汇总。"
            "将内容翻译成中文，每条推文翻译后加一行📌背景说明。"
            "不要引用英文原文，直接输出中文翻译。"
            "保留专业术语。不要遗漏任何条目。"
        )
    else:
        chinese_chars = len(re.findall(r"[一-鿿]", text))
        is_primarily_chinese = chinese_chars > len(text) * 0.3

        if is_primarily_chinese:
            system_prompt = (
                "你是专业翻译。将中文内容翻译成英文。"
                "输出格式：每段先引用中文原文（> 开头），紧跟英文翻译，然后加一行「背景:」简要说明这段新闻的来龙去脉和相关上下文。"
                "保留原文的专业术语。"
            )
        else:
            system_prompt = (
                "你是专业AI行业翻译与分析助手。将英文AI新闻翻译成中文。"
                "对每条新闻，输出格式为三段：\n"
                "1. 引用英文原文（> 开头）\n"
                "2. 中文翻译\n"
                "3. 背景信息（📌 背景: 开头）——简要说明该新闻的来龙去脉、涉及的公司/产品背景、"
                "为何重要、与之前事件的关联等，帮助读者理解上下文。每条背景2-4句话。\n"
                "保留原文的专业术语。不要遗漏任何新闻条目。"
            )

    payload = {
        "model": model,
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [{"role": "user", "content": text}],
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    api_url = f"{base_url.rstrip('/')}/v1/messages"
    req = urllib.request.Request(
        api_url,
        data=data,
        headers={
            "Content-Type": "application/json; charset=utf-8",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        print(f"  Claude API error: {error_body}", file=sys.stderr)
        return f"[翻译失败]\n\n{text}"
    except Exception as exc:
        print(f"  Claude API request failed: {exc}", file=sys.stderr)
        return f"[翻译失败]\n\n{text}"

    content = body.get("content", [])
    parts: list[str] = []
    for block in content:
        block_type = block.get("type", "")
        if block_type == "text":
            parts.append(block.get("text", ""))
        elif block_type == "thinking":
            # DeepSeek 等推理模型返回的 thinking 块，跳过
            continue
    if not parts:
        print(f"  Warning: No text in response. Content types: {[b.get('type') for b in content]}", file=sys.stderr)
    return "\n\n".join(parts)


# ── IMAP 邮件拉取 ───────────────────────────────────────────

def _connect_imap() -> imaplib.IMAP4_SSL:
    user = os.environ.get("EMAIL_163_USER", "")
    password = os.environ.get("EMAIL_163_PASS", "")
    if not user or not password:
        print("请设置环境变量 EMAIL_163_USER 和 EMAIL_163_PASS", file=sys.stderr)
        sys.exit(1)

    # 注册 IMAP ID 命令 (163 邮箱强制要求)
    if "ID" not in imaplib.Commands:
        imaplib.Commands["ID"] = ("AUTH",)

    ctx = ssl.create_default_context()
    conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx, timeout=30)
    conn.login(user, password)

    # 发送客户端 ID 标识 (163 邮箱要求，否则拒绝 SELECT)
    args = (
        "name", "AI-News-Fetcher",
        "version", "1.0.0",
        "vendor", "claude-test",
        "contact", user,
    )
    conn._simple_command("ID", '("' + '" "'.join(args) + '")')

    return conn


def _fetch_emails_by_subject(conn: imaplib.IMAP4_SSL, folder: str,
                              subject_patterns: list[str],
                              processed_ids: set[str],
                              limit: int = 50) -> list[dict]:
    """在指定文件夹拉取最近邮件，Python 端按标题关键字过滤。

    163 邮箱的 IMAP SUBJECT 搜索对含特殊字符（如 [ ]）的标题不可靠，
    因此改为拉取邮件头后本地过滤。
    """
    try:
        conn.select(folder, readonly=False)
    except Exception as e:
        print(f"  跳过文件夹 {folder}: {e}", file=sys.stderr)
        return []

    # 获取文件夹中最近 N 封邮件
    status, all_ids = conn.search(None, "ALL")
    if status != "OK" or not all_ids[0]:
        return []

    all_id_list = sorted(all_ids[0].split(), key=lambda x: int(x), reverse=True)
    recent_ids = all_id_list[:limit]

    results: list[dict] = []
    for mail_id in recent_ids:
        mid = mail_id.decode()
        if mid in processed_ids:
            continue

        try:
            status, msg_data = conn.fetch(mail_id, "(BODY.PEEK[HEADER.FIELDS (SUBJECT FROM DATE)])")
            if status != "OK":
                continue
        except Exception:
            continue

        header_data = msg_data[0][1]
        if header_data is None:
            continue
        msg = email.message_from_bytes(header_data)
        subject = _decode_header_value(msg.get("Subject", ""))
        sender = _decode_header_value(msg.get("From", ""))

        # Python 端关键字匹配
        matched = any(pattern.lower() in subject.lower() for pattern in subject_patterns)
        if not matched:
            continue

        processed_ids.add(mid)

        # 重新拉取完整邮件获取正文
        try:
            status, full_data = conn.fetch(mail_id, "(RFC822)")
            if status != "OK":
                continue
            raw = full_data[0][1]
            if raw is None:
                continue
        except Exception:
            continue

        full_msg = email.message_from_bytes(raw)
        try:
            mail_date = parsedate_to_datetime(full_msg.get("Date", ""))
        except Exception:
            mail_date = datetime.now(timezone.utc)

        body = _extract_body(full_msg)
        body = _clean_body(body)

        if body:
            results.append({
                "id": mid,
                "subject": subject,
                "sender": sender,
                "date": mail_date,
                "body": body,
                "translated_body": "",
            })

        conn.store(mail_id, "+FLAGS", "\\Seen")

    return results


def _search_ai_news_emails(conn: imaplib.IMAP4_SSL) -> list[dict]:
    """在收件箱及订阅文件夹中搜索 AI News 相关邮件。

    只返回当天的邮件（按 UTC 日期比较），最多 3 封。
    """
    processed_ids: set[str] = set()
    all_results: list[dict] = []

    # 标题匹配关键字（Python 端过滤，大小写不敏感）
    subject_keywords = ["[ainews]", "ainews", "ai news", "twitter recap"]

    # 1. 搜索收件箱
    inbox_results = _fetch_emails_by_subject(conn, "INBOX", subject_keywords, processed_ids, limit=50)
    all_results.extend(inbox_results)
    if inbox_results:
        print(f"  收件箱: {len(inbox_results)} 封匹配邮件")

    # 2. 搜索额外的文件夹
    for folder in EXTRA_FOLDERS:
        results = _fetch_emails_by_subject(conn, folder, subject_keywords, processed_ids, limit=50)
        all_results.extend(results)
        if results:
            print(f"  {folder}: {len(results)} 封匹配邮件")

    # 优先今天的邮件；今天没有则往前追溯最近日期的邮件
    today_utc = date.today()
    all_results.sort(key=lambda x: x["date"], reverse=True)

    today_results = [r for r in all_results
                     if (r["date"].date() if r["date"] else today_utc) == today_utc]

    # 今天有邮件用今天的，没有则取最新日期的那批
    if today_results:
        candidates = today_results
    else:
        candidates = all_results
        if candidates:
            latest_date = candidates[0]["date"].date()
            candidates = [r for r in candidates if r["date"].date() == latest_date]

    twitter_recaps = [r for r in candidates if "twitter recap" in r["subject"].lower()]
    non_recaps = [r for r in candidates if "twitter recap" not in r["subject"].lower()]
    return non_recaps[:3] + twitter_recaps


# ── 飞书推送 ─────────────────────────────────────────────────

def _send_feishu_text(text: str) -> None:
    """发送飞书纯文本消息。"""
    max_chars = 14_500
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n\n…(已截断)"

    payload = {"msg_type": "text", "content": {"text": text}}
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return

    code = body.get("code") or body.get("StatusCode")
    if code is not None and code != 0:
        print(f"Feishu push failed: {body}", file=sys.stderr)


def _send_feishu_rich(title: str, summary: str, url: str) -> None:
    """发送飞书富文本卡片消息。未配置 Webhook 则跳过。"""
    if not FEISHU_WEBHOOK:
        return
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": title},
                "template": "purple",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": summary,
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看完整双语日报"},
                            "type": "primary",
                            "url": url,
                        }
                    ],
                },
            ],
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        FEISHU_WEBHOOK,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8", errors="replace"), file=sys.stderr)
        return

    code = body.get("code") or body.get("StatusCode")
    if code is not None and code != 0:
        # 富文本发送失败时回退到纯文本
        print(f"  Feishu card failed, fallback to text: {body}", file=sys.stderr)
        _send_feishu_text(summary)


# ── 翻译内容解析 ────────────────────────────────────────────

def _parse_translated_blocks(translated_text: str) -> list[dict]:
    """将翻译结果解析为 [{title, original, translation}] 结构，供 HTML 和图片生成使用。"""
    blocks: list[dict] = []
    lines = translated_text.splitlines()
    i = 0

    current_origin: list[str] = []
    current_trans: list[str] = []

    def _flush() -> None:
        nonlocal current_origin, current_trans
        origin = " ".join(current_origin).strip()
        trans = " ".join(current_trans).strip()
        if origin or trans:
            blocks.append({"original": origin, "translation": trans, "title": ""})
        current_origin = []
        current_trans = []

    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(">"):
            _flush()
            current_origin.append(line[1:].strip())
            i += 1
            while i < len(lines):
                nl = lines[i].strip()
                if nl.startswith(">"):
                    break
                if nl:
                    current_trans.append(nl)
                elif current_trans:
                    break
                i += 1
        else:
            if line:
                current_trans.append(line)
            i += 1

    _flush()

    # 如果没有解析到结构化块，则将全文作为一个块
    if not blocks:
        blocks.append({"original": translated_text, "translation": "", "title": ""})

    # 为每个块取前几个词作为 title
    for block in blocks:
        origin = block["original"] or block["translation"]
        block["title"] = origin[:80] + ("..." if len(origin) > 80 else "")

    return blocks


# ── 索引文件 ───────────────────────────────────────────────

def _update_index_json() -> None:
    """更新 public/ai-news/index.json，列出所有 HTML 文件。"""
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(
        [f.name for f in PUBLIC_DIR.glob("*.html") if f.name != "index.html"],
        reverse=True,
    )
    index_path = PUBLIC_DIR / "index.json"
    index_path.write_text(json.dumps(files, ensure_ascii=False), encoding="utf-8")


# ── Markdown 生成 ───────────────────────────────────────────

def _build_markdown(emails: list[dict], today: str) -> str:
    lines = [f"# AI News 邮件翻译 - {today}\n"]
    for i, mail in enumerate(emails, 1):
        mail_time = mail["date"].strftime("%Y-%m-%d %H:%M") if mail["date"] else "未知"
        lines.append(f"## 邮件 {i}: {mail['subject']}")
        lines.append(f"**发件人:** {mail['sender']}")
        lines.append(f"**时间:** {mail_time}\n")
        lines.append(mail.get("translated_body", mail["body"]))
        lines.append("\n---\n")
    lines.append(f"\n> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    return "\n".join(lines)


def _generate_combined_caption(
    items: list[dict], output_dir: Path, date_str: str, emails: list[dict]
) -> Path:
    """Generate Xiaohongshu caption file for combined items."""
    date_display = date.fromisoformat(date_str).strftime("%Y年%m月%d日")
    email_subject = emails[0]["subject"] if emails else "AI News"
    # Strip [AINews] prefix
    email_subject = email_subject.replace("[AINews]", "").strip().strip(":").strip()

    lines = [f"🤖 AI 小白速览 | {date_display}"]
    lines.append("")
    for i, item in enumerate(items, 1):
        emoji = item.get("emoji", "📌")
        title = item.get("title", "")
        summary = item.get("summary", "")
        source = item.get("source_note", "")
        lines.append(f"{i}️⃣ {emoji} {title}")
        lines.append(f"   {summary}")
        if source:
            lines.append(f"   📍 {source}")
        lines.append("")

    lines.append("—")
    lines.append(f"📧 邮件来源: {email_subject}")
    lines.append("")
    lines.append("#AI新闻 #小白必看 #人工智能 #科技资讯 #每日AI")

    caption_path = output_dir / f"{date_str}_caption.txt"
    caption_path.write_text("\n".join(lines), encoding="utf-8")
    return caption_path


# ── Main ─────────────────────────────────────────────────────

def main() -> None:
    today = date.today().isoformat()
    print(f"[{today}] 开始检查 AI news 邮件...")

    conn = _connect_imap()
    try:
        emails = _search_ai_news_emails(conn)
    finally:
        conn.logout()

    print(f"  找到 {len(emails)} 封 AI news 邮件")

    # 日志目录
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    if not emails:
        (LOG_DIR / f"{today}.log").write_text(
            f"[{today}] 无 AI news 邮件\n", encoding="utf-8"
        )
        return

    # 用邮件实际日期作为 effective date，而非今天
    effective_date = emails[0]["date"].strftime("%Y-%m-%d") if emails[0]["date"] else today
    print(f"  effective date: {effective_date}")

    # ── Step 1: 翻译所有邮件 ──────────────────────────────
    for i, mail in enumerate(emails, 1):
        print(f"  翻译中... (邮件 {i}/{len(emails)}: {mail['subject'][:40]})")
        mail["translated_body"] = translate_with_claude(mail["body"], mail["subject"])

    # 收集合并后的翻译文本（供后续 enrich + distill 使用）
    merged_translated = "\n\n---\n\n".join(
        m.get("translated_body", m["body"]) for m in emails
    )
    primary_subject = emails[0]["subject"]

    # ── Step 1.5: 全网抓取 (所有信息源) ──────────────────
    print("  全网抓取 AI 新闻...")
    web_items_raw: list[dict] = []
    try:
        from web_scraper import scrape_broad_ai_news
        web_items_raw = scrape_broad_ai_news()
        print(f"  网页抓取: {len(web_items_raw)} 条")
    except Exception as exc:
        print(f"  网页抓取失败 (不阻塞): {exc}")

    # ── Step 1.6: Claude 精选 4 条 AI 新闻 ────────────────
    print("  精选 4 条 AI 新闻...")
    ai_items: list[dict] = []
    try:
        from item_matcher import curate_from_all_sources
        ai_items = curate_from_all_sources(merged_translated, web_items_raw)
        print(f"  AI 新闻: {len(ai_items)} 条")
    except Exception as exc:
        print(f"  精选失败 (不阻塞): {exc}")

    # ── Step 1.7: GitHub Trending (1条) ────────────────────
    print("  GitHub Trending...")
    github_items: list[dict] = []
    try:
        from github_trending import fetch_trending_repos, pick_best_github
        repos = fetch_trending_repos()
        if repos:
            github_items = pick_best_github(repos)
            print(f"  GitHub: {len(github_items)} 条")
    except Exception as exc:
        print(f"  GitHub Trending 失败 (不阻塞): {exc}")

    # ── Step 1.8: 精选结果 (自动确认) ──────────────────────
    from item_matcher import format_confirmation_prompt
    print(format_confirmation_prompt(ai_items, github_items))
    print("  ✅ 自动确认全部\n")

    # ── Step 1.9: 生成小红书卡片 + 封面 + PNG ────────────────
    card_html_paths: list[Path] = []
    all_card_pngs: list[Path] = []
    video_path: Path | None = None
    xhs_output_dir = XHS_DIR / effective_date
    combined_items = github_items + ai_items  # GitHub 置顶
    if combined_items:
        print(f"  生成小红书卡片 ({len(combined_items)}张)...")
        try:
            from xhs_publish.render_combined import save_cards_and_cover, screenshot_htmls
            xhs_output_dir.mkdir(parents=True, exist_ok=True)

            # 1. 生成卡片 + 封面（封面只用 AI items，不含 GitHub）
            card_html_paths, cover_path, caption_path = save_cards_and_cover(
                combined_items, xhs_output_dir, effective_date,
                cover_items=ai_items,
            )
            print(f"  卡片 HTML: {len(card_html_paths)} 张")
            print(f"  封面 HTML: {cover_path}")
            print(f"  文案: {caption_path}")

            # 1.5 生成 B站 16:9 封面
            from xhs_publish.render_video import _render_cover_html
            cover_bili_html = _render_cover_html(ai_items, effective_date, aspect="16:9")
            cover_bili_path = xhs_output_dir / f"{effective_date}_cover_bilibili.html"
            cover_bili_path.write_text(cover_bili_html, encoding="utf-8")

            # 2. HTML → PNG (封面 + B站封面 + 所有卡片)
            all_htmls = [cover_path, cover_bili_path] + card_html_paths
            all_card_pngs = screenshot_htmls(all_htmls, xhs_output_dir)
            print(f"  截图 PNG: {len(all_card_pngs)} 张 (含B站封面)")

            # 3. 同步封面 HTML 到 Vercel
            cover_public = PUBLIC_DIR / f"{effective_date}_cover.html"
            shutil.copy2(cover_path, cover_public)

            # 4. 生成视频 (B站 16:9 + 小红书 9:16)
            video_path = None
            try:
                from xhs_publish.render_video import render_video_from_items
                # BGM: first available mp3 in bgm/ dir
                _bgm_dir = PROJECT_DIR / "bgm"
                _bgm_files = sorted(_bgm_dir.glob("*.mp3")) if _bgm_dir.is_dir() else []
                _bgm = str(_bgm_files[0]) if _bgm_files else ""
                video_16x9 = render_video_from_items(combined_items, xhs_output_dir,
                                                     effective_date, aspect="16:9",
                                                     bgm_path=_bgm)
                print(f"  视频(16:9): {video_16x9}")
                video_9x16 = render_video_from_items(combined_items, xhs_output_dir,
                                                     effective_date, aspect="9:16",
                                                     bgm_path=_bgm)
                print(f"  视频(9:16): {video_9x16}")
                video_path = video_16x9  # primary output for logging
            except Exception as exc:
                print(f"  视频生成失败 (不阻塞): {exc}")
                video_path = None
        except Exception as exc:
            print(f"  卡片生成失败 (不阻塞): {exc}")

    # ── Step 2: 生成 Markdown 存档 ────────────────────────
    print("  生成 Markdown 存档...")
    md_content = _build_markdown(emails, effective_date)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    md_path = DAILY_DIR / f"{effective_date}.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"  已保存: {md_path}")

    # ── Step 3: 生成 HTML 展示页 ──────────────────────────
    print("  生成 HTML 展示页...")
    from xhs_publish.render_html import save_html

    html_path = save_html(emails, DAILY_DIR, effective_date)
    print(f"  HTML 已保存: {html_path}")

    # 复制到 public/ai-news/ 供 Vercel 部署
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    public_html = PUBLIC_DIR / f"{effective_date}.html"
    shutil.copy2(html_path, public_html)
    _update_index_json()
    print(f"  已复制到 Vercel public 目录: {public_html}")

    html_url = f"{VERCEL_URL.rstrip('/')}/ai-news/{effective_date}.html"

    # ── Step 4: 生成小红书内容 ────────────────────────────
    print("  生成小红书图文...")
    from xhs_publish.render_xiaohongshu import save_xiaohongshu

    # 收集所有翻译块供小红书图片使用
    all_blocks: list[dict] = []
    for mail in emails:
        blocks = _parse_translated_blocks(mail["translated_body"])
        for b in blocks:
            b["title"] = mail["subject"]  # 用邮件标题作为卡片标题
        all_blocks.extend(blocks[:3])  # 每封邮件最多3个块

    img_path, caption_path = save_xiaohongshu(emails, all_blocks, xhs_output_dir, effective_date)

    # ── Step 4.5: 自动发布到小红书 ────────────────────────
    try:
        publish_script = PROJECT_DIR / "xhs_publish" / "publish_xiaohongshu_auto.py"
        if publish_script.exists():
            import subprocess as _sp
            print("  启动自动发布...")
            _sp.Popen(
                [sys.executable, str(publish_script), effective_date],
                stdout=_sp.DEVNULL, stderr=_sp.DEVNULL,
            )
    except Exception as exc:
        print(f"  启动发布失败 (不阻塞): {exc}")

    # ── Step 5: 推送到飞书 ────────────────────────────────
    print("  推送到飞书...")
    date_display = date.fromisoformat(effective_date).strftime("%Y年%m月%d日")
    summary_lines = [
        f"共 {len(emails)} 封 AI News 邮件",
        "",
    ]
    for i, mail in enumerate(emails, 1):
        preview = mail["body"][:100].replace("\n", " ")
        summary_lines.append(f"**{i}. {mail['subject']}**")
        summary_lines.append(f"{preview}...")
        summary_lines.append("")

    summary_lines.append("---")
    summary_lines.append(f"双语完整版: {html_url}")
    if all_card_pngs:
        cover_url = f"{VERCEL_URL.rstrip('/')}/ai-news/{effective_date}_cover.html"
        summary_lines.append(f"小红书封面: {cover_url}")
    if video_path:
        summary_lines.append(f"视频: {video_path}")
    summary_lines.append(f"Markdown 存档: daily/{effective_date}.md")

    summary = "\n".join(summary_lines)
    _send_feishu_rich(
        title=f"AI News 双语日报 | {date_display}",
        summary=summary,
        url=html_url,
    )
    print("  已推送到飞书")

    # ── Step 6: 写日志 ───────────────────────────────────
    log_path = LOG_DIR / f"{today}.log"
    log_lines = [
        f"[{effective_date}] 处理了 {len(emails)} 封 AI news 邮件",
        f"  Markdown: {md_path}",
        f"  HTML: {html_path}",
        f"  HTML URL: {html_url}",
        f"  Xiaohongshu: {xhs_output_dir}",
    ]
    if all_card_pngs:
        log_lines.append(f"  卡片 PNG: {len(all_card_pngs)} 张")
        log_lines.append(f"  卡片目录: {xhs_output_dir}")
    if video_path:
        log_lines.append(f"  视频: {video_path}")
    log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")

    print(f"\n  {'='*50}")
    print(f"  处理完成!")
    print(f"  Markdown:    {md_path}")
    print(f"  HTML (本地): {html_path}")
    print(f"  HTML (线上): {html_url}")
    print(f"  小红书图片:  {img_path}")
    print(f"  小红书文案:  {caption_path}")
    if all_card_pngs:
        print(f"  卡片 PNG:    {len(all_card_pngs)} 张")
        print(f"  卡片目录:    {xhs_output_dir}")
    if video_path:
        print(f"  视频:        {video_path}")
    print(f"  {'='*50}")


if __name__ == "__main__":
    main()
