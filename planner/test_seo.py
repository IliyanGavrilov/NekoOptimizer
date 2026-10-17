import json
import re

import pytest

from planner.seo import ld_json

SITE = "https://neko.example"


@pytest.fixture(autouse=True)
def _site(settings):
    settings.SITE_URL = SITE


def _tiers():
    """A tiers.json doc with one per-set list, Dynamites."""
    tiers = [{"tier": "SS", "entries": [{"name": "Bahamut", "unit_id": 25, "boost": None}]}]
    dynamites = {
        "source": "https://example.test/tiers",
        "fetched": "2026-10-01",
        "tiers": tiers,
        "path": "/tier-lists/base-tier-lists/dynamites",
        "label": "Dynamites",
        "category": "Base",
    }

    return {
        "source": "https://example.test/tiers",
        "fetched": "2026-10-01",
        "tiers": tiers,
        "lists": [dynamites],
    }


@pytest.fixture
def tiers(monkeypatch):
    monkeypatch.setattr("planner.views.load_tiers", _tiers)


def _structured_data(body: bytes) -> dict:
    found = re.search(rb'<script type="application/ld\+json">(.*?)</script>', body, re.S)
    return json.loads(found.group(1))


def test_ld_json_cannot_close_its_script_tag():
    assert "</script>" not in ld_json({"name": "</script><script>alert(1)"})


def test_ld_json_round_trips_the_escaped_text():
    assert json.loads(ld_json({"name": "a<b>&c"})) == {"name": "a<b>&c"}


@pytest.mark.django_db
def test_a_set_tier_page_is_titled_for_its_set(client, tiers):
    body = client.get("/tiers/base-tier-lists/dynamites/").content.decode()
    assert "<title>Battle Cats Dynamites Tier List | Neko Optimizer</title>" in body


@pytest.mark.django_db
def test_the_canonical_url_is_the_public_site_without_the_query(client, tiers):
    body = client.get("/tiers/?sort=name").content.decode()
    assert f'<link rel="canonical" href="{SITE}/tiers/">' in body


@pytest.mark.django_db
def test_a_set_tier_page_breadcrumb_ends_at_its_set(client, tiers):
    trail = _structured_data(client.get("/tiers/base-tier-lists/dynamites/").content)
    assert trail["itemListElement"][-1] == {
        "@type": "ListItem",
        "position": 3,
        "name": "Dynamites",
        "item": f"{SITE}/tiers/base-tier-lists/dynamites/",
    }


@pytest.mark.django_db
def test_the_tier_page_links_every_set_for_crawlers(client, tiers):
    body = client.get("/tiers/").content.decode()
    assert '<a href="/tiers/base-tier-lists/dynamites/">Dynamites</a>' in body


def test_the_login_page_stays_out_of_the_index(client):
    assert b'<meta name="robots" content="noindex">' in client.get("/accounts/login/").content


def test_the_about_page_is_indexable(client):
    assert b'name="robots"' not in client.get("/about/").content


def test_the_sitemap_lists_each_set_tier_page_with_its_fetch_date(client, tiers):
    body = client.get("/sitemap.xml").content.decode()
    assert (
        f"<loc>{SITE}/tiers/base-tier-lists/dynamites/</loc>\n    <lastmod>2026-10-01</lastmod>"
        in body
    )


def test_the_sitemap_leaves_out_noindex_pages(client, tiers):
    assert b"/accounts/" not in client.get("/sitemap.xml").content


def test_robots_points_crawlers_at_the_sitemap(client):
    assert f"Sitemap: {SITE}/sitemap.xml" in client.get("/robots.txt").content.decode()
