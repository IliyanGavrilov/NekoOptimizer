from django.urls import resolve

from planner.context_processors import tools
from planner.links import PAGE_LINKS, unit_links


class _Request:
    """Just the attribute the context processor reads off a request."""

    def __init__(self, resolver_match=None):
        self.resolver_match = resolver_match


def test_unit_link_to_battlecatsstats_shifts_the_id_by_one():
    urls = {link.label: link.url for link in unit_links(25, "Bahamut Cat", "Uber Super Rare")}
    assert urls["battlecatsstats"] == "https://battlecatsstats.com/unit/26/0"


def test_unit_link_to_battlecatsinfo_keeps_our_own_id():
    urls = {link.label: link.url for link in unit_links(25, "Bahamut Cat", "Uber Super Rare")}
    assert urls["battlecatsinfo"] == "https://battlecatsinfo.github.io/unit.html?id=25"


def test_unit_links_title_the_wiki_page_by_rarity():
    urls = {link.label: link.url for link in unit_links(25, "Bahamut Cat", "Uber Super Rare")}
    assert urls["Battle Cats Wiki"].endswith("/Bahamut_Cat_(Uber_Rare_Cat)")


def test_page_links_come_from_the_resolved_url_name():
    assert tools(_Request(resolve("/resources/")))["page_links"] == PAGE_LINKS["resources"]


def test_both_tier_list_routes_get_the_same_links():
    slug_page = resolve("/tiers/base-tier-lists/dynamites/")
    assert tools(_Request(slug_page))["page_links"] == PAGE_LINKS["tier_list"]


def test_a_page_without_curated_links_gets_none():
    assert tools(_Request(resolve("/about/")))["page_links"] == ()


def test_an_unresolved_request_gets_no_links():
    assert tools(_Request())["page_links"] == ()
