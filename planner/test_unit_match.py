import pytest

from planner.models import Cat, Unit
from planner.services import unit_match_report


@pytest.mark.django_db
def test_report_matches_a_cat_to_its_unit():
    Unit.objects.create(unit_id=25, name="Bahamut Cat")
    Cat.objects.create(name="Bahamut Cat")
    matches, _ = unit_match_report()
    assert matches == {"Bahamut Cat": 25}


@pytest.mark.django_db
def test_report_flags_a_cat_with_no_unit():
    Cat.objects.create(name="Jeanne")
    _, unmatched = unit_match_report()
    assert unmatched == ["Jeanne"]
