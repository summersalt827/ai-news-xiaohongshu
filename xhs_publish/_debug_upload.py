"""Quick diagnostic: find Xiaohongshu creator upload element."""
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

PROJECT_DIR = Path(__file__).resolve().parent.parent
USER_DATA_DIR = PROJECT_DIR / ".playwright-data"
CREATOR_URL = "https://creator.xiaohongshu.com/publish/publish"

with sync_playwright() as p:
    ctx = p.chromium.launch_persistent_context(
        str(USER_DATA_DIR),
        headless=False,
        channel="chrome",
        viewport={"width": 1280, "height": 900},
        locale="zh-CN",
    )
    page = ctx.new_page()
    page.goto(CREATOR_URL, wait_until="domcontentloaded", timeout=60000)
    time.sleep(5)

    # Dump all file inputs and upload-related elements
    file_inputs = page.locator('input[type="file"]').all()
    print(f"File inputs found: {len(file_inputs)}")
    for fi in file_inputs:
        print(f"  visible={fi.is_visible()}, enabled={fi.is_enabled()}")

    # Search for upload-related elements
    for selector in [
        '[class*="upload"]',
        '[class*="Upload"]',
        '[class*="addPic"]',
        '[class*="image"]',
        'button:has-text("上传")',
        '[class*="publish"]',
        '[class*="creator"]',
    ]:
        elems = page.locator(selector).all()
        if elems:
            print(f"\n{selector}: {len(elems)} found")
            for e in elems[:5]:
                try:
                    cls = e.get_attribute("class")
                    txt = e.text_content()[:80] if e.is_visible() else ""
                    print(f"  class={cls} text={txt}")
                except:
                    pass

    print("\nBrowser stays open for manual inspection.")
    input("Press Enter to close...")
    ctx.close()
