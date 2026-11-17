from neko.bcinfo import fill_evolve, fill_forms, parse_evolve, parse_units
from neko.catalogue import Unit
from neko.models import Rarity

CAT = "rarity\tform_count\n0\t3\n4\t2\n4\t2\n"
NAMES = (
    "jp\ttw\ten\tkr\n"
    "ネコ|ネコビルダー\t貓咪\tCat|Macho Cat\t고양이\n"
    "りゅういち|りゅういち＆りゅうじ\t龍一\tRyuichi|Ryuichi & Ryuji\t류이치\n"
    "悠久山安慈\t\t|\t\n"
)


def test_a_unit_gets_its_versions_form_names():
    assert parse_units(CAT, NAMES, "en")[1].forms == ("Ryuichi", "Ryuichi & Ryuji")


def test_a_unit_gets_its_rarity_by_code():
    assert parse_units(CAT, NAMES, "jp")[1].rarity is Rarity.UBER_SUPER_RARE


def test_a_unit_the_version_has_not_released_is_left_out():
    assert 2 not in parse_units(CAT, NAMES, "en") and 2 in parse_units(CAT, NAMES, "jp")


# Voli: Japan already names the Ultra Form, English doesn't yet.
EVOLVE_CAT = "rarity\tevol_require\tevol4_require\n4\t1000000!0|4!38\t2000000!0|2!181|1!183\n"
EVOLVE_NAMES = "jp\ttw\ten\tkr\nボルト|ピカボルト|ギガボルト|テラボルタ\t\tVoli|Volta|Gigavolta\t\n"
TF = {"level": None, "xp": 1000000, "items": [[38, 4]]}
UF = {"level": None, "xp": 2000000, "items": [[181, 2], [183, 1]]}


def test_an_evolution_counts_once_the_version_names_its_form():
    assert parse_evolve(EVOLVE_CAT, EVOLVE_NAMES, "jp") == {0: {"tf": TF, "uf": UF}}


def test_an_evolution_another_version_got_first_stays_out():
    assert parse_evolve(EVOLVE_CAT, EVOLVE_NAMES, "en") == {0: {"tf": TF, "uf": None}}


def test_a_unit_the_version_has_not_released_has_no_evolutions():
    assert parse_evolve(EVOLVE_CAT, EVOLVE_NAMES, "kr") == {}


def test_filling_evolutions_adds_only_the_forms_the_mirror_lacks():
    own = {"level": 30, "xp": 5, "items": []}
    assert fill_evolve({0: {"tf": own, "uf": None}}, {0: {"tf": TF, "uf": UF}}) == {
        0: {"tf": own, "uf": UF}
    }


def test_filling_forms_appends_the_newer_ones_and_keeps_the_mirrors_names():
    mirror = Unit(1, ("Voli", "Volta"), Rarity.UBER_SUPER_RARE, "Elemental Pixies")
    newer = Unit(1, ("voli", "volta", "Teravolta"), Rarity.UBER_SUPER_RARE)
    assert fill_forms({1: mirror}, {1: newer})[1] == Unit(
        1, ("Voli", "Volta", "Teravolta"), Rarity.UBER_SUPER_RARE, "Elemental Pixies"
    )


def test_filling_forms_adds_the_units_the_mirror_lacks():
    newer = Unit(2, ("Ryuichi",), Rarity.UBER_SUPER_RARE)
    assert fill_forms({}, {2: newer}) == {2: newer}
