import pytest

from planner.models import Unit


@pytest.mark.django_db
def test_named_excludes_id_only_names():
    Unit.objects.create(unit_id=25, name="Bahamut")
    Unit.objects.create(unit_id=860, name="861_1")
    Unit.objects.create(unit_id=825, name="826-1")
    assert list(Unit.objects.named().values_list("name", flat=True)) == ["Bahamut"]


@pytest.mark.django_db
def test_unnamed_selects_only_id_only_names():
    Unit.objects.create(unit_id=25, name="Bahamut")
    Unit.objects.create(unit_id=860, name="861_1")
    assert list(Unit.objects.unnamed().values_list("name", flat=True)) == ["861_1"]


@pytest.mark.django_db
def test_real_names_with_digits_are_kept():
    for name in ["EVA Unit-01", "SV-001", "Mer-Cat", "Ancient Egg: N001", "Happy 100"]:
        Unit.objects.create(unit_id=hash(name) % 100000, name=name)
    assert Unit.objects.named().count() == Unit.objects.count()
