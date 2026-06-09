from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from neko.cache import RollCache
from neko.godfat import GachaEvent, parse_rolls
from neko.scraper import GodfatScraper, active_events, aiohttp_fetch, roll_url

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "godfat_sample.html").read_text(encoding="utf-8")
EVENTS = (FIXTURES / "godfat_events.html").read_text(encoding="utf-8")


def fetch_returning(html):
    async def fetch(url):
        return html

    return fetch


def mock_session(html):
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.text = AsyncMock(return_value=html)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=response)
    ctx.__aexit__ = AsyncMock(return_value=False)
    session = MagicMock()
    session.get = MagicMock(return_value=ctx)
    return session, response


def test_roll_url_format():
    assert (
        roll_url(12345, "2026-06-26_1052", 30)
        == "https://bc.godfat.org/?seed=12345&event=2026-06-26_1052&count=30&display=text&name=2"
    )


async def test_rolls_fetches_and_parses():
    scraper = GodfatScraper(fetch_returning(FIXTURE))
    assert await scraper.rolls(1, "ev") == parse_rolls(FIXTURE)


async def test_rolls_returns_cache_without_fetching(tmp_path):
    async def boom(url):
        raise AssertionError("fetched despite a cache hit")

    cache = RollCache(tmp_path)
    expected = parse_rolls(FIXTURE)
    cache.save(1, "ev", 30, expected)
    scraper = GodfatScraper(boom, cache, count=30)
    assert await scraper.rolls(1, "ev") == expected


async def test_rolls_writes_to_cache(tmp_path):
    cache = RollCache(tmp_path)
    scraper = GodfatScraper(fetch_returning(FIXTURE), cache, count=30)
    await scraper.rolls(1, "ev")
    assert cache.load(1, "ev", 30) == parse_rolls(FIXTURE)


async def test_all_rolls_keyed_by_event():
    scraper = GodfatScraper(fetch_returning(FIXTURE))
    result = await scraper.all_rolls(1, ["a", "b"])
    assert result == {"a": parse_rolls(FIXTURE), "b": parse_rolls(FIXTURE)}


async def test_events_parses_dropdown():
    scraper = GodfatScraper(fetch_returning(EVENTS))
    assert [event.event_id for event in await scraper.events()] == [
        "2026-06-26_1052",
        "2026-04-24_1047",
        "2026-01-01_900",
    ]


def test_active_events_keeps_only_current():
    events = [
        GachaEvent("past", "n", date(2026, 1, 1), date(2026, 1, 8)),
        GachaEvent("now", "n", date(2026, 6, 1), date(2026, 6, 30)),
        GachaEvent("future", "n", date(2026, 12, 1), date(2026, 12, 2)),
    ]
    assert active_events(events, date(2026, 6, 15)) == [events[1]]


def test_active_events_boundary_is_inclusive():
    event = GachaEvent("edge", "n", date(2026, 6, 1), date(2026, 6, 15))
    assert active_events([event], date(2026, 6, 15)) == [event]


async def test_aiohttp_fetch_returns_body():
    session, _ = mock_session("<html>ok</html>")
    assert await aiohttp_fetch(session, "https://x") == "<html>ok</html>"


async def test_aiohttp_fetch_checks_status():
    session, response = mock_session("x")
    response.raise_for_status.side_effect = RuntimeError
    with pytest.raises(RuntimeError):
        await aiohttp_fetch(session, "https://x")
