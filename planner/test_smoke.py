import os

import pytest

# A real browser over the served site, for what the Python tests can't see: a script that
# no longer parses, or one that throws as a page loads. CI's smoke job runs it
# (NEKO_SMOKE=1, with Playwright's Chromium); the everyday gate skips it.
pytestmark = pytest.mark.skipif(not os.environ.get("NEKO_SMOKE"), reason="set NEKO_SMOKE=1")
sync_api = pytest.importorskip("playwright.sync_api")

PAGES = ["/", "/normal/", "/collection/", "/resources/", "/tiers/", "/seek/", "/guides/", "/jp/"]


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as playwright:
        # NEKO_SMOKE_CHANNEL picks an installed browser (e.g. msedge) over the bundled one.
        engine = playwright.chromium.launch(channel=os.environ.get("NEKO_SMOKE_CHANNEL"))
        yield engine
        engine.close()


def _visit(browser, url, act=None):
    """The script errors and failed requests a page shows while it loads (and acts)."""
    page = browser.new_page()
    problems = []
    page.on("pageerror", lambda error: problems.append(f"script: {error}"))
    page.on(
        "response",
        lambda r: problems.append(f"{r.status} {r.url}") if r.status >= 400 else None,
    )
    page.goto(url)
    page.wait_for_load_state("networkidle")
    if act:
        act(page)
    page.close()

    return problems


@pytest.mark.parametrize("path", PAGES)
def test_page_loads_without_errors(live_server, browser, path):
    assert _visit(browser, live_server.url + path) == []


def test_planner_search_runs_without_errors(live_server, browser):
    def search(page):
        page.fill("#targetSearch", "cat")
        page.wait_for_timeout(1500)

    assert _visit(browser, live_server.url + "/", search) == []
