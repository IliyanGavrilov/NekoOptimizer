from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.utils import timezone

from planner.models import CannonPlan, Profile, Seed, TalentPlan, Unit, UnitPlan

pytestmark = pytest.mark.django_db


def _guest(age=timedelta(days=2)):
    profile = Profile.objects.create()
    Profile.objects.filter(pk=profile.pk).update(created=timezone.now() - age)
    return profile


def _cat():
    return Unit.objects.create(unit_id=1, name="Cat")


HOLDINGS = {
    "an account": lambda p: Profile.objects.filter(pk=p.pk).update(
        user=User.objects.create(username="neko")
    ),
    "an owned cat": lambda p: p.owned.add(_cat()),
    "a wanted cat": lambda p: p.wanted.add(_cat()),
    "an evolve plan": lambda p: UnitPlan.objects.create(profile=p, unit=_cat()),
    "a talent plan": lambda p: TalentPlan.objects.create(profile=p, unit=_cat(), slot=0),
    "a cannon plan": lambda p: CannonPlan.objects.create(profile=p, cannon_id=1),
    "a seed": lambda p: Seed.store(p, 1),
    "an avatar": lambda p: Profile.objects.filter(pk=p.pk).update(avatar_unit=1),
    "auto-wishlist on": lambda p: Profile.objects.filter(pk=p.pk).update(auto_wishlist=True),
}


def test_an_old_guest_profile_holding_nothing_is_deleted():
    _guest()
    call_command("prune_guests")
    assert not Profile.objects.exists()


@pytest.mark.parametrize("holding", HOLDINGS)
def test_a_profile_holding_something_is_kept(holding):
    HOLDINGS[holding](_guest())
    call_command("prune_guests")
    assert Profile.objects.count() == 1


def test_a_fresh_empty_guest_is_kept_while_its_first_change_may_still_be_saving():
    _guest(age=timedelta(minutes=5))
    call_command("prune_guests")
    assert Profile.objects.count() == 1
