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

# 项目路径
PROJECT_DIR = Path(__file__).resolve().parent  # ai_news_translation 文件夹
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

    # 只保留今天的邮件
    today_utc = date.today()
    today_results: list[dict] = []
    for r in all_results:
        mail_date = r["date"].date() if r["date"] else today_utc
        if mail_date == today_utc:
            today_results.append(r)

    # 按日期排序，取最多 3 封 AINews + 不限数量的 Twitter Recap
    today_results.sort(key=lambda x: x["date"], reverse=True)
    twitter_recaps = [r for r in today_results if "twitter recap" in r["subject"].lower()]
    non_recaps = [r for r in today_results if "twitter recap" not in r["subject"].lower()]
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
    """发送飞书富文本卡片消息。"""
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

    # ── Step 1: 翻译所有邮件 ──────────────────────────────
    for i, mail in enumerate(emails, 1):
        print(f"  翻译中... (邮件 {i}/{len(emails)}: {mail['subject'][:40]})")
        mail["translated_body"] = translate_with_claude(mail["body"], mail["subject"])

    # ── Step 2: 生成 Markdown 存档 ────────────────────────
    print("  生成 Markdown 存档...")
    md_content = _build_markdown(emails, today)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)
    md_path = DAILY_DIR / f"{today}.md"
    md_path.write_text(md_content, encoding="utf-8")
    print(f"  已保存: {md_path}")

    # ── Step 3: 生成 HTML 展示页 ──────────────────────────
    print("  生成 HTML 展示页...")
    from render_html import save_html

    html_path = save_html(emails, DAILY_DIR, today)
    print(f"  HTML 已保存: {html_path}")

    # 复制到 public/ai-news/ 供 Vercel 部署
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    public_html = PUBLIC_DIR / f"{today}.html"
    shutil.copy2(html_path, public_html)
    _update_index_json()
    print(f"  已复制到 Vercel public 目录: {public_html}")

    html_url = f"{VERCEL_URL.rstrip('/')}/ai-news/{today}.html"

    # ── Step 4: 生成小红书内容 ────────────────────────────
    print("  生成小红书图文...")
    from render_xiaohongshu import save_xiaohongshu

    # 收集所有翻译块供小红书图片使用
    all_blocks: list[dict] = []
    for mail in emails:
        blocks = _parse_translated_blocks(mail["translated_body"])
        for b in blocks:
            b["title"] = mail["subject"]  # 用邮件标题作为卡片标题
        all_blocks.extend(blocks[:3])  # 每封邮件最多3个块

    xhs_output_dir = XHS_DIR / today
    img_path, caption_path = save_xiaohongshu(emails, all_blocks, xhs_output_dir, today)

    # ── Step 5: 推送到飞书 ────────────────────────────────
    print("  推送到飞书...")
    date_display = date.fromisoformat(today).strftime("%Y年%m月%d日")
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
    summary_lines.append(f"Markdown 存档: daily/{today}.md")

    summary = "\n".join(summary_lines)
    _send_feishu_rich(
        title=f"AI News 双语日报 | {date_display}",
        summary=summary,
        url=html_url,
    )
    print("  已推送到飞书")

    # ── Step 6: 写日志 ───────────────────────────────────
    log_path = LOG_DIR / f"{today}.log"
    log_path.write_text(
        f"[{today}] 处理了 {len(emails)} 封 AI news 邮件\n"
        f"  Markdown: {md_path}\n"
        f"  HTML: {html_path}\n"
        f"  HTML URL: {html_url}\n"
        f"  Xiaohongshu: {xhs_output_dir}\n",
        encoding="utf-8",
    )

    print(f"\n  {'='*50}")
    print(f"  处理完成!")
    print(f"  Markdown:    {md_path}")
    print(f"  HTML (本地): {html_path}")
    print(f"  HTML (线上): {html_url}")
    print(f"  小红书图片:  {img_path}")
    print(f"  小红书文案:  {caption_path}")
    print(f"  {'='*50}")


if __name__ == "__main__":
    main()
