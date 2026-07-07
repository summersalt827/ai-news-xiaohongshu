#!/usr/bin/env python3
"""小红书自动发布脚本 — 用 Playwright 打开创作中心，上传图片，填写文案。

用法:
  python3 publish_xiaohongshu_auto.py <日期> [--login-only] [--force]

示例:
  python3 publish_xiaohongshu_auto.py 2026-06-13
  python3 publish_xiaohongshu_auto.py 2026-06-13 --login-only
  python3 publish_xiaohongshu_auto.py 2026-06-13 --force
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 项目路径配置 — publish 脚本在 xhs_publish/ 下，PROJECT_DIR 指向上级
PROJECT_DIR = Path(__file__).resolve().parent.parent  # ai-news-xiaohongshu 根目录
XHS_DIR = PROJECT_DIR / "xiaohongshu"
USER_DATA_DIR = PROJECT_DIR / ".playwright-data"

CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"


def _find_publish_files(date_str: str) -> tuple[list[Path], Path | None]:
    """查找指定日期的图片和文案文件。

    返回: (图片路径列表, 文案路径)
    """
    date_dir = XHS_DIR / date_str
    xiaobai_dir = date_dir / "xiaobai"

    images: list[Path] = []
    caption_file: Path | None = None

    if xiaobai_dir.exists():
        # 封面第一，然后卡片按编号排序
        cover = xiaobai_dir / "cover.png"
        cards = sorted(xiaobai_dir.glob("0?-*.png"))
        if cover.exists():
            images.append(cover)
        images.extend(c for c in cards if c not in images)

        cap = xiaobai_dir / "xiaobai_caption.txt"
        if cap.exists():
            caption_file = cap

    # AI Skills 格式优先: xhs-skill-cover.png + xhs-skill-p1~p4.png
    skill_cover = date_dir / "xhs-skill-cover.png"
    skill_pages = sorted(date_dir.glob("xhs-skill-p?.png"))
    if skill_cover.exists() and skill_pages:
        images.append(skill_cover)
        images.extend(skill_pages)
        cap = date_dir / "xhs-skill-caption.md"
        if cap.exists():
            caption_file = cap
        return images, caption_file

    # 卡片 PNG 格式 (cover + 4 card PNGs)
    card_pngs = sorted(date_dir.glob(f"{date_str}_card_*.png"))
    cover_png = date_dir / f"{date_str}_cover.png"
    if cover_png.exists() and card_pngs:
        images.append(cover_png)
        images.extend(card_pngs)
        cap = date_dir / f"{date_str}_combined_caption.txt"
        if cap.exists():
            caption_file = cap
        return images, caption_file

    # 如果 xiaobai 目录不存在或为空，尝试旧格式
    if not images:
        for f in sorted(date_dir.glob("*.jpg")) + sorted(date_dir.glob("*.png")):
            images.append(f)
        cap = date_dir / f"{date_str}_caption.txt"
        if cap.exists():
            caption_file = cap

    return images, caption_file


def _parse_caption(caption_path: Path) -> tuple[str, str]:
    """解析文案文件，第一行为标题，其余为正文。

    返回: (title, body)
    """
    text = caption_path.read_text(encoding="utf-8").strip()
    lines = text.split("\n")
    title = lines[0] if lines else ""
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
    return title, body


def run_publish(date_str: str, login_only: bool = False) -> None:
    """主发布流程。"""
    from playwright.sync_api import sync_playwright

    images, caption_file = _find_publish_files(date_str)

    if not images:
        print(f"❌ 未找到图片: xiaohongshu/{date_str}/xiaobai/")
        sys.exit(1)

    title = ""
    body = ""
    if caption_file:
        title, body = _parse_caption(caption_file)
    else:
        print(f"⚠️  未找到文案文件，将只上传图片")

    print(f"📕 小红书发布")
    print(f"  日期: {date_str}")
    print(f"  图片: {len(images)} 张")
    print(f"  标题: {title[:50]}...")

    USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
            viewport={"width": 1280, "height": 900},
            locale="zh-CN",
        )

        page = ctx.new_page()
        page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=30000)

        # 检查是否需要登录
        if "login" in page.url.lower() or "passport" in page.url.lower():
            print("\n🔐 需要登录小红书")
            print("   请在浏览器中扫码登录（60 秒超时）...")
            try:
                page.wait_for_url(
                    lambda u: "creator.xiaohongshu.com" in u,
                    timeout=60_000,
                )
                print("✅ 登录成功")
            except Exception:
                print("⚠️  登录超时，请在浏览器中手动登录 (60s)...")
                time.sleep(60)
                page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=30000)

        if login_only:
            print("✅ 已登录，cookie 已保存到 .playwright-data/")
            ctx.close()
            return

        # 等待发布页面加载
        time.sleep(2)

        try:
            # ── 上传图片 ──────────────────────────────────────
            print("📤 上传图片...")
            # 确保在图文模式
            img_tab = page.locator('.creator-tab.active:has-text("图文")').first
            if not img_tab.is_visible():
                tab_btn = page.locator('.creator-tab:has-text("图文")').first
                if tab_btn.is_visible():
                    tab_btn.click(force=True)
                    print("  ✅ 切换到图文模式")
                    page.wait_for_load_state("networkidle", timeout=10000)
                    time.sleep(2)

            time.sleep(1.5)
            # 找到接受图片的 file input（优先匹配 image 类型，排除视频）
            file_inputs = page.locator('input[type="file"]')
            img_input = None
            for j in range(file_inputs.count()):
                inp = file_inputs.nth(j)
                accept = inp.get_attribute("accept") or ""
                # 明确接受图片格式的 input
                if any(ext in accept for ext in [".png", ".jpg", ".jpeg", ".webp", "image"]):
                    img_input = inp
                    break
            if not img_input:
                # 回退：排除明显是视频的 input
                for j in range(file_inputs.count()):
                    inp = file_inputs.nth(j)
                    accept = inp.get_attribute("accept") or ""
                    if accept and "mp4" in accept:
                        continue
                    img_input = inp
                    break
            if not img_input:
                img_input = file_inputs.first

            img_strs = [str(img.resolve()) for img in images[:10]]
            img_input.set_input_files(img_strs)
            print(f"  ✅ 已选择 {len(img_strs)} 张图片")

            # 等待图片上传完成
            time.sleep(3)

            # ── 填写文案 ──────────────────────────────────────
            if title or body:
                print("📝 填写文案...")
                # 标题输入框
                title_input = page.locator('[placeholder*="标题"]').first
                if not title_input.is_visible():
                    title_input = page.locator('[class*="title"] input').first
                if title_input.is_visible() and title:
                    title_input.click()
                    title_input.fill("")
                    title_input.type(title, delay=50)
                    print(f"  ✅ 标题: {title[:40]}...")
                    time.sleep(0.5)

                # 正文输入框
                body_input = page.locator('[placeholder*="写"]').first
                if not body_input.is_visible():
                    body_input = page.locator('[contenteditable="true"]').first
                if body_input.is_visible() and body:
                    body_input.click()
                    body_input.type(body, delay=30)
                    print(f"  ✅ 正文已填入")
                    time.sleep(0.5)

            # ── 自动点击发布 ──────────────────────────────────
            print("🚀 自动发布中...")
            time.sleep(1)

            publish_clicked = False
            # Try multiple selectors for the publish button
            publish_selectors = [
                'button:has-text("发布")',
                '[class*="publish"] button',
                'button:has-text("发布笔记")',
                'div[class*="publish"]:has-text("发布")',
            ]
            for sel in publish_selectors:
                btn = page.locator(sel).first
                if btn.is_visible():
                    btn.click()
                    publish_clicked = True
                    print(f"  ✅ 点击发布按钮")
                    break

            if not publish_clicked:
                print("  ⚠️ 未找到发布按钮，浏览器保持打开 30s 供手动操作")
                time.sleep(30)
                ctx.close()
                return

            # 等待发布成功或确认弹窗
            time.sleep(2)

            # 处理可能的确认弹窗
            confirm_selectors = [
                'button:has-text("确定")',
                'button:has-text("确认")',
                'button:has-text("发布")',
            ]
            for sel in confirm_selectors:
                confirm_btn = page.locator(sel).first
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    print(f"  ✅ 确认发布")
                    time.sleep(1)
                    break

            # 等待发布结果
            success = False
            for _ in range(15):  # wait up to 15s
                time.sleep(1)
                # Check for success indicators
                if page.locator(':has-text("发布成功")').first.is_visible():
                    success = True
                    break
                if page.locator(':has-text("已发布")').first.is_visible():
                    success = True
                    break
                # Check if redirected back (publish complete)
                if "publish" not in page.url.lower():
                    # Likely redirected to notes page
                    success = True
                    break

            if success:
                print("🎉 发布成功！")
            else:
                print("⚠️ 发布状态未确认，请检查浏览器")

            # 显示几秒结果后自动关闭
            print("   3 秒后自动关闭浏览器...")
            time.sleep(3)

        except Exception as exc:
            print(f"\n❌ 发布过程出错: {exc}")
            print("   浏览器保持打开 30s，请手动操作")
            time.sleep(30)

        ctx.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="小红书自动发布")
    parser.add_argument("date", nargs="?", help="日期 (YYYY-MM-DD)", default=None)
    parser.add_argument("--login-only", action="store_true", help="仅登录，不发布")
    parser.add_argument("--force", action="store_true", help="强制发布（跳过去重警告）")
    args = parser.parse_args()

    from datetime import date

    date_str = args.date or date.today().isoformat()
    run_publish(date_str, login_only=args.login_only)


if __name__ == "__main__":
    main()
