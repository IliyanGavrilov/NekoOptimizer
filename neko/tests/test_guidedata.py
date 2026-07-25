from neko.guidedata import parse_guide, resolve_names

# The page shape that matters: a preamble full of = characters before the tabber,
# then one {{CatGuide}} call per region tab.
_WIKITEXT = """==How to update==
See [{{fullurl:User:X/Archive|oldid=1}} Archive] for code.

==Units==
<onlyinclude>
<tabber>
English Version=
{{CatGuide|Cat|Tank Cat|Axe Cat}}
|-|Japanese Version=
{{CatGuide|Cat|Tank Cat}}
</tabber>
</onlyinclude>"""

_RECORDS = [
    {"id": 0, "name": "Cat"},
    {"id": 1, "name": "Tank Cat"},
    {"id": 2, "name": "Axe Cat"},
]


def test_parse_survives_the_preambles_equals_signs():
    assert parse_guide(_WIKITEXT)["en"] == ["Cat", "Tank Cat", "Axe Cat"]


def test_parse_splits_regions_at_tab_boundaries():
    assert parse_guide(_WIKITEXT)["jp"] == ["Cat", "Tank Cat"]


def test_resolve_keeps_the_guide_order():
    ids, _ = resolve_names(["Axe Cat", "Cat"], _RECORDS)
    assert ids == [2, 0]


def test_resolve_reports_unknown_names():
    ids, unmatched = resolve_names(["Cat", "Region Exclusive"], _RECORDS)
    assert (ids, unmatched) == ([0], ["Region Exclusive"])


def test_resolve_normalizes_spelling_differences():
    ids, unmatched = resolve_names(["Li’l Cat"], [{"id": 5, "name": "Li'l Cat"}])
    assert (ids, unmatched) == ([5], [])


def test_resolve_drops_duplicate_entries():
    ids, _ = resolve_names(["Cat", "Cat"], _RECORDS)
    assert ids == [0]
