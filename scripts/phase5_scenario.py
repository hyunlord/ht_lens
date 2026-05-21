#!/usr/bin/env python3
"""Phase 5 — Playwright-driven 10-question scenario + screenshot capture.

This is the actual driver used to produce ``docs/phases/phase-5/screenshots/``.
It is intentionally committed (instead of staying in /tmp) so verify
reviewers and Planner can audit + re-run the strongest DoD evidence.

Dependencies
------------
- ``playwright`` (Python) + chromium browser
- An external venv that already has both is fine — Phase 5 forbids adding
  ``playwright`` as a project dep. Suggested invocation:

      /path/to/external/venv/bin/python scripts/phase5_scenario.py PORT

Server expected at ``http://127.0.0.1:PORT`` with at least one document
that has translated text blocks. ``--skip-llm-check`` is OK because we
hit the LLM through the actual UI flow.

Usage
-----
    ht-lens serve --port 8201 --db /tmp/ht_lens_phase5.db &
    sleep 4
    /path/to/playwright-venv/bin/python scripts/phase5_scenario.py 8201

Captures ``docs/phases/phase-5/screenshots/01..10.png`` and prints
``{threads, total_messages}`` on stdout.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:  # pragma: no cover - environment-specific
    sys.stderr.write("playwright is required (see module docstring); aborting.\n")
    sys.exit(2)

OUT = Path("docs/phases/phase-5/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PORT = sys.argv[1] if len(sys.argv) > 1 else "8201"
BASE = f"http://127.0.0.1:{PORT}"


async def goto_page(page, pnum: int) -> None:
    await page.goto(f"{BASE}/static/viewer.html?doc=1&page={pnum}", wait_until="networkidle")
    await page.wait_for_selector(".stage", timeout=10_000)
    await page.wait_for_timeout(500)


async def click_nth_text_block(page, n: int) -> bool:
    blocks = page.locator(".block.block--text")
    if n >= await blocks.count():
        return False
    await blocks.nth(n).click()
    await page.wait_for_selector(".chat-panel", timeout=5000)
    await page.wait_for_timeout(300)
    return True


async def wait_assistant(page, prior: int, timeout_ms: int = 180_000) -> int:
    deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
    sel = ".message.message--assistant:not(.message--loading)"
    while asyncio.get_event_loop().time() < deadline:
        cur = await page.locator(sel).count()
        if cur > prior:
            return cur
        await asyncio.sleep(0.5)
    return -1


async def click_explain(page) -> bool:
    btn = page.locator(".explain-btn")
    if await btn.count() == 0:
        return False
    prior = await page.locator(".message.message--assistant:not(.message--loading)").count()
    await btn.first.click()
    return await wait_assistant(page, prior) > prior


async def send_msg(page, text: str) -> bool:
    ta = page.locator(".message-input textarea")
    if await ta.count() == 0:
        return False
    await ta.first.fill(text)
    prior = await page.locator(".message.message--assistant:not(.message--loading)").count()
    await page.keyboard.press("Control+Enter")
    return await wait_assistant(page, prior) > prior


async def capture(page, name: str) -> None:
    await page.wait_for_timeout(400)
    await page.screenshot(path=str(OUT / f"{name}.png"))
    print(f"captured {name}")


async def main() -> None:
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1600, "height": 1000})
        page = await ctx.new_page()

        # 1: empty + 2: explain
        await goto_page(page, 1)
        await click_nth_text_block(page, 0)
        await capture(page, "01-block-click-empty")
        await click_explain(page)
        await capture(page, "02-explain-response")

        # 3: direct question, 4: follow-up in same thread
        await goto_page(page, 1)
        await click_nth_text_block(page, 1)
        await send_msg(page, "이 텍스트가 의미하는 바를 자세히 알려줘.")
        await capture(page, "03-direct-question")
        await send_msg(page, "한 문장으로 더 짧게 요약해줘.")
        await capture(page, "04-followup-question")

        # accumulate more threads until we have 10
        plan = [
            (1, 2, "explain"),
            (2, 0, "explain"),
            (2, 1, ("msg", "이 단락의 핵심 개념이 무엇인가요?")),
            (3, 0, "explain"),
            (4, 0, "explain"),
            (5, 0, "explain"),
            (6, 0, "explain"),
        ]
        for pnum, idx, action in plan:
            try:
                await goto_page(page, pnum)
                if not await click_nth_text_block(page, idx):
                    continue
                if action == "explain":
                    await click_explain(page)
                else:
                    _, text = action
                    await send_msg(page, text)
            except Exception as exc:  # pragma: no cover
                print(f"  error p{pnum} idx{idx}: {exc}")

        # 5: page with pins
        await goto_page(page, 1)
        await capture(page, "05-pins-on-blocks")

        # 6: sidebar questions
        tab = page.locator('.sidebar-tab[data-tab="questions"]')
        if await tab.count() > 0:
            await tab.first.click()
            await page.wait_for_timeout(500)
            await capture(page, "06-sidebar-questions-tab")

            # 7: thread jump
            items = page.locator(".thread-item")
            n = await items.count()
            if n > 2:
                await items.nth(2).click()
                await page.wait_for_timeout(2500)
                await capture(page, "07-thread-jump-from-list")

        # 8: markdown close-up
        await page.wait_for_timeout(500)
        await capture(page, "08-markdown-render")

        # 9: 10 threads
        tab = page.locator('.sidebar-tab[data-tab="questions"]')
        if await tab.count() > 0:
            await tab.first.click()
            await page.wait_for_timeout(500)
            await capture(page, "09-ten-questions-accumulated")

        # 10: reload restore
        await page.reload(wait_until="networkidle")
        await page.wait_for_selector(".stage", timeout=10_000)
        await page.wait_for_timeout(2000)
        await capture(page, "10-localstorage-restore")

        stats = await page.evaluate("() => fetch('/threads?doc_id=1').then((r) => r.json())")
        total = sum(t["message_count"] for t in stats)
        print(json.dumps({"threads": len(stats), "total_messages": total}, indent=2))

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
