#!/usr/bin/env python3
"""
Regenerate the README screenshots from the real running app.

It seeds a throw-away database, starts the Flask app on a spare port, and uses
headless Chromium (Playwright) to capture pages into ./screenshots.

Setup (once):  pip install playwright && playwright install chromium
Run:           python scripts/take_screenshots.py     (set CHROME_PATH to use an installed Chrome)
"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402
from werkzeug.serving import make_server          # noqa: E402

import seed                                        # noqa: E402
from app import create_app                         # noqa: E402

OUT = ROOT / "screenshots"
PORT = 5057


def main() -> None:
    OUT.mkdir(exist_ok=True)
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "shots.sqlite")
    seed.build(db_path, count=60, seed=42)
    app = create_app({"DATABASE": db_path})
    server = make_server("127.0.0.1", PORT, app)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    time.sleep(0.5)
    base = f"http://127.0.0.1:{PORT}"

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None,
                                    args=["--no-sandbox"])

        def shot(page, name, full=False):
            page.wait_for_timeout(400)               # let the slide-over settle
            page.screenshot(path=OUT / name, full_page=full)

        desk = browser.new_page(viewport={"width": 1440, "height": 900})
        desk.goto(base + "/")
        shot(desk, "01-queue-desktop.png")

        desk.locator(".row-link").nth(1).click()               # open a ticket beside the list
        desk.wait_for_selector("#panel:not([hidden]) form.update")
        shot(desk, "02-ticket-open-desktop.png")

        # a finished ticket, with its resolution and log
        desk.goto(base + "/tickets?status=Resolved")
        desk.locator(".row-link").first.click()
        desk.wait_for_selector("#panel:not([hidden]) .res-box")
        shot(desk, "03-resolved-ticket-detail.png")

        desk.goto(base + "/")
        desk.click("summary:has-text('Filters')")
        desk.check("input[name=overdue]")
        desk.click(".filter-grid button[type=submit]")
        desk.wait_for_function("document.querySelector('#count-line').textContent.includes('past due')")
        shot(desk, "04-filtered-overdue-desktop.png")

        desk.goto(base + "/overview")
        shot(desk, "05-overview-desktop.png", full=True)

        desk.goto(base + "/")
        desk.click("button.help-link")
        shot(desk, "06-help-panel-desktop.png")

        mob = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mob.goto(base + "/")
        shot(mob, "07-queue-mobile.png")
        mob.locator(".row-link").nth(1).click()
        mob.wait_for_selector("#panel:not([hidden]) form.update")
        shot(mob, "08-ticket-mobile.png")
        browser.close()
    server.shutdown()
    print("Screenshots written to", OUT)


if __name__ == "__main__":
    main()
