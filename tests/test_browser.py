"""Browser tests: the slide-over, the filters, the help panel and the update forms in a real Chromium.

They are skipped when Playwright or a browser is not installed. To run them:
    pip install playwright && playwright install chromium     (or set CHROME_PATH to a Chrome binary)
"""
import os
import threading

import pytest

sync_api = pytest.importorskip("playwright.sync_api")
from werkzeug.serving import make_server  # noqa: E402

import seed                               # noqa: E402
from app import create_app                # noqa: E402


@pytest.fixture(scope="module")
def base(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("db") / "b.sqlite")
    seed.build(db, 60, 42)
    server = make_server("127.0.0.1", 5073, create_app({"DATABASE": db}))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield "http://127.0.0.1:5073"
    server.shutdown()


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch(executable_path=os.environ.get("CHROME_PATH") or None,
                                  args=["--no-sandbox"])
        except Exception as exc:                       # no browser installed
            pytest.skip(f"no browser available: {exc}")
        yield b
        b.close()


@pytest.fixture()
def page(browser, base):
    pg = browser.new_page(viewport={"width": 1440, "height": 900})
    pg.errors = []
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.goto(base + "/")
    yield pg
    assert pg.errors == []
    pg.close()


def test_clicking_a_ticket_opens_it_beside_the_list(page):
    first = page.locator(".row-link").nth(1)
    title = first.locator(".q-title").inner_text()
    first.click()
    page.wait_for_selector("#panel:not([hidden]) #p-title")
    assert page.locator("#p-title").inner_text() == title
    assert page.url.split("/")[-1].isdigit()
    assert page.locator(".row-link[aria-current=true]").count() == 1
    assert page.locator(".queue").is_visible()                  # the list is still there


def test_escape_closes_the_panel_and_returns_focus(page):
    row = page.locator(".row-link").first
    row.click()
    page.wait_for_selector("#panel:not([hidden])")
    page.keyboard.press("Escape")
    page.wait_for_selector("#panel", state="hidden")
    assert page.evaluate("document.activeElement.className") == "row-link"
    assert "/tickets/" not in page.url


def test_back_button_closes_the_panel(page):
    page.locator(".row-link").first.click()
    page.wait_for_selector("#panel:not([hidden])")
    page.go_back()
    page.wait_for_selector("#panel", state="hidden")


def test_saving_changes_updates_the_panel_and_the_list(page):
    page.locator(".row-link").first.click()
    page.wait_for_selector("form.update")
    before = page.locator(".log li").count()
    page.select_option("form.update select[name=priority]", "Critical")
    page.click("form.update button[type=submit]")
    page.wait_for_selector(".flash")
    assert "Ticket updated" in page.locator(".flash").inner_text()
    assert page.locator(".log li").count() > before          # the change was logged
    assert "Critical" in page.locator(".row-link[aria-current=true] .q-pri").inner_text()


def test_resolution_box_appears_only_when_resolving(page):
    page.locator(".row-link").first.click()
    page.wait_for_selector("form.update")
    assert page.locator(".res-field").is_hidden()
    page.select_option("form.update select[name=status]", "Resolved")
    assert page.locator(".res-field").is_visible()
    page.click("form.update button[type=submit]")                # no resolution: refused
    page.wait_for_selector(".flash.error")
    page.select_option("form.update select[name=status]", "Resolved")
    page.fill("textarea[name=resolution]", "Cleared the cache and restarted the client.")
    page.click("form.update button[type=submit]")
    page.wait_for_selector(".flash.ok")
    assert "Cleared the cache" in page.locator(".res-box").inner_text()


def test_adding_a_note(page):
    page.locator(".row-link").first.click()
    page.wait_for_selector("#note-body")
    page.fill("#note-body", "Called the user back.")
    page.click(".note-form button[type=submit]")
    page.wait_for_selector(".flash.ok")
    assert "Called the user back." in page.locator(".log").inner_text()
    assert page.input_value("#note-body") == ""


def test_new_ticket_flow(page):
    page.click("[data-new]")
    page.wait_for_selector("[data-new-form]")
    page.click("[data-new-form] button[type=submit]")           # empty form: browser validation blocks it
    assert page.locator("[data-new-form]").is_visible()
    page.fill("#panel input[name=title]", "Projector shows no signal")
    page.fill("#panel input[name=requester]", "Dana Test")
    page.select_option("#panel select[name=priority]", "High")
    page.click("[data-new-form] button[type=submit]")
    page.wait_for_selector("#p-title:has-text('Projector shows no signal')")
    assert "/tickets/" in page.url
    assert page.locator(".queue", has_text="Projector shows no signal").count() == 1


def test_search_and_filters_narrow_the_list_without_reloading(page):
    total = page.locator(".row-link").count()
    page.fill("#q", "access")
    page.press("#q", "Enter")
    page.wait_for_function("document.querySelectorAll('.row-link').length < %d" % total)
    assert "q=access" in page.url
    assert page.locator(".row-link").count() >= 1
    page.fill("#q", "")
    page.click("summary:has-text('Filters')")
    page.check("input[name=overdue]")
    page.click(".filter-grid button[type=submit]")
    page.wait_for_function("document.querySelector('#count-line').textContent.includes('past due')")
    assert page.locator(".q-due:not(.sla-overdue)").count() == 0


def test_help_dialog_opens_closes_and_has_the_why_note(page):
    page.click("button.help-link")
    assert page.locator("dialog#help").is_visible()
    assert page.locator("dialog#help ol li").count() == 5
    assert "Why I built this" in page.locator("dialog#help").inner_text()
    page.keyboard.press("Escape")
    assert page.locator("dialog#help").is_hidden()
    assert page.evaluate("document.activeElement.className") == "help-link"


def test_mobile_ticket_opens_as_a_sheet(browser, base):
    pg = browser.new_page(viewport={"width": 390, "height": 844})
    pg.goto(base + "/")
    pg.locator(".row-link").first.click()
    pg.wait_for_selector("#panel:not([hidden]) #p-title")
    box = pg.locator("#panel").bounding_box()
    assert box["width"] >= 389
    assert pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    pg.close()
