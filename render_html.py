#!/usr/bin/env python3
"""为 AI News 双语内容生成精美 HTML 展示页面。"""

from __future__ import annotations

import html
from datetime import date
from pathlib import Path

CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
               "Hiragino Sans GB", "Microsoft YaHei", "Helvetica Neue", sans-serif;
  background: #f5f5f5; color: #333; line-height: 1.8;
}
.container { max-width: 800px; margin: 0 auto; padding: 24px 20px 60px; }
.header {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: #fff; padding: 48px 32px; border-radius: 16px; margin-bottom: 32px;
  text-align: center;
}
.header h1 { font-size: 28px; font-weight: 700; margin-bottom: 8px; }
.header .date { font-size: 14px; opacity: 0.85; }
.header .badge {
  display: inline-block; background: rgba(255,255,255,0.2);
  padding: 4px 14px; border-radius: 20px; font-size: 12px;
  margin-top: 12px;
}
.email-card {
  background: #fff; border-radius: 12px; padding: 32px;
  margin-bottom: 24px; box-shadow: 0 2px 12px rgba(0,0,0,0.06);
}
.email-card h2 {
  font-size: 20px; color: #333; margin-bottom: 12px;
  padding-bottom: 12px; border-bottom: 2px solid #f0f0f0;
}
.email-meta {
  display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px;
  color: #888; margin-bottom: 24px;
}
.email-meta span { display: inline-flex; align-items: center; gap: 4px; }
.content-block { margin-bottom: 20px; }
.content-block .original {
  background: #f8f9fa; border-left: 3px solid #667eea;
  padding: 12px 16px; border-radius: 0 8px 8px 0; margin-bottom: 8px;
  color: #555; font-style: italic;
}
.content-block .translation {
  padding: 8px 16px; color: #333;
}
.footer {
  text-align: center; color: #aaa; font-size: 12px;
  margin-top: 40px; padding-top: 20px; border-top: 1px solid #eee;
}
.tag {
  display: inline-block; padding: 2px 10px; border-radius: 4px;
  font-size: 11px; font-weight: 600; margin-right: 6px;
}
.tag-en { background: #e3f2fd; color: #1976d2; }
.tag-zh { background: #fce4ec; color: #c62828; }
.divider {
  text-align: center; color: #ddd; margin: 20px 0;
  font-size: 18px; letter-spacing: 8px;
}
@media (max-width: 600px) {
  .container { padding: 12px 12px 40px; }
  .header { padding: 32px 20px; border-radius: 12px; }
  .header h1 { font-size: 22px; }
  .email-card { padding: 20px; }
}
"""


def _escape(text: str) -> str:
    return html.escape(text)


def _parse_bilingual(content: str) -> list[dict]:
    """解析 Claude 翻译后的中英对照文本，按段落分为 original/translation 块。

    翻译格式约定:
      > English original here...
      中文翻译在这里...

    或

      > 中文原文...
      English translation here...
    """
    blocks: list[dict] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith(">"):
            origin_lines = [line[1:].strip()]
            trans_lines: list[str] = []
            i += 1
            while i < len(lines):
                nl = lines[i].strip()
                if nl.startswith(">"):
                    break
                if nl:
                    trans_lines.append(nl)
                elif trans_lines:
                    break
                i += 1
            blocks.append({
                "original": " ".join(origin_lines),
                "translation": " ".join(trans_lines) if trans_lines else "",
            })
        else:
            if line:
                # 普通段落，可能是翻译或说明
                blocks.append({"original": "", "translation": line})
            i += 1
    return blocks


def render_html(emails: list[dict], today: str) -> str:
    """生成完整的 HTML 页面字符串。"""
    today_obj = date.fromisoformat(today)
    date_display = today_obj.strftime("%Y年%m月%d日")

    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append(f"<title>AI News 双语日报 - {date_display}</title>")
    parts.append(f"<style>{CSS}</style>")
    parts.append("</head>")
    parts.append("<body>")
    parts.append('<div class="container">')

    # Header
    parts.append('<div class="header">')
    parts.append("<h1>AI News 双语日报</h1>")
    parts.append(f'<div class="date">{date_display}</div>')
    parts.append(
        f'<div class="badge">{len(emails)} 封 AI 新闻邮件 · 中英对照</div>'
    )
    parts.append("</div>")

    # Email cards
    for i, mail in enumerate(emails, 1):
        parts.append('<div class="email-card">')
        parts.append(f"<h2>{_escape(mail['subject'])}</h2>")
        parts.append('<div class="email-meta">')
        parts.append(f"<span>发件人: {_escape(mail['sender'])}</span>")
        if mail.get("date"):
            time_str = mail["date"].strftime("%Y-%m-%d %H:%M")
            parts.append(f"<span>{time_str}</span>")
        parts.append("</div>")

        # 解析并渲染双语内容
        body = mail.get("translated_body") or mail.get("body", "")
        blocks = _parse_bilingual(body)

        for block in blocks:
            original = block["original"].strip()
            translation = block["translation"].strip()
            if original:
                parts.append('<div class="content-block">')
                parts.append(
                    f'<div class="original"><span class="tag tag-en">EN</span> '
                    f"{_escape(original)}</div>"
                )
                if translation:
                    parts.append(
                        f'<div class="translation"><span class="tag tag-zh">中</span> '
                        f"{_escape(translation)}</div>"
                    )
                parts.append("</div>")
            elif translation:
                parts.append('<div class="content-block">')
                parts.append(f'<div class="translation">{_escape(translation)}</div>')
                parts.append("</div>")

        parts.append("</div>")

    # Footer
    parts.append('<div class="footer">')
    parts.append(f"<p>AI News 双语日报 · 自动生成于 {date_display}</p>")
    parts.append("</div>")

    parts.append("</div>")
    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts)


def save_html(emails: list[dict], output_dir: Path, today: str) -> Path:
    """生成 HTML 并保存到指定目录。"""
    html_content = render_html(emails, today)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{today}.html"
    path.write_text(html_content, encoding="utf-8")
    return path
