from neko.tierdata import parse_tiers, resolve_names, tier_records


def _records(*rows):
    """Catalogue records as parse_tiers/resolve_names expect them: id, name, forms."""
    return [{"id": i, "name": name, "forms": list(forms)} for i, name, *forms in rows]


def test_parse_reads_tier_and_names():
    assert parse_tiers("<p>S: Kasli the Bane, Phono</p>") == [
        ("S", "Kasli the Bane", None),
        ("S", "Phono", None),
    ]


def test_parse_pulls_the_uf_ut_boost_off_an_entry():
    assert parse_tiers("<li>SSS: Lasvoss (UF), Miyabi (UT)</li>") == [
        ("SSS", "Lasvoss", "UF"),
        ("SSS", "Miyabi", "UT"),
    ]


def test_parse_ignores_lines_that_are_not_tier_rows():
    assert parse_tiers("<h1>Tier List</h1><p>Updated today</p>") == []


def test_parse_unescapes_html_entities_in_names():
    assert parse_tiers("<p>A: Li&#39;l Valkyrie</p>") == [("A", "Li'l Valkyrie", None)]


def test_parse_skips_script_and_style_blocks():
    page = "<style>S: Nope</style><script>SS: Nope</script><p>S: Real</p>"
    assert parse_tiers(page) == [("S", "Real", None)]


def test_resolve_matches_an_exact_catalogue_name():
    records = _records((5, "Bahamut Cat"))
    assert resolve_names(["Bahamut Cat"], records) == {"Bahamut Cat": 5}


def test_resolve_matches_on_a_form_name():
    records = _records((7, "Crazed Cat", "Manic Macho Legs"))
    assert resolve_names(["Manic Macho Legs"], records) == {"Manic Macho Legs": 7}


def test_resolve_uses_the_alias_table_when_names_collide():
    # "Zeus" alone doesn't uniquely name the unit; the alias pins it to id 257.
    records = _records((257, "Thunder God Zeus"), (999, "Baby Zeus"))
    assert resolve_names(["Zeus"], records) == {"Zeus": 257}


def test_resolve_falls_back_to_a_token_subset():
    records = _records((3, "Winter General Kaihime"))
    assert resolve_names(["Winter Kaihime"], records) == {"Winter Kaihime": 3}


def test_longer_name_claims_its_unit_before_the_bare_one():
    records = _records((10, "Keiji"), (11, "Keiji Claus"))
    assert resolve_names(["Keiji", "Keiji Claus"], records) == {"Keiji": 10, "Keiji Claus": 11}


def test_resolve_leaves_an_unknown_name_out():
    assert resolve_names(["Ghost Uber"], _records((1, "Bahamut Cat"))) == {}


def test_tier_records_keep_order_and_use_the_canonical_name():
    rows = [("S", "Baha", None), ("A", "Manic", None)]
    resolution = {"Baha": 5, "Manic": 7}
    records = _records((5, "Bahamut Cat"), (7, "Crazed Cat"))
    doc = tier_records(rows, resolution, records)
    assert doc["tiers"] == [
        {"tier": "S", "entries": [{"name": "Bahamut Cat", "unit_id": 5, "boost": None}]},
        {"tier": "A", "entries": [{"name": "Crazed Cat", "unit_id": 7, "boost": None}]},
    ]


def test_tier_records_keep_unresolved_names_with_a_null_id():
    doc = tier_records([("S", "Mystery", None)], {}, _records((5, "Bahamut Cat")))
    assert doc["tiers"] == [
        {"tier": "S", "entries": [{"name": "Mystery", "unit_id": None, "boost": None}]}
    ]


def test_tier_records_order_follows_the_tier_ranking_not_input_order():
    rows = [("A", "One", None), ("SSS", "Two", None)]
    resolution = {"One": 1, "Two": 2}
    records = _records((1, "One"), (2, "Two"))
    doc = tier_records(rows, resolution, records)
    assert [row["tier"] for row in doc["tiers"]] == ["SSS", "A"]
