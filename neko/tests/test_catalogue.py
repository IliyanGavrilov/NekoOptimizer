from pathlib import Path

from neko.catalogue import build_catalogue, parse_forms, parse_pools, parse_rarities, parse_sets
from neko.models import Rarity

FIXTURES = Path(__file__).parent / "fixtures" / "bcdata"
UNITBUY = (FIXTURES / "unitbuy_head.csv").read_text(encoding="utf-8")
GATYA = (FIXTURES / "GatyaDataSetR1_head.csv").read_text(encoding="utf-8")
CAT_NAMES = (FIXTURES / "Unit_Explanation1_en.csv").read_text(encoding="utf-8")


def test_form_name_drops_flavour_text():
    assert parse_forms(CAT_NAMES)[0] == "Cat"


def test_forms_keep_every_evolution_in_order():
    assert parse_forms(CAT_NAMES) == ("Cat", "Macho Cat", "Mohawk Cat")


def test_rarity_is_keyed_by_unit_id():
    assert parse_rarities(UNITBUY)[0] == Rarity.NORMAL


def test_short_rows_have_no_rarity():
    assert parse_rarities("1,2,3") == {}


def test_unknown_rarity_code_is_skipped():
    assert parse_rarities(",".join(["0"] * 13 + ["9"])) == {}


def test_pool_excludes_terminator_and_comment():
    assert parse_pools(GATYA)[2] == [161, 160, 64, 65, 66, 67, 68]


def test_catalogue_name_is_the_base_form():
    catalogue = build_catalogue({0: Rarity.NORMAL}, {0: ("Cat", "Macho Cat")})
    assert catalogue[0].name == "Cat"


PICTURE_BOOK = "\n".join(
    [
        "＠|＠|＠|EVOLVE at Level 10",  # 0: a Normal cat, no set
        "From Rare Capsule Event|The Dynamites|＠|EVOLVE at Level 10",  # 1
        "Collect from limited event stage|Horde of Cats|＠",  # 2: stage name, not a set
        "Collect from Limited Rare Capsules|Xmas Gals|＠",  # 3
        "From Rare Capsule Event|＠|＠",  # 4: capsule cat without a set name
    ]
)


def test_parse_sets_names_only_capsule_sets():
    assert parse_sets(PICTURE_BOOK) == {1: "The Dynamites", 3: "Xmas Gals"}


def test_catalogue_carries_the_set_name():
    catalogue = build_catalogue(
        {1: Rarity.UBER_SUPER_RARE}, {1: ("Ice Cat",)}, {1: "The Dynamites"}
    )
    assert catalogue[1].set_name == "The Dynamites"


def test_unit_without_rarity_is_dropped():
    assert build_catalogue({}, {0: ("Cat",)}) == {}


def test_unit_without_a_name_is_dropped():
    assert build_catalogue({0: Rarity.NORMAL}, {0: ()}) == {}
