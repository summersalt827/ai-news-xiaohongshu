#!/usr/bin/env python3
"""小白速览卡片生成模块 — 蒸馏 → 去重 → HTML 卡片 → Chrome 截图 → 2×2 封面。

流程:
  1. distill_for_beginners()  — Claude 蒸馏 4 条大白话摘要
  2. _deduplicate_items()     — 与历史卡片去重
  3. _generate_card_html()    — 生成单张卡片 HTML
  4. _screenshot_html()       — Chrome headless 截图
  5. _generate_cover_html()   — 2×2 网格封面 HTML
  6. save_xiaobai_cards()     — 主入口，串联所有步骤
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import textwrap
import urllib.request
from pathlib import Path
from typing import Any

os.environ.setdefault("no_proxy", "*")  # 国内直连，走代理反而 TLS 失败

# 复用 fetch_ai_news 的 API 配置
BASE_URL = os.environ.get("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# 卡片设计常量
CARD_WIDTH = 1080
CARD_SCALE = 2  # @2x 高清截图

# 中文停用词（去重时剔除）
CN_STOPWORDS = {
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着",
    "没有", "看", "好", "自己", "这", "他", "她", "它", "们", "那", "些",
    "模型", "发布", "推出", "生成", "免费", "功能", "支持", "使用",
    "可以", "能够", "通过", "进行", "提供", "包括", "以及", "一个",
    "这个", "今年", "目前", "已经", "将", "将", "还", "更", "从",
    "与", "等", "为", "被", "但", "而", "或", "及", "所", "其",
    "每", "让", "向", "对", "中", "后", "前", "大", "新", "最",
}

# AI 领域高频专有名词（去重时适度保护，不参与停用词过滤）
PROTECTED_TERMS = {
    "claude", "fable", "openai", "gemma", "gpt", "chatgpt",
    "anthropic", "google", "meta", "deepseek", "cursor", "cline",
    "cognition", "devin", "agent", "benchmark", "sora", "veo",
}


def _call_claude(system_prompt: str, user_text: str, max_tokens: int = 2048) -> str:
    """调用 Claude API 并返回文本响应。"""
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
        print(f"  [xiaobai] Claude API call failed: {exc}")
        return ""

    parts: list[str] = []
    for block in body.get("content", []):
        if block.get("type") == "text":
            parts.append(block["text"])
    return "\n\n".join(parts)


# ── 蒸馏 ────────────────────────────────────────────────────────

def distill_for_beginners(
    translated_text: str, enrichment_context: str = "", subject: str = ""
) -> list[dict[str, str]]:
    """将 AI 新闻蒸馏为 4 条小白能看懂的大白话摘要。

    每条: {"title": str, "summary": str, "why_care": str, "emoji": str}
    """
    enrichment_block = ""
    if enrichment_context:
        enrichment_block = (
            "\n\n## 外部补充信息（供参考，可综合进摘要）\n\n" + enrichment_context
        )

    system_prompt = (
        '你是一个AI科普作者，擅长把复杂技术新闻用大白话讲清楚。'
        '你的读者是完全不懂AI的普通人。\n\n'
        '要求：\n'
        '- 挑选4条最重要的新闻，每条提炼成一个独立要点\n'
        '- 标题：用大白话，10-20字，有吸引力，像小红书标题\n'
        '- 摘要：2-3句话，讲清楚发生了什么，用生活类比\n'
        '- 为什么和普通人有关：1-2句话，说明实际影响\n'
        '- 专业术语必须加括号用大白话解释\n'
        '- 每个要点配一个相关emoji\n'
        '- 不要堆砌术语，不要写业内人士认为这类废话\n'
        '- 如果外部补充信息中有邮件未覆盖的新视角，优先采用\n\n'
        '输出JSON数组格式（不要markdown代码块）：\n'
        '[{"title":"...","summary":"...","why_care":"...","emoji":"..."}]\n'
        '必须恰好4条。'
    )

    user_text = translated_text[:5000] + enrichment_block

    raw = _call_claude(system_prompt, user_text, max_tokens=2048)
    if not raw:
        return _fallback_distill(translated_text)

    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```\w*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                items = json.loads(m.group(0))
            except json.JSONDecodeError:
                return _fallback_distill(translated_text)
        else:
            return _fallback_distill(translated_text)

    if not isinstance(items, list) or len(items) == 0:
        return _fallback_distill(translated_text)

    # 确保每条都有 required fields
    valid = []
    for item in items:
        if isinstance(item, dict) and item.get("title"):
            valid.append({
                "title": str(item.get("title", "")),
                "summary": str(item.get("summary", "")),
                "why_care": str(item.get("why_care", "")),
                "emoji": str(item.get("emoji", "📌")),
            })
    return valid[:4]


def _fallback_distill(text: str) -> list[dict[str, str]]:
    """蒸馏失败时的后备方案：直接从文本中提取要点。"""
    # 按双换行拆分，取前几个非空段落
    paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
    items: list[dict[str, str]] = []
    for i, p in enumerate(paras[:4]):
        title = p.split("\n")[0][:40]
        if len(title) > 20:
            title = title[:20] + "..."
        items.append({
            "title": title or f"AI 新闻要点 {i + 1}",
            "summary": p[:200],
            "why_care": "关注AI发展，了解技术如何改变日常生活。",
            "emoji": ["🤖", "📰", "💡", "🔥"][i % 4],
        })
    return items[:4]


# ── 去重 ────────────────────────────────────────────────────────

def _extract_keywords(text: str) -> dict[str, float]:
    """从文本中提取加权关键词。EN词 ×2，CN bigram ×1。"""
    tokens: dict[str, float] = {}

    # 英文词汇（2+ 字母，转小写）
    for m in re.finditer(r"[a-zA-Z]{2,}", text):
        word = m.group(0).lower()
        if word not in CN_STOPWORDS:
            tokens[word] = tokens.get(word, 0) + 2.0

    # 中文 bigram 滑窗
    chinese_only = re.sub(r"[a-zA-Z0-9\s\W]", "", text)
    for i in range(len(chinese_only) - 1):
        bigram = chinese_only[i : i + 2]
        if bigram not in CN_STOPWORDS and len(bigram) == 2:
            tokens[bigram] = tokens.get(bigram, 0) + 1.0

    return tokens


def _weighted_overlap(item1: dict[str, str], item2: dict[str, str]) -> float:
    """计算两个条目的加权重叠分数。"""
    text1 = item1.get("title", "") + " " + item1.get("summary", "")
    text2 = item2.get("title", "") + " " + item2.get("summary", "")

    kw1 = _extract_keywords(text1)
    kw2 = _extract_keywords(text2)

    if not kw1 or not kw2:
        return 0.0

    score = 0.0
    for word, weight in kw1.items():
        if word in kw2:
            score += min(weight, kw2[word])

    # 对受保护术语的匹配给予额外加分
    for term in PROTECTED_TERMS:
        if term in text1.lower() and term in text2.lower():
            score += 1.0

    return score


def _deduplicate_items(
    items: list[dict[str, str]], xhs_base_dir: Path
) -> list[dict[str, str]]:
    """与历史所有小白卡片比对，过滤重复条目。

    遍历 xiaohongshu/*/xiaobai/ 中的历史 HTML 文件，
    提取 <h1> 和 .card-title 文本作为历史标题。
    加权重叠 >= 4 视为重复。
    """
    history_titles: list[str] = []

    if xhs_base_dir.exists():
        for html_file in sorted(xhs_base_dir.glob("*/xiaobai/0?-*.html")):
            try:
                content = html_file.read_text(encoding="utf-8")
                # 提取标题
                h1_matches = re.findall(r"<h1[^>]*>(.*?)</h1>", content, re.DOTALL)
                card_matches = re.findall(
                    r'class="[^"]*card-title[^"]*"[^>]*>(.*?)</', content, re.DOTALL
                )
                for m in h1_matches + card_matches:
                    title = re.sub(r"<[^>]+>", "", m).strip()
                    if title and len(title) >= 4:
                        history_titles.append(title)
            except Exception:
                continue

    if not history_titles:
        print("  [xiaobai] 无历史卡片，跳过去重")
        return items

    print(f"  [xiaobai] 与 {len(history_titles)} 条历史卡片去重...")
    kept: list[dict[str, str]] = []
    for item in items:
        is_dup = False
        for hist_title in history_titles:
            hist_item = {"title": hist_title, "summary": ""}
            if _weighted_overlap(item, hist_item) >= 4:
                print(f"  [xiaobai] 去重拦截: {item['title'][:40]}")
                is_dup = True
                break
        if not is_dup:
            kept.append(item)

    return kept


# ── HTML 卡片生成 ────────────────────────────────────────────────

def _slugify(text: str) -> str:
    """生成英文/拼音 slug，用于文件名。"""
    # 移除非字母数字，取前 30 字符
    slug = re.sub(r"[^a-zA-Z0-9一-鿿]", "-", text)
    return slug[:30].strip("-") or "card"


def _generate_card_html(item: dict[str, str], index: int) -> str:
    """生成一张小白卡片的完整 HTML。"""
    title = item.get("title", "")
    summary = item.get("summary", "")
    why_care = item.get("why_care", "")
    emoji = item.get("emoji", "📌")

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="utf-8">
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap');
      body {{
        font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
        background: #faf9f5;
        display: flex; justify-content: center; align-items: center;
        min-height: 100vh; padding: 40px;
      }}
      .card {{
        max-width: 960px; width: 100%;
        background: #ffffff;
        border-radius: 20px;
        padding: 48px 52px;
        box-shadow: 0 2px 20px rgba(0,0,0,0.06);
        border: 1px solid #f0ede5;
      }}
      .card-header {{
        display: flex; align-items: center; gap: 16px; margin-bottom: 24px;
      }}
      .emoji {{ font-size: 42px; line-height: 1; }}
      h1 {{
        font-size: 32px; font-weight: 700; color: #2d2d2d;
        line-height: 1.3; letter-spacing: -0.01em;
      }}
      .summary {{
        font-size: 20px; color: #555; line-height: 1.7; margin-bottom: 28px;
      }}
      .insight-box {{
        background: linear-gradient(135deg, #fff7f0, #fff3e8);
        border-left: 4px solid #d97757;
        border-radius: 12px;
        padding: 20px 24px; margin-top: 8px;
      }}
      .insight-label {{
        font-size: 16px; font-weight: 700; color: #d97757;
        text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px;
      }}
      .insight-text {{
        font-size: 19px; color: #4a3728; line-height: 1.65;
      }}
      .card-number {{
        font-size: 14px; color: #c4b5a5; text-align: right; margin-top: 24px;
        letter-spacing: 0.05em;
      }}
    </style>
    </head>
    <body>
    <div class="card">
      <div class="card-header">
        <span class="emoji">{emoji}</span>
        <h1>{title}</h1>
      </div>
      <p class="summary">{summary}</p>
      <div class="insight-box">
        <div class="insight-label">为什么和普通人有关</div>
        <p class="insight-text">{why_care}</p>
      </div>
      <div class="card-number">AI 小白速览 · {index}/4</div>
    </div>
    </body>
    </html>
    """)


def _generate_cover_html(items: list[dict[str, str]], date_str: str) -> str:
    """生成 2×2 封面 HTML。"""
    date_display = date_str.replace("-", " / ")

    # 生成 4 个网格项的 HTML
    grid_items: list[str] = []
    for i, item in enumerate(items):
        emoji = item.get("emoji", "📌")
        title = item.get("title", "")
        summary = item.get("summary", "")[:80]
        grid_items.append(f"""\
        <div class="grid-item">
          <div class="grid-emoji">{emoji}</div>
          <div class="grid-title">{title}</div>
          <div class="grid-summary">{summary}</div>
        </div>
        """)

    grid_html = "\n".join(grid_items)
    item_count = len(items)

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
    <meta charset="utf-8">
    <style>
      * {{ margin: 0; padding: 0; box-sizing: border-box; }}
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
      body {{
        font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', sans-serif;
        background: #faf9f5;
        width: 1080px; min-height: 1440px;
      }}
      .cover {{
        padding: 60px 52px 40px;
        display: flex; flex-direction: column; min-height: 1440px;
      }}
      .header {{ text-align: center; margin-bottom: 48px; }}
      .header h1 {{
        font-size: 46px; font-weight: 800; color: #2d2d2d;
        letter-spacing: -0.02em; margin-bottom: 8px;
      }}
      .header .accent {{ color: #d97757; }}
      .header .date {{
        font-size: 20px; color: #999; letter-spacing: 0.05em;
      }}
      .grid {{
        display: grid; grid-template-columns: 1fr 1fr;
        grid-template-rows: 1fr 1fr;
        gap: 20px; flex: 1; margin-bottom: 40px;
      }}
      .grid-item {{
        background: #ffffff;
        border-radius: 16px;
        padding: 28px 24px;
        border: 1px solid #f0ede5;
        display: flex; flex-direction: column;
        box-shadow: 0 1px 12px rgba(0,0,0,0.04);
      }}
      .grid-emoji {{ font-size: 36px; margin-bottom: 12px; }}
      .grid-title {{
        font-size: 24px; font-weight: 700; color: #2d2d2d;
        line-height: 1.3; margin-bottom: 8px;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
        overflow: hidden;
      }}
      .grid-summary {{
        font-size: 17px; color: #777; line-height: 1.5;
        display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
        overflow: hidden;
      }}
      .footer {{
        text-align: center; padding-top: 24px;
        border-top: 1px solid #e8e4da;
      }}
      .footer .insight-box {{
        background: linear-gradient(135deg, #fff7f0, #fff3e8);
        border-radius: 12px; padding: 18px 28px; margin-bottom: 20px;
        display: inline-block; text-align: left; max-width: 700px;
      }}
      .footer .insight-box .label {{
        font-size: 15px; font-weight: 700; color: #d97757; margin-bottom: 6px;
      }}
      .footer .insight-box p {{
        font-size: 17px; color: #4a3728; line-height: 1.5;
      }}
      .footer .hashtags {{
        font-size: 17px; color: #c4b5a5; letter-spacing: 0.03em;
      }}
    </style>
    </head>
    <body>
    <div class="cover">
      <div class="header">
        <h1>AI 小白速览 <span class="accent">{date_display}</span></h1>
        <div class="date">{item_count} 条 AI 新闻 · 一看就懂</div>
      </div>
      <div class="grid">
        {grid_html}
      </div>
      <div class="footer">
        <div class="insight-box">
          <div class="label">INSIGHT</div>
          <p>AI不是魔法，是正在改变每个人生活的工具箱。每天4条，跟上AI时代的脚步。</p>
        </div>
        <div class="hashtags">#AI新闻 #小白必看 #科技资讯 #每日打卡 #人工智能</div>
      </div>
    </div>
    </body>
    </html>
    """)


# ── Chrome 截图 ─────────────────────────────────────────────────

def _screenshot_html(html_content: str, png_path: Path) -> bool:
    """用 Chrome headless 将 HTML 截图保存为 PNG。

    要求：png_path 必须通过 Path.resolve().as_uri() 编码中文路径。
    """
    png_path.parent.mkdir(parents=True, exist_ok=True)

    # 写临时 HTML 文件
    html_path = png_path.with_suffix(".html")
    html_path.write_text(html_content, encoding="utf-8")

    # Chrome headless 截图
    uri = html_path.resolve().as_uri()
    cmd = [
        CHROME_PATH,
        "--headless=new",
        f"--screenshot={png_path.resolve()}",
        "--window-size=1080,800",
        "--force-device-scale-factor=2",
        "--hide-scrollbars",
        uri,
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if png_path.exists() and png_path.stat().st_size > 10000:
            return True
        print(f"  [xiaobai] Chrome 截图失败: {result.stderr[:300]}")
        return False
    except FileNotFoundError:
        print("  [xiaobai] Chrome 未找到，请安装 Google Chrome")
        return False
    except subprocess.TimeoutExpired:
        print("  [xiaobai] Chrome 截图超时")
        return False
    except Exception as exc:
        print(f"  [xiaobai] Chrome 截图异常: {exc}")
        return False
    finally:
        # 保留 HTML 文件用于调试，后续 cleanup 会删除
        pass


# ── 文案 ────────────────────────────────────────────────────────

def generate_xiaobai_caption(
    items: list[dict[str, str]], emails: list[dict], date_str: str
) -> str:
    """生成小红书发布文案，标题优先使用邮件原始 subject。"""
    # 日期显示
    parts = date_str.split("-")
    date_display = f"{parts[0]}年{int(parts[1])}月{int(parts[2])}日" if len(parts) == 3 else date_str

    # 用邮件原始 subject 作为标题
    if emails and emails[0].get("subject"):
        raw_subject = emails[0]["subject"]
        # 去掉 [AINews] 前缀
        subject = re.sub(r"\[?AINews\]?\s*", "", raw_subject, flags=re.IGNORECASE).strip()
        if len(subject) > 60:
            subject = subject[:60] + "..."
    else:
        subject = "今日 AI 小白速览"

    lines = [
        f"{subject} | {date_display}",
        "",
        "整理了最新AI圈大事，用大白话讲给你听～",
        "",
    ]

    for item in items:
        emoji = item.get("emoji", "📌")
        title = item.get("title", "")
        lines.append(f"{emoji} {title}")

    lines.extend([
        "",
        "---",
        "",
        "#AI新闻 #小白必看 #科技资讯",
        "#每日打卡 #人工智能 #效率工具",
    ])

    return "\n".join(lines)


# ── 清理 ────────────────────────────────────────────────────────

def _cleanup_old_cards(output_dir: Path, current_pngs: list[Path]) -> None:
    """删除 output_dir 中不属于当前批次的旧卡片。"""
    if not output_dir.exists():
        return

    current_names = {p.name for p in current_pngs}
    for f in sorted(output_dir.iterdir()):
        if f.is_file() and f.suffix in (".png", ".html"):
            if f.name in current_names or f.name == "cover.png":
                continue
            # 匹配 0?-* 模式（卡片文件）或旧 HTML
            if re.match(r"0\d-", f.name) or f.suffix == ".html":
                try:
                    f.unlink()
                    print(f"  [xiaobai] 清理旧文件: {f.name}")
                except OSError:
                    pass


# ── 主入口 ──────────────────────────────────────────────────────

def save_xiaobai_cards(
    items: list[dict[str, str]],
    output_dir: Path,
    emails: list[dict],
    effective_date: str,
) -> list[Path]:
    """生成小白卡片、封面和文案，返回所有 PNG 路径。

    参数:
      items: 蒸馏后的摘要列表（4条）
      output_dir: 输出父目录（如 xiaohongshu/2026-06-13/）
      emails: 原始邮件列表（用于提取 subject）
      effective_date: 日期字符串 YYYY-MM-DD

    返回: [card1.png, card2.png, card3.png, card4.png, cover.png]
    """
    xiaobai_dir = output_dir / "xiaobai"
    xiaobai_dir.mkdir(parents=True, exist_ok=True)

    png_paths: list[Path] = []

    # 1. 生成每张卡片
    for i, item in enumerate(items, 1):
        slug = _slugify(item.get("title", f"card-{i}"))
        html_content = _generate_card_html(item, i)
        png_path = xiaobai_dir / f"0{i}-{slug}.png"

        print(f"  [xiaobai] 生成卡片 {i}/4: {item['title'][:30]}...")
        if _screenshot_html(html_content, png_path):
            png_paths.append(png_path)
        else:
            print(f"  [xiaobai] 卡片 {i} 截图失败，跳过")

    # 2. 生成 2×2 封面
    if items:
        cover_html = _generate_cover_html(items, effective_date)
        cover_path = xiaobai_dir / "cover.png"
        print("  [xiaobai] 生成 2×2 封面...")
        if _screenshot_html(cover_html, cover_path):
            png_paths.append(cover_path)

    # 3. 生成文案
    caption = generate_xiaobai_caption(items, emails, effective_date)
    caption_path = xiaobai_dir / "xiaobai_caption.txt"
    caption_path.write_text(caption, encoding="utf-8")
    print(f"  [xiaobai] 文案已保存: {caption_path}")

    # 4. 清理旧卡片
    _cleanup_old_cards(xiaobai_dir, png_paths)

    return png_paths
