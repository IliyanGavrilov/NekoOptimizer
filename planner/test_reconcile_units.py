import pytest
from django.core.management import call_command

from planner.models import Cat, Profile, Unit
from planner.services import PROVISIONAL_BASE, reconcile_provisional_units


def provisional(name):
    last = Unit.objects.filter(unit_id__gte=PROVISIONAL_BASE).order_by("-unit_id").first()
    next_id = (last.unit_id + 1) if last else PROVISIONAL_BASE
    return Unit.objects.create(unit_id=next_id, name=name, canonical=False)


@pytest.mark.django_db
def test_merge_deletes_provisional_and_keeps_canonical():
    Unit.objects.create(unit_id=841, name="Nezuko Kamado")
    provisional("Nezuko Kamado")
    merged, orphaned = reconcile_provisional_units()
    assert (merged, orphaned) == (1, [])
    assert Unit.objects.filter(name="Nezuko Kamado").count() == 1
    assert Unit.objects.get(name="Nezuko Kamado").canonical is True


@pytest.mark.django_db
def test_merge_repoints_cats_to_canonical_unit():
    canonical = Unit.objects.create(unit_id=841, name="Nezuko Kamado")
    prov = provisional("Nezuko Kamado")
    cat = Cat.objects.create(name="Nezuko Kamado", unit=prov)
    reconcile_provisional_units()
    cat.refresh_from_db()
    assert cat.unit_id == canonical.pk


@pytest.mark.django_db
def test_merge_carries_every_players_marks_onto_canonical():
    Unit.objects.create(unit_id=841, name="Nezuko Kamado")
    prov = provisional("Nezuko Kamado")
    profile = Profile.objects.create()
    profile.owned.add(prov)
    profile.wanted.add(prov)
    reconcile_provisional_units()
    assert (profile.owned.get().unit_id, profile.wanted.get().unit_id) == (841, 841)


@pytest.mark.django_db
def test_merge_does_not_clear_canonical_marks_when_provisional_is_bare():
    profile = Profile.objects.create()
    profile.owned.add(Unit.objects.create(unit_id=841, name="Nezuko Kamado"))
    provisional("Nezuko Kamado")
    reconcile_provisional_units()
    assert profile.owned.filter(unit_id=841).exists()


@pytest.mark.django_db
def test_orphan_provisional_is_left_in_place():
    prov = provisional("Uncatalogued Cat")
    merged, orphaned = reconcile_provisional_units()
    assert (merged, orphaned) == (0, ["Uncatalogued Cat"])
    assert Unit.objects.filter(pk=prov.pk).exists()


@pytest.mark.django_db
def test_command_runs():
    Unit.objects.create(unit_id=841, name="Nezuko Kamado")
    provisional("Nezuko Kamado")
    call_command("reconcile_units")
    assert Unit.objects.filter(canonical=False).count() == 0
