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


def test_forms_drop_an_unreleased_placeholder_that_repeats_the_previous_name():
    assert parse_forms("Kasli|x\nDaughter|x\nDaughter|x") == ("Kasli", "Daughter")


def test_forms_keep_a_name_that_repeats_non_consecutively():
    assert parse_forms("Cat|x\nMacho|x\nCat|x") == ("Cat", "Macho", "Cat")


def test_forms_split_on_the_japanese_feeds_commas():
    text = "ネコ,安価で生産できる基本キャラ,\nネコビルダー,鍛えぬいた筋肉が,"
    assert parse_forms(text, "jp") == ("ネコ", "ネコビルダー")


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
        "＠|＠|＠|EVOLVE at Level 10",
        "From Rare Capsule Event|The Dynamites|＠|EVOLVE at Level 10",
        "Collect from limited event stage|Horde of Cats|＠",
        "Collect from Limited Rare Capsules|Xmas Gals|＠",
        "From Rare Capsule Event|＠|＠",
    ]
)


def test_parse_sets_names_only_capsule_sets():
    assert parse_sets(PICTURE_BOOK) == {1: "The Dynamites", 3: "Xmas Gals"}


# The same rows as the Japanese feed spells them: comma-separated, the capsule source in
# its own words, and the set name wrapped in a sentence.
JP_PICTURE_BOOK = "\n".join(
    [
        "日本編第3章「西表島」クリア後に解放,＠,＠",
        "レアガチャイベント,「ネコルガ族」で入手可能,＠",
        "期間限定レアガチャイベント,「メリーゴールド」で入手可能,＠",
    ]
)


def test_parse_sets_reads_the_regions_own_capsule_sources():
    assert sorted(parse_sets(JP_PICTURE_BOOK, "jp")) == [1, 2]


def test_parse_sets_unwraps_a_set_name_quoted_inside_a_sentence():
    assert parse_sets(JP_PICTURE_BOOK, "jp")[1] == "ネコルガ族"


def test_catalogue_carries_the_set_name():
    catalogue = build_catalogue(
        {1: Rarity.UBER_SUPER_RARE}, {1: ("Ice Cat",)}, {1: "The Dynamites"}
    )
    assert catalogue[1].set_name == "The Dynamites"


def test_unit_without_rarity_is_dropped():
    assert build_catalogue({}, {0: ("Cat",)}) == {}


def test_unit_without_a_name_is_dropped():
    assert build_catalogue({0: Rarity.NORMAL}, {0: ()}) == {}
