"""Phase 6d — Playwright scenario for ~10 screenshots."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path("docs/phases/phase-6d/screenshots")
OUT.mkdir(parents=True, exist_ok=True)
PORT = sys.argv[1] if len(sys.argv) > 1 else "8080"
PDF = sys.argv[2] if len(sys.argv) > 2 else "/tmp/phase6d_demo2.pdf"
BASE = f"http://127.0.0.1:{PORT}"


async def cap(page, name):
    await page.wait_for_timeout(500)
    await page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
    print(f"captured {name}")


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        ctx = await browser.new_context(viewport={"width": 1400, "height": 950})
        page = await ctx.new_page()

        # 01 — empty upload zone (clean slate)
        await page.goto(f"{BASE}/static/index.html", wait_until="networkidle")
        await page.evaluate("() => localStorage.clear()")
        await page.wait_for_timeout(700)
        await cap(page, "01-upload-zone-empty")

        # 02 — drag-over state (simulate by toggling the class)
        await page.evaluate(
            "() => document.getElementById('upload-zone').classList.add('upload-zone--drag')"
        )
        await page.wait_for_timeout(400)
        await cap(page, "02-drag-over")
        await page.evaluate(
            "() => document.getElementById('upload-zone').classList.remove('upload-zone--drag')"
        )

        # 03 — upload in progress (use the hidden file input directly)
        async with page.expect_response("**/uploads") as resp_info:
            await page.set_input_files("#upload-input", PDF)
        resp = await resp_info.value
        print("upload status:", resp.status)
        # Let the polling panel render the row
        await page.wait_for_selector(".job-row", timeout=10_000)
        await page.wait_for_timeout(800)
        await cap(page, "03-upload-in-progress")

        # 04 — translating mid: wait for status="translating"
        for _ in range(60):
            stat = await page.evaluate(
                "() => document.querySelector('.job-status')?.textContent || ''"
            )
            if "translating" in stat:
                break
            await page.wait_for_timeout(1000)
        await cap(page, "04-translating-mid")

        # 05 — summarizing
        for _ in range(120):
            stat = await page.evaluate(
                "() => document.querySelector('.job-status')?.textContent || ''"
            )
            if "summarizing" in stat:
                break
            await page.wait_for_timeout(1000)
        await cap(page, "05-summarizing")

        # 06 — done + new card visible
        for _ in range(120):
            # Either jobs panel is hidden (auto-stopped) or status=done
            panel_hidden = await page.evaluate(
                "() => document.getElementById('active-jobs').hidden"
            )
            if panel_hidden:
                break
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(1500)  # let refetch settle
        await cap(page, "06-done-and-card")

        # 07 — dedup toast: re-upload the same file
        await page.set_input_files("#upload-input", PDF)
        await page.wait_for_timeout(800)
        await cap(page, "07-dedup-toast")

        # Navigate to the new doc's viewer for screenshots 09/10.
        # Get the new document id from the API.
        import json
        import urllib.request

        docs = json.loads(urllib.request.urlopen(f"{BASE}/documents").read())
        new_doc = max(docs, key=lambda d: d["id"])
        doc_id = new_doc["id"]

        # 09 — summary preview in card (index page already shows it)
        await cap(page, "09-summary-in-card")

        # 10 — viewer summary banner
        await page.goto(f"{BASE}/static/viewer.html?doc={doc_id}&page=1", wait_until="networkidle")
        await page.wait_for_selector(".summary-banner", timeout=10_000)
        await page.wait_for_timeout(1200)
        await cap(page, "10-summary-full-in-viewer")

        # 08 — failed/error display: trigger by uploading a non-PDF.
        await page.goto(f"{BASE}/static/index.html", wait_until="networkidle")
        await page.wait_for_timeout(500)
        # Create a tiny txt file path on the fly.
        import tempfile

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"not a pdf")
            txt = f.name
        try:
            await page.set_input_files("#upload-input", txt)
            await page.wait_for_timeout(1500)
            await cap(page, "08-failed-error-display")
        finally:
            Path(txt).unlink(missing_ok=True)

        await browser.close()
        print("done")


asyncio.run(main())
