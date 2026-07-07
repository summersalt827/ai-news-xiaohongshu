#!/usr/bin/env python3
"""为 AI News 双语日报生成小红书图文内容（图片 + 文案）。"""

from __future__ import annotations

import textwrap
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# 小红书推荐图片尺寸 3:4
IMG_WIDTH = 1080
IMG_HEIGHT = 1440

# 颜色
BG_COLOR = (250, 248, 255)  # 浅紫白背景
ACCENT = (102, 126, 234)     # 紫色强调
DARK = (51, 51, 51)
MID = (119, 119, 119)
WHITE = (255, 255, 255)
CARD_BG = (255, 255, 255)
TAG_BG_EN = (227, 242, 253)
TAG_BG_ZH = (252, 228, 236)
TAG_TEXT_EN = (25, 118, 210)
TAG_TEXT_ZH = (198, 40, 40)


def _get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """尝试加载系统字体，回退到默认。"""
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Light.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/PingFang SC.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                return ImageFont.truetype(fp, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """按像素宽度换行。"""
    lines: list[str] = []
    current = ""
    for char in text:
        test = current + char
        bbox = font.getbbox(test)
        if bbox is None:
            continue
        w = bbox[2] - bbox[0]
        if w > max_width and current:
            lines.append(current)
            current = char
        else:
            current = test
    if current:
        lines.append(current)
    return lines


def _draw_gradient_bg(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    """绘制渐变背景。"""
    for y in range(height):
        ratio = y / height
        r = int(250 - ratio * 20)
        g = int(248 - ratio * 15)
        b = int(255 - ratio * 10)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def generate_image(content_blocks: list[dict], today: str, output_path: Path) -> None:
    """生成一张小红书风格的长图。

    content_blocks: [{"title": str, "original": str, "translation": str}, ...]
    """
    img = Image.new("RGB", (IMG_WIDTH, IMG_HEIGHT), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # 顶部渐变装饰条
    for y in range(20):
        ratio = y / 20
        r = int(102 + (250 - 102) * ratio)
        g = int(126 + (248 - 126) * ratio)
        b = int(234 + (255 - 234) * ratio)
        draw.line([(0, y), (IMG_WIDTH, y)], fill=(r, g, b))

    y = 60
    margin = 60
    content_width = IMG_WIDTH - margin * 2

    # 标题
    title_font = _get_font(52, bold=True)
    date_font = _get_font(28)
    subtitle_font = _get_font(24)

    draw.text((margin, y), "AI News 双语日报", fill=ACCENT, font=title_font)
    y += 70

    date_display = date.fromisoformat(today).strftime("%Y年%m月%d日")
    draw.text((margin, y), date_display, fill=MID, font=date_font)
    y += 40

    draw.text((margin, y), "中英对照 · 每日AI资讯精选", fill=MID, font=subtitle_font)
    y += 60

    # 分隔线
    draw.line([(margin, y), (IMG_WIDTH - margin, y)], fill=(220, 220, 230), width=2)
    y += 40

    # 内容卡片
    body_font = _get_font(26)
    small_font = _get_font(22)
    tag_font = _get_font(20)

    for block in content_blocks:
        card_y_start = y

        # 卡片背景
        title = block.get("title", "")
        original = block.get("original", "")
        translation = block.get("translation", "")

        # 估算卡片高度
        title_lines = _wrap_text(title, _get_font(30, bold=True), content_width - 40)
        en_lines = _wrap_text(original, body_font, content_width - 60)
        zh_lines = _wrap_text(translation, body_font, content_width - 60)

        card_height = (
            50  # padding top
            + len(title_lines) * 42
            + 20
            + len(en_lines) * 38
            + 20
            + len(zh_lines) * 38
            + 50
        )  # padding bottom

        # 检查是否够空间，不够就新开一页（实际应该生成多图，这里简化）
        if y + card_height > IMG_HEIGHT - 100:
            break

        # 绘制卡片
        card_rect = [(margin, y), (IMG_WIDTH - margin, y + card_height)]
        draw.rounded_rectangle(card_rect, radius=16, fill=CARD_BG, outline=(230, 230, 240), width=1)
        y += 30

        # 标题
        title_f = _get_font(30, bold=True)
        for line in title_lines:
            draw.text((margin + 30, y), line, fill=DARK, font=title_f)
            y += 42

        y += 10

        # EN 标签 + 英文原文
        if original:
            tag_box = [(margin + 30, y), (margin + 72, y + 28)]
            draw.rounded_rectangle(tag_box, radius=4, fill=TAG_BG_EN)
            draw.text((margin + 34, y + 3), "EN", fill=TAG_TEXT_EN, font=tag_font)

            for line in en_lines:
                draw.text((margin + 86, y + 3), line, fill=(100, 100, 100), font=body_font)
                y += 38
            y += 10

        # 中 标签 + 中文翻译
        if translation:
            tag_box = [(margin + 30, y), (margin + 72, y + 28)]
            draw.rounded_rectangle(tag_box, radius=4, fill=TAG_BG_ZH)
            draw.text((margin + 34, y + 3), "中", fill=TAG_TEXT_ZH, font=tag_font)

            for line in zh_lines:
                draw.text((margin + 86, y + 3), line, fill=DARK, font=body_font)
                y += 38

        y = card_y_start + card_height + 24

    # 底部
    y = max(y + 20, IMG_HEIGHT - 150)
    draw.line([(margin, y), (IMG_WIDTH - margin, y)], fill=(220, 220, 230), width=1)
    y += 30
    footer_font = _get_font(22)
    draw.text((margin, y), "AI News 双语日报 · 每日自动生成", fill=(180, 180, 190), font=footer_font)
    y += 30
    hashtags = "#AI新闻 #双语阅读 #每日资讯 #人工智能"
    draw.text((margin, y), hashtags, fill=ACCENT, font=footer_font)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output_path), quality=95)
    print(f"  小红书图片已保存: {output_path}")


def generate_caption(emails: list[dict], today: str) -> str:
    """生成小红书文案（带 emoji 和 hashtags）。"""
    date_display = date.fromisoformat(today).strftime("%Y年%m月%d日")

    lines = [
        f"AI News 双语日报 | {date_display}",
        "",
        "今天整理了最新AI行业动态，中英对照，一起学习～",
        "",
    ]

    for i, mail in enumerate(emails[:3], 1):  # 最多展示3封
        subject = mail.get("subject", "AI News")
        lines.append(f" {i}. {subject}")
        # 截取正文前80字
        body = mail.get("translated_body") or mail.get("body", "")
        preview = body[:120].replace("\n", " ").strip()
        lines.append(f"   {preview}...")
        lines.append("")

    lines.extend([
        "---",
        "",
        "完整中英对照内容已同步到飞书 ",
        "每天自动更新，欢迎关注 ",
        "",
        "#AI新闻 #人工智能 #英语学习 #双语阅读",
        "#每日打卡 #科技资讯 #自我提升 #知识分享",
    ])

    return "\n".join(lines)


def save_xiaohongshu(
    emails: list[dict], translated_blocks: list[dict], output_dir: Path, today: str
) -> tuple[Path, Path]:
    """生成小红书图片和文案，保存到输出目录。

    返回 (image_path, caption_path)。
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # 生成图片
    img_path = output_dir / f"{today}.jpg"
    generate_image(translated_blocks, today, img_path)

    # 生成文案
    caption = generate_caption(emails, today)
    caption_path = output_dir / f"{today}_caption.txt"
    caption_path.write_text(caption, encoding="utf-8")
    print(f"  小红书文案已保存: {caption_path}")

    return img_path, caption_path
