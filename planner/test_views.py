import pytest

from neko.godfat import TrackPull
from neko.models import Rarity
from planner.models import Cat, Seed

U = Rarity.UBER_SUPER_RARE


def fixed_banners(*pulls):
    def _fetch(seed):
        return {"x": list(pulls)}

    return _fetch


@pytest.mark.django_db
def test_get_shows_form(client):
    assert b"<form" in client.get("/").content


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
def test_invalid_input_renders_no_plan(client):
    cat = Cat.objects.create(name="Bahamut")
    response = client.post("/", {"seed": 7, "tickets": -1, "catfood": 0, "targets": [cat.pk]})
    assert response.context["plans"] is None
