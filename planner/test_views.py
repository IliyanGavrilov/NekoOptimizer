from itertools import count

import pytest

from neko.godfat import BannerRolls, TrackPull
from neko.models import Rarity
from neko.scraper import ScrapeResult
from neko.search import Multi
from planner.models import Banner, Cat, Seed, Unit

R = Rarity.RARE
U = Rarity.UBER_SUPER_RARE

_ids = count(1)


def cat_with_unit(name, owned=False, wanted=False):
    unit = Unit.objects.create(unit_id=next(_ids), name=name, owned=owned, wanted=wanted)
    return Cat.objects.create(name=name, unit=unit)


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
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_post_persists_seed(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert Seed.current() == 7


@pytest.mark.django_db
def test_use_wishlist_searches_wanted_cats(client, monkeypatch):
    cat_with_unit("Bahamut", wanted=True)
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "use_wishlist": "on"})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_guaranteed_config_reaches_target(client, monkeypatch):
    cat = Cat.objects.create(name="Target")
    result = ScrapeResult(
        {"x": BannerRolls([TrackPull(1, "A", "Filler", U)], [TrackPull(2, "A", "Target", U)])},
        {"x": [Multi(rolls=2, cost=300)]},
    )
    monkeypatch.setattr("planner.views.fetch_banners", lambda seed, count=100: result)
    response = client.post("/plan/", {"seed": 7, "tickets": 0, "catfood": 300, "targets": [cat.pk]})
    assert b"Target" in response.content


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
        "/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk], "banners": ["Pick"]}
    )
    assert called["names"] == ["Pick"]


@pytest.mark.django_db
def test_prefer_catfood_keeps_the_ticket(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post(
        "/plan/",
        {"seed": 7, "tickets": 1, "catfood": 150, "targets": [cat.pk], "prefer": "catfood"},
    )
    # prefer=catfood spends the draw, not the ticket: cost shows catfood, no ticket.
    assert b"150 catfood" in response.content


@pytest.mark.django_db
def test_platinum_legend_cap_zero_excludes_the_banner(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    result = ScrapeResult(
        {"Platinum Capsules": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {}
    )
    monkeypatch.setattr("planner.views.fetch_banners", lambda seed, count=100: result)
    response = client.post(
        "/plan/",
        {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk], "platinum_legend_cap": 0},
    )
    # Capped out, the only target is unreachable: it shows as a "Not found" subset row.
    assert b"Not found" in response.content


@pytest.mark.django_db
def test_platinum_legend_allowed_by_default(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    result = ScrapeResult(
        {"Platinum Capsules": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {}
    )
    monkeypatch.setattr("planner.views.fetch_banners", lambda seed, count=100: result)
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0, "targets": [cat.pk]})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_explore_mode_funds_single_pulls_with_tickets(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners",
        fixed_banners(TrackPull(1, "A", "Filler", R), TrackPull(2, "A", "Bahamut", U)),
    )
    # Two single pulls reach Bahamut: explore must bill them as tickets, not catfood.
    response = client.post(
        "/plan/", {"seed": 7, "tickets": 0, "catfood": 0, "targets": [cat.pk], "explore": "on"}
    )
    assert b"2 tickets" in response.content


@pytest.mark.django_db
def test_multiple_targets_list_every_subset(client, monkeypatch):
    a = Cat.objects.create(name="Aaa")
    b = Cat.objects.create(name="Bbb")
    monkeypatch.setattr(
        "planner.views.fetch_banners",
        fixed_banners(TrackPull(1, "A", "Aaa", U), TrackPull(2, "A", "Bbb", U)),
    )
    response = client.post(
        "/plan/", {"seed": 7, "tickets": 5, "catfood": 0, "targets": [a.pk, b.pk]}
    )
    html = response.json()["solutions_html"]
    # Powerset of two reachable targets: {Aaa}, {Bbb}, {Aaa, Bbb}.
    assert html.count("<details") == 3
    assert "Aaa, Bbb" in html


@pytest.mark.django_db
def test_unreachable_subset_is_listed_not_found(client, monkeypatch):
    a = Cat.objects.create(name="Aaa")
    b = Cat.objects.create(name="Bbb")
    # Only Aaa is on the banner; Bbb (and the pair) can't be reached.
    monkeypatch.setattr("planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Aaa", U)))
    response = client.post(
        "/plan/", {"seed": 7, "tickets": 5, "catfood": 0, "targets": [a.pk, b.pk]}
    )
    html = response.json()["solutions_html"]
    assert "Not found" in html


@pytest.mark.django_db
def test_explore_mode_scrapes_to_the_horizon(client, monkeypatch):
    cat = Cat.objects.create(name="Bahamut")
    seen = {}

    def fake(seed, count=100):
        seen["count"] = count
        return ScrapeResult({"x": BannerRolls([TrackPull(1, "A", "Bahamut", U)], [])}, {})

    monkeypatch.setattr("planner.views.fetch_banners", fake)
    data = {"seed": 7, "tickets": 0, "catfood": 0, "targets": [cat.pk]}
    client.post("/plan/", {**data, "explore": "on", "horizon": 500})
    assert seen["count"] == 500


@pytest.mark.django_db
def test_owned_cats_are_still_targetable(client):
    cat_with_unit("Bahamut", owned=True).banners.add(Banner.objects.create(name="Epic"))
    assert b"Bahamut" in client.get("/").content


@pytest.mark.django_db
def test_seed_field_starts_empty(client):
    Seed.store(42)
    assert b'name="seed" value="42"' not in client.get("/").content


@pytest.mark.django_db
def test_apply_plan_owns_cats_and_clears_wishlist(client):
    cat = cat_with_unit("Bahamut", owned=False, wanted=True)
    client.post("/apply/", {"cats": ["Bahamut"]})
    cat.refresh_from_db()
    assert (cat.owned, cat.wanted) == (True, False)


@pytest.mark.django_db
def test_requires_targets_or_wishlist(client):
    response = client.post("/plan/", {"seed": 7, "tickets": 1, "catfood": 0})
    assert response.status_code == 400


@pytest.mark.django_db
def test_negative_resources_rejected(client):
    cat = Cat.objects.create(name="Bahamut")
    response = client.post("/plan/", {"seed": 7, "tickets": -1, "catfood": 0, "targets": [cat.pk]})
    assert response.status_code == 400


@pytest.mark.django_db
def test_blank_budget_is_treated_as_zero(client, monkeypatch):
    # Explore hides the budget fields, so they submit blank; that must not 400.
    cat = Cat.objects.create(name="Bahamut")
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post(
        "/plan/", {"seed": 7, "tickets": "", "catfood": "", "targets": [cat.pk], "explore": "on"}
    )
    assert response.status_code == 200


@pytest.mark.django_db
def test_tracks_endpoint_lists_the_rolls(client, monkeypatch):
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    response = client.post("/tracks/", {"seed": 7})
    assert b"Bahamut" in response.content


@pytest.mark.django_db
def test_tracks_endpoint_blank_seed_renders_nothing(client):
    assert client.post("/tracks/", {}).content == b""


@pytest.mark.django_db
def test_planner_ships_the_past_group_as_a_lazy_shell(client):
    # The ~2000 Past rows are nearly all of the page; they must not render inline.
    html = client.get("/").content
    assert b'id="pastGroup"' in html
    assert html.count(b"banner-include") < 100


@pytest.mark.django_db
def test_picker_past_serves_the_past_rows(client):
    html = client.get("/picker/past/").content
    assert html.count(b"banner-include") > 1000


@pytest.mark.django_db
def test_tracks_endpoint_renders_the_guaranteed_column(client, monkeypatch):
    rolls = BannerRolls(
        [TrackPull(1, "A", "Shaman Cat", R)], [TrackPull(1, "A", "Trixi the Merc", U)]
    )
    monkeypatch.setattr(
        "planner.views.fetch_banners", lambda seed, count=100: ScrapeResult({"x": rolls}, {})
    )
    response = client.post("/tracks/", {"seed": 7})
    assert b"Guaranteed" in response.content
    assert b"Trixi the Merc" in response.content


@pytest.mark.django_db
def test_tracks_endpoint_hides_the_guaranteed_column_without_a_guarantee(client, monkeypatch):
    # No selected banner runs a guarantee, so the extra columns stay out of the table.
    monkeypatch.setattr(
        "planner.views.fetch_banners", fixed_banners(TrackPull(1, "A", "Bahamut", U))
    )
    assert b"Guaranteed" not in client.post("/tracks/", {"seed": 7}).content
