from datetime import date
from pathlib import Path

import pytest

from neko.godfat import parse_events, parse_guaranteed, parse_rerolls, parse_rolls
from neko.models import Rarity

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = (FIXTURES / "godfat_sample.html").read_text(encoding="utf-8")
EVENTS = (FIXTURES / "godfat_events.html").read_text(encoding="utf-8")


def by_key(html):
    return {(pull.position, pull.track): pull for pull in parse_rolls(html)}


def test_extracts_results_in_order_ignoring_other_cells():
    order = [(pull.position, pull.track) for pull in parse_rolls(FIXTURE)]
    assert order == [(1, "A"), (1, "B"), (2, "A"), (2, "B"), (3, "A"), (3, "B"), (4, "A"), (4, "B")]


def test_extracts_cat_name_without_paw():
    assert by_key(FIXTURE)[(1, "A")].cat == "Luxury Bath Cat"


def test_empty_html_yields_no_pulls():
    assert parse_rolls("") == []


@pytest.mark.parametrize(
    "css,expected",
    [
        ("rare", Rarity.RARE),
        ("supa", Rarity.SUPER_RARE),
        ("uber", Rarity.UBER_SUPER_RARE),
        ("legend", Rarity.LEGEND_RARE),
        ("exclusive", Rarity.UBER_SUPER_RARE),
        ("supa_fest", Rarity.SUPER_RARE),
        ("uber_fest", Rarity.UBER_SUPER_RARE),
    ],
)
def test_maps_cell_class_to_rarity(css, expected):
    html = f'<table><td class="cat pick {css}" onclick="pick(\'1A\')">X</td></table>'
    assert parse_rolls(html)[0].rarity == expected


def test_parses_event_ids_skipping_blank_options():
    ids = [event.event_id for event in parse_events(EVENTS)]
    assert ids == ["2026-06-26_1052", "2026-04-24_1047", "2026-01-01_900"]


def test_keeps_colon_inside_event_name():
    assert parse_events(EVENTS)[0].name == "Trixi joins the Capsules! ★Check banner: details!"


def test_parses_event_date_range():
    event = parse_events(EVENTS)[0]
    assert (event.start, event.end) == (date(2026, 6, 26), date(2026, 7, 3))


def test_missing_select_yields_no_events():
    assert parse_events("<html></html>") == []


def test_parse_guaranteed_extracts_ubers_stripping_arrows():
    names = {(p.position, p.track): p.cat for p in parse_guaranteed(FIXTURE)}
    assert names == {(1, "A"): "Guaranteed Uber", (2, "B"): "Another Uber"}


def test_parse_guaranteed_marks_results_uber():
    assert all(p.rarity == Rarity.UBER_SUPER_RARE for p in parse_guaranteed(FIXTURE))


def test_parse_guaranteed_reads_legend_rarity_from_cell_class():
    html = '<table><td class="cat pick legend" onclick="pick(\'1AG\')">Wonder MOMOCO</td></table>'
    assert parse_guaranteed(html)[0].rarity == Rarity.LEGEND_RARE


def test_parse_guaranteed_ignores_the_rolled_slot_band():
    # godfat tags this guaranteed uber's cell "rare" (the slot's band); it must stay uber.
    html = '<table><td class="cat pick rare" onclick="pick(\'9AG\')">Lightmother Aset</td></table>'
    assert parse_guaranteed(html)[0].rarity == Rarity.UBER_SUPER_RARE


def test_parse_rerolls_extracts_the_rerolled_cat_stripping_the_arrow():
    html = (
        '<table><td class="cat pick rare" onclick="pick(\'7AR\')">'
        "Jurassic Cat \U0001f43e -&gt; 8B</td></table>"
    )
    pull = parse_rerolls(html)[0]
    assert (pull.position, pull.track, pull.cat) == (7, "A", "Jurassic Cat")


def test_parse_rerolls_strips_reroll_marker_from_backward_landing():
    # A backward arrow onto another reroll cell reads "<- 62AR"; the trailing R must not
    # glue onto the cat name (real godfat: seed 1893568593 gave "ROnmyoji Cat").
    html = (
        '<table><td class="cat pick rare" onclick="pick(\'60BR\')">'
        "&lt;- 62AR Onmyoji Cat \U0001f43e</td></table>"
    )
    pull = parse_rerolls(html)[0]
    assert (pull.position, pull.track, pull.cat) == (60, "B", "Onmyoji Cat")


def test_parse_rolls_ignores_reroll_cells():
    html = '<table><td class="cat pick rare" onclick="pick(\'7AR\')">Jurassic Cat</td></table>'
    assert parse_rolls(html) == []
