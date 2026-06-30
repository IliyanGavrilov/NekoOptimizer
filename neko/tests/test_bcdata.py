from pathlib import Path

from neko.bcdata import catalogue_records, fetch_catalogue, names_url, unitbuy_url
from neko.catalogue import Unit
from neko.models import Rarity

FIXTURES = Path(__file__).parent / "fixtures" / "bcdata"
UNITBUY = (FIXTURES / "unitbuy_head.csv").read_text(encoding="utf-8")
CAT_NAMES = (FIXTURES / "Unit_Explanation1_en.csv").read_text(encoding="utf-8")


def fetcher_from(pages):
    async def fetch(url):
        if url not in pages:
            raise FileNotFoundError(url)
        return pages[url]

    return fetch


def test_names_file_is_one_based():
    assert names_url(0).endswith("Unit_Explanation1_en.csv")


async def test_fetch_builds_a_unit_from_both_files():
    fetch = fetcher_from({unitbuy_url(): UNITBUY, names_url(0): CAT_NAMES})
    catalogue = await fetch_catalogue(fetch)
    assert catalogue[0].name == "Cat"


async def test_unit_with_no_name_file_is_dropped():
    fetch = fetcher_from({unitbuy_url(): UNITBUY, names_url(0): CAT_NAMES})
    catalogue = await fetch_catalogue(fetch)
    assert set(catalogue) == {0}


def test_records_are_sorted_by_id():
    catalogue = {2: Unit(2, ("B",), Rarity.RARE), 0: Unit(0, ("A",), Rarity.NORMAL)}
    assert [record["id"] for record in catalogue_records(catalogue)] == [0, 2]
