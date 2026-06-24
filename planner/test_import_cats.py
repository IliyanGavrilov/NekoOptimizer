import pytest
from django.core.management import call_command

from neko.godfat import BannerRolls, TrackPull
from neko.models import Rarity
from neko.scraper import ScrapeResult
from planner.models import Cat
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
def test_import_skips_existing_cats():
    Cat.objects.create(name="Bahamut")
    assert import_cats(banners(x=[TrackPull(1, "A", "Bahamut", U)])) == 0


@pytest.mark.django_db
def test_import_stores_rarity():
    import_cats(banners(x=[TrackPull(1, "A", "Bahamut", U)]))
    assert Cat.objects.get(name="Bahamut").rarity == "Uber Super Rare"


@pytest.mark.django_db
def test_command_populates_catalogue(monkeypatch):
    monkeypatch.setattr(
        "planner.management.commands.import_cats.fetch_banners",
        lambda seed: ScrapeResult(banners(x=[TrackPull(1, "A", "Bahamut", U)]), {}),
    )
    call_command("import_cats", 7)
    assert Cat.objects.filter(name="Bahamut").exists()
