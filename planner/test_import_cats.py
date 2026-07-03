import pytest
from django.core.management import call_command

from neko.models import BannerRolls, Rarity, TrackPull
from neko.roller import RollResult
from planner.models import Banner, Cat, Unit
from planner.services import import_cats

U = Rarity.UBER_SUPER_RARE
R = Rarity.RARE


def banners(**pulls_by_banner):
    return {name: BannerRolls(list(pulls), []) for name, pulls in pulls_by_banner.items()}


@pytest.mark.django_db
def test_import_counts_distinct_new_cats():
    catalogue = banners(
        x=[TrackPull(1, "A", "Bahamut", U), TrackPull(2, "A", "Bahamut", U)],
        y=[TrackPull(1, "A", "Cat", R)],
    )
    assert import_cats(catalogue) == 2


@pytest.mark.django_db
def test_import_includes_guaranteed_ubers():
    catalogue = {"x": BannerRolls([], [TrackPull(11, "A", "Kasli", U)])}
    assert import_cats(catalogue) == 1


@pytest.mark.django_db
def test_import_links_cats_to_their_banner():
    import_cats(banners(Epicfest=[TrackPull(1, "A", "Bahamut", U)]))
    assert list(Banner.objects.get(name="Epicfest").cats.values_list("name", flat=True)) == [
        "Bahamut"
    ]


@pytest.mark.django_db
def test_import_skips_existing_cats():
    Cat.objects.create(name="Bahamut")
    assert import_cats(banners(x=[TrackPull(1, "A", "Bahamut", U)])) == 0


@pytest.mark.django_db
def test_import_stores_rarity():
    import_cats(banners(x=[TrackPull(1, "A", "Bahamut", U)]))
    assert Cat.objects.get(name="Bahamut").rarity == "Uber Super Rare"


@pytest.mark.django_db
def test_import_corrects_stale_rarity():
    Cat.objects.create(name="Wonder MOMOCO", rarity="Uber Super Rare")
    import_cats(banners(x=[TrackPull(1, "A", "Wonder MOMOCO", Rarity.LEGEND_RARE)]))
    assert Cat.objects.get(name="Wonder MOMOCO").rarity == "Legend Rare"


@pytest.mark.django_db
def test_import_stores_banner_dates():
    from datetime import date

    run = (date(2026, 2, 1), date(2026, 2, 8))
    import_cats(banners(Epicfest=[TrackPull(1, "A", "Bahamut", U)]), {"Epicfest": run})
    banner = Banner.objects.get(name="Epicfest")
    assert (banner.start, banner.end) == run


@pytest.mark.django_db
def test_import_links_cat_to_its_unit():
    Unit.objects.create(unit_id=25, name="Bahamut")
    import_cats(banners(x=[TrackPull(1, "A", "Bahamut", U)]))
    assert Cat.objects.get(name="Bahamut").unit.unit_id == 25


@pytest.mark.django_db
def test_import_gives_an_uncatalogued_cat_a_provisional_unit():
    import_cats(banners(x=[TrackPull(1, "A", "Nezuko Kamado", U)]))
    assert Cat.objects.get(name="Nezuko Kamado").unit.canonical is False


@pytest.mark.django_db
def test_command_populates_catalogue(monkeypatch):
    monkeypatch.setattr(
        "planner.management.commands.import_cats.fetch_banners",
        lambda seed: RollResult(banners(x=[TrackPull(1, "A", "Bahamut", U)]), {}),
    )
    call_command("import_cats", 7)
    assert Cat.objects.filter(name="Bahamut").exists()
