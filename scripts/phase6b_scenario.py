"""Phase 6b — Playwright scenario for 8 screenshots + memory benchmark."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("docs/phases/phase-6b/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PORT = sys.argv[1] if len(sys.argv) > 1 else "8080"
BASE = f"http://127.0.0.1:{PORT}"


async def cap(page, name: str) -> None:
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"captured {name}")


async def mem(page) -> float:
    val = await page.evaluate("performance.memory?.usedJSHeapSize || 0")
    return val / 1024 / 1024


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--enable-precise-memory-info"],
        )
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()

        # Bootstrap localStorage with zoom=0.5 so two panes fit horizontally.
        await page.goto(f"{BASE}/static/index.html", wait_until="networkidle")
        await page.evaluate(
            "() => { localStorage.clear(); localStorage.setItem('ht_lens.zoom', '0.5'); }"
        )

        await page.goto(f"{BASE}/static/viewer.html?doc=1&page=1", wait_until="networkidle")
        await page.wait_for_selector(".stage-container", timeout=10_000)
        await page.wait_for_timeout(1500)

        mem_start = await mem(page)
        print(f"mem start: {mem_start:.1f} MB")

        # 02 translation only (default)
        await cap(page, "02-translation-only")

        # 03 original only (T x 1 from translation -> original)
        await page.keyboard.press("t")
        await page.wait_for_timeout(700)
        await cap(page, "03-original-only")

        # 01 both side-by-side (T x 1: original -> both)
        await page.keyboard.press("t")
        await page.wait_for_timeout(900)
        await cap(page, "01-side-by-side-default")

        # 04 natural scroll mid — scroll to page 2
        await page.evaluate("""() => {
            const row = document.querySelector('.page-row[data-page="2"]');
            row?.scrollIntoView({ behavior: 'auto', block: 'start' });
        }""")
        await page.wait_for_timeout(1200)
        await cap(page, "04-natural-scroll-mid")

        # 05 zoom 75% (one step up from 0.5) — captures both at slightly bigger size
        await page.keyboard.press("Control+ArrowUp")
        await page.wait_for_timeout(800)
        await cap(page, "05-zoom-150-both")
        # Reset
        await page.keyboard.press("Control+ArrowDown")
        await page.wait_for_timeout(400)

        # 06 chat panel forces single — scroll back to page 1, click a block (force).
        await page.evaluate("""() => {
            const row = document.querySelector('.page-row[data-page="1"]');
            row?.scrollIntoView({ behavior: 'auto', block: 'start' });
        }""")
        await page.wait_for_timeout(800)
        block = page.locator(".pane-translation .block.block--text").first
        await block.click(force=True)
        await page.wait_for_timeout(800)
        await cap(page, "06-chat-panel-forces-single")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)

        # 07 search jump
        await page.keyboard.press("Control+k")
        await page.wait_for_selector(".search-modal", timeout=5000)
        await page.wait_for_timeout(300)
        await page.fill(".search-input", "비디오")
        await page.wait_for_timeout(700)
        await page.keyboard.press("Enter")
        await page.wait_for_timeout(2200)
        await cap(page, "07-search-jump-to-block")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)

        # 08 sidebar thread jump
        await page.locator('.sidebar-tab[data-tab="questions"]').click()
        await page.wait_for_timeout(500)
        thread = page.locator(".thread-item").first
        await thread.click(force=True)
        await page.wait_for_timeout(1800)
        await cap(page, "08-sidebar-thread-jump")
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(400)

        # Memory stress
        peak = mem_start
        scroll_js = (
            '(p) => document.querySelector(`.page-row[data-page="${p}"]`)'
            "?.scrollIntoView({behavior:'auto',block:'start'})"
        )
        for p in range(1, 7):
            await page.evaluate(scroll_js, p)
            await page.wait_for_timeout(900)
            cur = await mem(page)
            peak = max(peak, cur)
            print(f"page {p}: {cur:.1f} MB")
        print(f"\nPEAK_JS_HEAP_MB={peak:.1f}")
        # Snapshot mount + DOM block count for stress evidence.
        mounted = await page.evaluate(
            """() => document.querySelectorAll('.page-row[data-mounted="1"]').length"""
        )
        blocks = await page.evaluate("""() => document.querySelectorAll('.block').length""")
        print(f"MOUNTED_PAGES={mounted}")
        print(f"DOM_BLOCK_COUNT={blocks}")

        await browser.close()
        print(f"\nfinished. screenshots in {OUT}/")


asyncio.run(main())
