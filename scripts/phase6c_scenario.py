"""Phase 6c — 6 screenshots."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("docs/phases/phase-6c/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PORT = sys.argv[1] if len(sys.argv) > 1 else "8080"
BASE = f"http://127.0.0.1:{PORT}"


async def cap(page, name):
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"captured {name}")


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()

        # Clean state
        await page.goto(f"{BASE}/static/index.html", wait_until="networkidle")
        await page.evaluate("() => localStorage.clear()")

        # 01 — fit-to-width on default landing (translation mode, sidebar open)
        await page.goto(f"{BASE}/static/viewer.html?doc=1&page=1", wait_until="networkidle")
        await page.wait_for_selector(".stage-container", timeout=10_000)
        await page.wait_for_timeout(1500)
        await cap(page, "01-fit-to-width-default")

        # 02 — sidebar collapsed
        await page.click("#sidebar-toggle")
        await page.wait_for_timeout(700)
        await cap(page, "02-sidebar-collapsed")

        # 03 — sidebar expanded again
        await page.click("#sidebar-toggle")
        await page.wait_for_timeout(700)
        await cap(page, "03-sidebar-expanded")

        # 04 — natural scroll mid (scroll to page 3 to evidence next-page mount)
        await page.evaluate("""() => {
            const row = document.querySelector('.page-row[data-page="3"]');
            row?.scrollIntoView({ behavior: 'auto', block: 'start' });
        }""")
        await page.wait_for_timeout(1500)
        # Force one extra scroll bump so IO fires again
        await page.evaluate("() => document.getElementById('stage').scrollBy(0, 200)")
        await page.wait_for_timeout(800)
        await cap(page, "04-natural-scroll-mid")

        # Snapshot mounted page count for the README
        mounted_js = (
            "() => Array.from("
            "document.querySelectorAll('.page-row[data-mounted=\"1\"]')"
            ").map(r => Number(r.dataset.page))"
        )
        mounted = await page.evaluate(mounted_js)
        print(f"mounted_pages_mid_scroll={mounted}")

        # 05 — click logo, land on index.html
        await page.evaluate("() => document.querySelector('.app-logo').click()")
        await page.wait_for_url("**/static/index.html", timeout=10_000)
        await page.wait_for_timeout(800)
        await cap(page, "05-logo-back-to-index")

        # 06 — real LLM evidence (we capture the DB SELECT below, screenshot
        # is the viewer panel showing a real qwen response from the live test).
        await page.goto(f"{BASE}/static/viewer.html?doc=1&page=1", wait_until="networkidle")
        await page.wait_for_selector(".stage-container", timeout=10_000)
        await page.wait_for_timeout(1500)
        # Click first text block to open the chat panel.
        await page.locator(".block.block--text").first.click(force=True)
        await page.wait_for_selector(".chat-panel-host", state="visible", timeout=5000)
        await page.wait_for_timeout(800)
        await cap(page, "06-real-llm-response")

        await browser.close()
        print("done")


asyncio.run(main())
