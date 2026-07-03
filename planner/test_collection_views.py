from itertools import count

import pytest

from planner.models import Cat, Unit

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
def test_collection_lists_unit_once(client):
    unit("Bahamut")
    assert client.get("/collection/").content.count(b">Bahamut</button>") == 1


@pytest.mark.django_db
def test_add_cat_creates_it(client):
    client.post("/collection/", {"name": "Kasli", "rarity": "Uber Super Rare"})
    assert Cat.objects.filter(name="Kasli").exists()


@pytest.mark.django_db
def test_added_cat_gets_a_provisional_unit(client):
    client.post("/collection/", {"name": "Kasli", "rarity": "Uber Super Rare"})
    assert Unit.objects.filter(name="Kasli", canonical=False).exists()


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
def test_wishlist_all_skips_owned_cats(client):
    owned = unit("Bahamut", owned=True)
    client.post("/collection/wishlist-all/")
    owned.refresh_from_db()
    assert owned.wanted is False


@pytest.mark.django_db
def test_wishlist_all_wants_the_unowned(client):
    missing = unit("Kasli")
    client.post("/collection/wishlist-all/")
    missing.refresh_from_db()
    assert missing.wanted is True


@pytest.mark.django_db
def test_wishlist_all_skips_non_gacha_cats(client):
    basic = unit("Tank Cat", rarity="Normal")
    client.post("/collection/wishlist-all/")
    basic.refresh_from_db()
    assert basic.wanted is False
