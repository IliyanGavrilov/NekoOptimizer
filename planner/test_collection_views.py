from itertools import count

import pytest

from planner.models import Banner, Cat, Unit

_ids = count(1)


def cat_with_unit(name, owned=False, wanted=False):
    unit = Unit.objects.create(unit_id=next(_ids), name=name, owned=owned, wanted=wanted)
    return Cat.objects.create(name=name, unit=unit)


@pytest.mark.django_db
def test_collection_lists_cats(client):
    Cat.objects.create(name="Bahamut")
    assert b"Bahamut" in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_groups_by_banner(client):
    cat = Cat.objects.create(name="Bahamut")
    cat.banners.add(Banner.objects.create(name="Epicfest"))
    assert b"Epicfest" in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_shows_rarity(client):
    Cat.objects.create(name="Bahamut", rarity="Uber Super Rare")
    assert b"Uber Super Rare" in client.get("/collection/").content


@pytest.mark.django_db
def test_add_cat_creates_it(client):
    client.post("/collection/", {"name": "Kasli", "rarity": "Uber Super Rare"})
    assert Cat.objects.filter(name="Kasli").exists()


@pytest.mark.django_db
def test_toggle_owned_flips_flag(client):
    cat = Cat.objects.create(name="Bahamut")
    client.post("/collection/toggle/", {"pk": cat.pk, "field": "owned"})
    cat.refresh_from_db()
    assert cat.owned is True


@pytest.mark.django_db
def test_toggle_wanted_twice_returns_to_false(client):
    cat = Cat.objects.create(name="Bahamut")
    client.post("/collection/toggle/", {"pk": cat.pk, "field": "wanted"})
    client.post("/collection/toggle/", {"pk": cat.pk, "field": "wanted"})
    cat.refresh_from_db()
    assert cat.wanted is False


@pytest.mark.django_db
def test_toggle_rejects_unknown_field(client):
    cat = Cat.objects.create(name="Bahamut")
    assert client.post("/collection/toggle/", {"pk": cat.pk, "field": "rarity"}).status_code == 400


@pytest.mark.django_db
def test_wishlist_all_skips_owned_cats(client):
    owned = cat_with_unit("Bahamut", owned=True)
    client.post("/collection/wishlist-all/")
    owned.refresh_from_db()
    assert owned.wanted is False


@pytest.mark.django_db
def test_wishlist_all_wants_the_unowned(client):
    missing = cat_with_unit("Kasli")
    client.post("/collection/wishlist-all/")
    missing.refresh_from_db()
    assert missing.wanted is True
