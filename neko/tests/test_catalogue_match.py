from neko.catalogue import Unit, match_names, name_index
from neko.models import Rarity


def test_name_index_maps_base_name_to_id():
    assert name_index([Unit(25, ("Bahamut Cat",), Rarity.SPECIAL)]) == {"Bahamut Cat": 25}


def test_matched_name_carries_its_unit_id():
    matches, _ = match_names(["Cat"], {"Cat": 0})
    assert matches == {"Cat": 0}


def test_unknown_name_is_unmatched():
    _, unmatched = match_names(["Ghost Cat"], {"Cat": 0})
    assert unmatched == ["Ghost Cat"]


def test_unmatched_names_are_deduped_and_sorted():
    _, unmatched = match_names(["Beta", "Alpha", "Beta"], {})
    assert unmatched == ["Alpha", "Beta"]
