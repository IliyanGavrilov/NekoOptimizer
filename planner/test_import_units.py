import pytest
from django.core.management import call_command

from planner.models import Profile, Unit
from planner.services import import_units

RECORD = {"id": 25, "name": "Bahamut Cat", "rarity": "Special", "forms": ["Bahamut Cat"]}


@pytest.mark.django_db
def test_import_counts_new_units():
    assert import_units([RECORD]) == 1


@pytest.mark.django_db
def test_reimport_creates_nothing():
    import_units([RECORD])
    assert import_units([RECORD]) == 0


@pytest.mark.django_db
def test_import_stores_the_canonical_id():
    import_units([RECORD])
    assert Unit.objects.get(name="Bahamut Cat").unit_id == 25


@pytest.mark.django_db
def test_reimport_updates_a_renamed_unit():
    import_units([RECORD])
    import_units([{**RECORD, "name": "Bahamut Cat (Renamed)"}])
    assert Unit.objects.get(unit_id=25).name == "Bahamut Cat (Renamed)"


@pytest.mark.django_db
def test_import_keeps_the_evolution_forms():
    import_units([{**RECORD, "forms": ["Bahamut Cat", "Awakened Bahamut Cat"]}])
    assert Unit.objects.get(unit_id=25).forms == ["Bahamut Cat", "Awakened Bahamut Cat"]


@pytest.mark.django_db
def test_import_stores_the_gacha_set():
    import_units([{**RECORD, "set": "The Dynamites"}])
    assert Unit.objects.get(unit_id=25).set_name == "The Dynamites"


@pytest.mark.django_db
def test_command_loads_records(monkeypatch):
    monkeypatch.setattr("planner.management.commands.import_units.load_records", lambda: [RECORD])
    call_command("import_units")
    assert Unit.objects.filter(unit_id=25).exists()


UBER = {"id": 700, "name": "New Uber", "rarity": "Uber Super Rare"}


@pytest.mark.django_db
def test_new_gacha_unit_lands_on_opted_in_wishlists():
    import_units([RECORD])
    fan, other = Profile.objects.create(auto_wishlist=True), Profile.objects.create()
    import_units([RECORD, UBER, {**RECORD, "id": 26, "name": "New Special"}])
    assert list(fan.wanted.values_list("name", flat=True)) == ["New Uber"]
    assert not other.wanted.exists()


@pytest.mark.django_db
def test_first_import_wishlists_nothing():
    fan = Profile.objects.create(auto_wishlist=True)
    import_units([UBER])
    assert not fan.wanted.exists()
