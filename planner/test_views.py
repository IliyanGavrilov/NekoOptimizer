import pytest

from neko.godfat import BannerRolls, TrackPull
from neko.models import Rarity
from neko.scraper import ScrapeResult
from neko.search import Multi
from planner.models import Banner, Cat, Seed

R = Rarity.RARE
U = Rarity.UBER_SUPER_RARE


def fixed_banners(*pulls):
    def _fetch(seed, count=100):
        return ScrapeResult({"x": BannerRolls(list(pulls), [])}, {})

    return _fetch


@pytest.mark.django_db
def test_get_shows_form(client):
    assert b"<form" in client.get("/").content


@pytest.mark.django_db
def test_targets_grouped_by_banner(client):
    banner = Banner.objects.create(name="Epicfest")
    Cat.objects.create(name="Bahamut").banners.add(banner)
    assert b"Epicfest" in client.get("/").content


@pytest.mark.django_db
def test_post_renders_plan(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_post_persists_seed(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    client.post("/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert Seed.current() == 7


@pytest.mark.django_db
def test_use_wishlist_searches_wanted_cats(client, monkeypatch):
    Cat.objects.create(name="Bahamut", wanted=True)
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/", {"seed": 7, "tickets": 1, "catfood": 0, "use_wishlist": "on"})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_guaranteed_config_reaches_target(client, monkeypatch):
    cat = Cat.objects.create(name="Target")
    result = ScrapeResult(
        {"x": BannerRolls([TrackPull(1, "A", "Filler", U)], [TrackPull(2, "A", "Target", U)])},
        {"x": [Multi(rolls=2, cost=300)]},
    )
    monkeypatch.setattr("planner.views.fetch_banners", lambda seed, count=100: result)
    response = client.post("/", {"seed": 7, "tickets": 0, "catfood": 300, "targets": [cat.pk]})
    assert response.context["plans"][0].targets == frozenset({"Target"})


@pytest.mark.django_db
def test_selected_banners_use_chosen_scrape(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    called = {}

    def fake_for_banners(seed, names, count=100):
        called["names"] = list(names)
        return ScrapeResult({"Pick": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_for_banners", fake_for_banners)
    monkeypatch.setattr("planner.views.fetch_banners", fixed_banners())
    client.post(
        "/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk], "banners": ["Pick"]}
    )
    assert called["names"] == ["Pick"]


@pytest.mark.django_db
def test_prefer_catfood_keeps_the_ticket(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post(
        "/",
        {"seed": 7, "tickets": 1, "catfood": 150, "targets": [cat.pk], "prefer": "catfood"},
    )
    assert response.context["plans"][0].plan.tickets_used == 0


@pytest.mark.django_db
def test_platinum_legend_cap_zero_excludes_the_banner(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    result = ScrapeResult(
        {"Platinum Capsules": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {}
    )
    monkeypatch.setattr("planner.views.fetch_banners", lambda seed, count=100: result)
    response = client.post(
        "/",
        {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk], "platinum_legend_cap": 0},
    )
    assert response.context["plans"] == []


@pytest.mark.django_db
def test_platinum_legend_allowed_by_default(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    result = ScrapeResult(
        {"Platinum Capsules": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {}
    )
    monkeypatch.setattr("planner.views.fetch_banners", lambda seed, count=100: result)
    response = client.post("/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert response.context["plans"][0].targets == frozenset({"Bahamut"})


@pytest.mark.django_db
def test_explore_mode_reaches_target_beyond_budget(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners",
        fixed_banners(TrackPull(1, "A", "Filler", R), TrackPull(2, "A", "Bahamut", U)),
    )
    response = client.post(
        "/", {"seed": 7, "tickets": 0, "catfood": 0, "targets": [cat.pk], "explore": "on"}
    )
    assert response.context["plans"][0].plan.cost == 300


@pytest.mark.django_db
def test_explore_mode_scrapes_to_the_horizon(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    seen = {}

    def fake(seed, count=100):
        seen["count"] = count
        return ScrapeResult({"x": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    data = {"seed": 7, "tickets": 0, "catfood": 0, "targets": [cat.pk]}
    client.post("/", {**data, "explore": "on", "horizon": 500})
    assert seen["count"] == 500


@pytest.mark.django_db
def test_requires_targets_or_wishlist(client):
    response = client.post("/", {"seed": 7, "tickets": 1, "catfood": 0})
    assert response.context["plans"] is None


@pytest.mark.django_db
def test_negative_resources_rejected(client):
    cat = Cat.objects.create(name="Bahamut")
    response = client.post("/", {"seed": 7, "tickets": -1, "catfood": 0, "targets": [cat.pk]})
    assert response.context["plans"] is None
