#!/usr/bin/env python3
"""Phase 6a — Playwright-driven 7 screenshots for verify.

Captures:
  01 — search modal opened (empty input)
  02 — search results listed
  03 — block highlighted after search-result jump
  04 — sidebar with export button
  05 — exported markdown file content (rendered text)
  06 — retranslate confirm modal
  07 — retranslate result (toast / updated translation)
"""

import asyncio
import contextlib
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("docs/phases/phase-6a/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PORT = sys.argv[1] if len(sys.argv) > 1 else "8201"
BASE = f"http://127.0.0.1:{PORT}"


async def capture(page, name: str) -> None:
    await page.wait_for_timeout(400)
    await page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"captured {name}")


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()

        # Start fresh
        await page.goto(f"{BASE}/static/index.html", wait_until="networkidle")
        await page.evaluate("() => localStorage.clear()")

        # 1. Open viewer + Cmd+K
        await page.goto(f"{BASE}/static/viewer.html?doc=1&page=1", wait_until="networkidle")
        await page.wait_for_selector(".stage", timeout=10_000)
        await page.wait_for_timeout(800)
        await page.keyboard.press("Control+k")
        await page.wait_for_selector(".search-modal", timeout=5000)
        await page.wait_for_timeout(400)
        await capture(page, "01-search-modal-open")

        # 2. Type a query and capture results
        await page.fill(".search-input", "비디오")
        await page.wait_for_timeout(700)  # debounce 200ms + roundtrip
        await capture(page, "02-search-results")

        # 3. Press Enter to jump to first result and capture the block flash
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(1500)
        await capture(page, "03-search-jump")

        # 4. Sidebar with export button — switch to questions tab
        # Close the panel first (Esc)
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(300)
        await page.locator('.sidebar-tab[data-tab="questions"]').click()
        await page.wait_for_timeout(500)
        await capture(page, "04-export-button")

        # 5. Click export — capture the toast right after download triggers
        await page.locator(".export-btn").click()
        await page.wait_for_timeout(700)
        await capture(page, "05-export-toast")

        # 6. Retranslate confirm — right-click a block
        await page.locator('.sidebar-tab[data-tab="pages"]').click()
        await page.wait_for_timeout(400)
        first_block = page.locator(".block.block--text").first
        # Trigger the contextmenu event directly (right click).
        await first_block.click(button="right")
        await page.wait_for_selector(".confirm-modal", timeout=5000)
        await page.wait_for_timeout(400)
        await capture(page, "06-retranslate-confirm")

        # 7. Click confirm and capture the toast + updated translation
        await page.locator(".btn-confirm").click()
        # Wait for either toast (success or error) or up to 3 minutes for LLM
        with contextlib.suppress(Exception):
            await page.wait_for_selector(".toast.success", timeout=180_000)
        await page.wait_for_timeout(600)
        await capture(page, "07-retranslate-result")

        await browser.close()


asyncio.run(main())
