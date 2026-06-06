from pathlib import Path

import pytest

from neko.godfat import parse_rolls
from neko.models import Rarity

FIXTURE = (Path(__file__).parent / "fixtures" / "godfat_sample.html").read_text(encoding="utf-8")


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
