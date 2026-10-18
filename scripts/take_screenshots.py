#!/usr/bin/env python3
"""
Regenerate the README screenshots from the real running app.

It seeds a throw-away database, starts the Flask app on a spare port, and uses
headless Chromium (Playwright) to capture pages into ./screenshots.

Setup (once):  pip install playwright && playwright install chromium
Run:           python scripts/take_screenshots.py
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
        browser = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None)
        page = browser.new_page(viewport={"width": 1280, "height": 900})

        page.goto(base + "/")
        page.screenshot(path=OUT / "01-dashboard.png", full_page=True)

        page.goto(base + "/tickets?status=active")
        page.screenshot(path=OUT / "02-open-tickets.png", full_page=True)

        page.goto(base + "/tickets?q=wi-fi&category=Network")
        page.screenshot(path=OUT / "03-search-filter.png", full_page=True)

        # Ticket detail of a finished ticket (has a resolution log)
        page.goto(base + "/tickets?status=Resolved")
        page.locator("table.tickets tbody tr a").first.click()
        page.screenshot(path=OUT / "04-ticket-detail.png", full_page=True)

        page.goto(base + "/tickets/new")
        page.fill("input[name=title]", "Laptop will not connect to office Wi-Fi")
        page.fill("input[name=requester]", "Sample User")
        page.select_option("select[name=category]", "Network")
        page.select_option("select[name=priority]", "High")
        page.fill("textarea[name=description]", "Sample ticket created while taking screenshots.")
        page.screenshot(path=OUT / "05-new-ticket-form.png", full_page=True)
        browser.close()
    server.shutdown()
    print("Screenshots written to", OUT)


if __name__ == "__main__":
    main()
