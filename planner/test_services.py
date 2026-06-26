import pytest

from planner.models import Banner, Cat
from planner.services import group_cats


@pytest.mark.django_db
def test_group_by_banner_puts_cat_under_its_banner():
    cat = Cat.objects.create(name="Bahamut")
    cat.banners.add(Banner.objects.create(name="Epicfest"))
    assert group_cats([cat]) == [("Epicfest", [cat])]


@pytest.mark.django_db
def test_group_by_banner_files_bannerless_cat_under_other():
    cat = Cat.objects.create(name="Bahamut")
    assert group_cats([cat]) == [("Other", [cat])]


@pytest.mark.django_db
def test_group_by_banner_lists_cat_in_every_banner():
    cat = Cat.objects.create(name="Bahamut")
    cat.banners.add(Banner.objects.create(name="Epicfest"), Banner.objects.create(name="Uberfest"))
    assert [heading for heading, _ in group_cats([cat])] == ["Epicfest", "Uberfest"]


@pytest.mark.django_db
def test_group_by_rarity_orders_cheapest_to_rarest():
    legend = Cat.objects.create(name="Mecha", rarity="Legend Rare")
    rare = Cat.objects.create(name="Pogo", rarity="Rare")
    headings = [heading for heading, _ in group_cats([legend, rare], "rarity")]
    assert headings == ["Rare", "Legend Rare"]


@pytest.mark.django_db
def test_group_by_rarity_files_blank_rarity_under_unknown():
    cat = Cat.objects.create(name="Mystery")
    assert group_cats([cat], "rarity") == [("Unknown", [cat])]
