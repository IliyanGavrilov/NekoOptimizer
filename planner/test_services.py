from datetime import date, timedelta

import pytest

from neko.godfat import BannerRolls, TrackPull
from neko.models import Rarity
from planner.models import Banner, Cat
from planner.services import catalogue, dated_catalogue, equivalent_banners


@pytest.mark.django_db
def test_catalogue_nests_rarity_under_banner():
    cat = Cat.objects.create(name="Bahamut", rarity="Uber Super Rare")
    cat.banners.add(Banner.objects.create(name="Epicfest"))
    assert catalogue([cat]) == [("Epicfest", [("Uber Super Rare", [cat])])]


@pytest.mark.django_db
def test_catalogue_files_bannerless_cat_under_other():
    cat = Cat.objects.create(name="Bahamut")
    assert catalogue([cat]) == [("Other", [("Unknown", [cat])])]


@pytest.mark.django_db
def test_catalogue_lists_cat_in_every_banner():
    cat = Cat.objects.create(name="Bahamut")
    cat.banners.add(Banner.objects.create(name="Epicfest"), Banner.objects.create(name="Uberfest"))
    assert [banner for banner, _ in catalogue([cat])] == ["Epicfest", "Uberfest"]


@pytest.mark.django_db
def test_catalogue_orders_rarities_cheapest_to_rarest():
    banner = Banner.objects.create(name="Uberfest")
    legend = Cat.objects.create(name="Mecha", rarity="Legend Rare")
    rare = Cat.objects.create(name="Pogo", rarity="Rare")
    legend.banners.add(banner)
    rare.banners.add(banner)
    rarities = [rarity for rarity, _ in catalogue([legend, rare])[0][1]]
    assert rarities == ["Rare", "Legend Rare"]


@pytest.mark.django_db
def test_catalogue_reverse_rarity_lists_rarest_first():
    banner = Banner.objects.create(name="Uberfest")
    legend = Cat.objects.create(name="Mecha", rarity="Legend Rare")
    rare = Cat.objects.create(name="Pogo", rarity="Rare")
    legend.banners.add(banner)
    rare.banners.add(banner)
    rarities = [rarity for rarity, _ in catalogue([legend, rare], reverse_rarity=True)[0][1]]
    assert rarities == ["Legend Rare", "Rare"]


def _dated_banner(name, start, end):
    banner = Banner.objects.create(name=name, start=start, end=end)
    cat = Cat.objects.create(name=f"{name} cat")
    cat.banners.add(banner)
    return cat


@pytest.mark.django_db
def test_dated_catalogue_splits_now_upcoming_and_past():
    today = date(2026, 6, 15)
    day = timedelta(days=1)
    _dated_banner("Soon", today + 5 * day, today + 10 * day)
    _dated_banner("Later", today + 20 * day, today + 25 * day)
    _dated_banner("ActiveNow", today - day, today + day)
    _dated_banner("OldPast", today - 30 * day, today - 20 * day)
    _dated_banner("RecentPast", today - 6 * day, today - 2 * day)

    groups = dated_catalogue(Cat.objects.all(), today=today)
    labelled = {label: [name for name, _dates, _ in sections] for label, sections in groups}
    assert labelled["Available now"] == ["ActiveNow"]
    assert labelled["Upcoming"] == ["Soon", "Later"]
    assert labelled["Past"] == ["RecentPast", "OldPast"]


@pytest.mark.django_db
def test_dated_catalogue_carries_banner_dates():
    today = date(2026, 6, 15)
    run = (today, today + timedelta(days=3))
    banner = Banner.objects.create(name="ActiveNow", start=run[0], end=run[1])
    Cat.objects.create(name="Cat").banners.add(banner)
    _label, sections = dated_catalogue(Cat.objects.all(), today=today)[0]
    assert sections[0][1] == run


def test_equivalent_banners_groups_identical_roll_sequences():
    same = [TrackPull(1, "A", "Bahamut", Rarity.UBER_SUPER_RARE)]
    other = [TrackPull(1, "A", "Kasli", Rarity.UBER_SUPER_RARE)]
    banners = {
        "A": BannerRolls(same, []),
        "B": BannerRolls(same, []),
        "C": BannerRolls(other, []),
    }
    equivalent = equivalent_banners(banners)
    assert sorted(equivalent["A"]) == ["A", "B"]
    assert equivalent["C"] == ["C"]
