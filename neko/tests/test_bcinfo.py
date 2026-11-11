from neko.bcinfo import parse_units
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
