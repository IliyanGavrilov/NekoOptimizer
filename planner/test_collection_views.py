from itertools import count

import pytest

from planner.models import Unit

_ids = count(1)


def unit(name, rarity="Uber Super Rare", **flags):
    return Unit.objects.create(unit_id=next(_ids), name=name, rarity=rarity, **flags)


@pytest.mark.django_db
def test_collection_lists_catalogue_units(client):
    unit("Bahamut")
    assert b"Bahamut" in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_hides_unnamed_units(client):
    unit("861_1")
    assert b"861_1" not in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_groups_by_rarity(client):
    unit("Bahamut", rarity="Uber Super Rare")
    assert b"Uber Super Rare" in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_offers_both_views(client):
    assert b"By gacha set" in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_shows_a_named_set(client):
    unit("Ice Cat", set_name="The Dynamites")
    assert b"The Dynamites" in client.get("/collection/").content


@pytest.mark.django_db
def test_toggle_owned_flips_flag(client):
    u = unit("Bahamut")
    client.post("/collection/toggle/", {"pk": u.pk, "field": "owned"})
    u.refresh_from_db()
    assert u.owned is True


@pytest.mark.django_db
def test_toggle_wanted_twice_returns_to_false(client):
    u = unit("Bahamut")
    client.post("/collection/toggle/", {"pk": u.pk, "field": "wanted"})
    client.post("/collection/toggle/", {"pk": u.pk, "field": "wanted"})
    u.refresh_from_db()
    assert u.wanted is False


@pytest.mark.django_db
def test_toggle_rejects_unknown_field(client):
    u = unit("Bahamut")
    assert client.post("/collection/toggle/", {"pk": u.pk, "field": "rarity"}).status_code == 400


@pytest.mark.django_db
def test_bulk_owns_every_unit(client):
    units = [unit("Bahamut"), unit("Kasli")]
    client.post("/collection/bulk/", {"field": "owned", "pk": [u.pk for u in units]})
    assert all(u.owned for u in Unit.objects.all())


@pytest.mark.django_db
def test_bulk_clears_a_fully_owned_section(client):
    units = [unit("Bahamut", owned=True), unit("Kasli", owned=True)]
    client.post("/collection/bulk/", {"field": "owned", "pk": [u.pk for u in units]})
    assert not Unit.objects.filter(owned=True).exists()


@pytest.mark.django_db
def test_bulk_wishlist_stars_owned_units_too(client):
    owned = unit("Bahamut", owned=True)
    missing = unit("Kasli")
    client.post("/collection/bulk/", {"field": "wanted", "pk": [owned.pk, missing.pk]})
    owned.refresh_from_db()
    missing.refresh_from_db()
    assert (owned.wanted, missing.wanted) == (True, True)


@pytest.mark.django_db
def test_bulk_rejects_unknown_field(client):
    assert client.post("/collection/bulk/", {"field": "rarity"}).status_code == 400
