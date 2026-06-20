import pytest

from planner.models import Cat


@pytest.mark.django_db
def test_collection_lists_cats(client):
    Cat.objects.create(name="Bahamut")
    assert b"Bahamut" in client.get("/collection/").content


@pytest.mark.django_db
def test_add_cat_creates_it(client):
    client.post("/collection/", {"name": "Kasli", "rarity": "Uber Super Rare"})
    assert Cat.objects.filter(name="Kasli").exists()


@pytest.mark.django_db
def test_save_sets_owned_and_wanted(client):
    cat = Cat.objects.create(name="Bahamut")
    client.post("/collection/", {"save": "1", "owned": [cat.pk], "wanted": [cat.pk]})
    cat.refresh_from_db()
    assert (cat.owned, cat.wanted) == (True, True)


@pytest.mark.django_db
def test_save_clears_unchecked_flags(client):
    cat = Cat.objects.create(name="Bahamut", owned=True, wanted=True)
    client.post("/collection/", {"save": "1"})
    cat.refresh_from_db()
    assert (cat.owned, cat.wanted) == (False, False)
