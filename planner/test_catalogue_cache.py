import pytest

from neko import region
from planner import catalogue_cache
from planner.catalogue_cache import bump_catalogue
from planner.middleware import PROFILE_COOKIE
from planner.models import CatalogueVersion, Profile, Unit
from planner.services import guide_units, import_units, unit_form_names


def _unit(unit_id, name, forms=()):
    return Unit.objects.create(unit_id=unit_id, name=name, forms=list(forms))


@pytest.fixture
def clock(monkeypatch):
    """The cache's monotonic clock, moved by hand."""
    now = [1000.0]
    monkeypatch.setattr(catalogue_cache.time, "monotonic", lambda: now[0])

    return now


@pytest.mark.django_db
def test_a_cached_read_touches_no_database_until_the_version_is_due(
    clock, django_assert_num_queries
):
    _unit(1, "Bahamut", ["Bahamut Cat"])
    unit_form_names()

    with django_assert_num_queries(0):
        assert unit_form_names() == {1: ["Bahamut Cat"]}


@pytest.mark.django_db
def test_an_import_in_this_process_shows_at_once(clock):
    unit_form_names()

    import_units([{"id": 7, "name": "Kasli", "forms": ["Kasli the Scourge"]}])

    assert unit_form_names() == {7: ["Kasli the Scourge"]}


@pytest.mark.django_db
def test_another_process_bumping_the_version_shows_once_the_ttl_passes(clock):
    _unit(1, "Bahamut", ["Bahamut Cat"])
    unit_form_names()
    Unit.objects.filter(unit_id=1).update(forms=["Crazed Bahamut"])
    CatalogueVersion.objects.create(region=region.current(), number=5)

    assert unit_form_names() == {1: ["Bahamut Cat"]}
    clock[0] += catalogue_cache.VERSION_TTL

    assert unit_form_names() == {1: ["Crazed Bahamut"]}


@pytest.mark.django_db
def test_each_region_keeps_its_own_catalogue(clock):
    _unit(1, "Bahamut", ["Bahamut Cat"])
    unit_form_names()

    with region.using("jp"):
        assert unit_form_names() == {}


@pytest.mark.django_db
def test_bumping_counts_up_from_a_region_with_no_version_yet():
    bump_catalogue()
    bump_catalogue()

    assert CatalogueVersion.objects.get(region=region.current()).number == 2


@pytest.mark.django_db
def test_a_visitors_marks_stay_off_the_rows_every_request_shares(client):
    """Concurrent requests share the cached rows: marking them would show one player's
    collection on another's page."""
    owned = _unit(1, "Bahamut")
    collector = Profile.objects.create()
    collector.owned.add(owned)
    client.cookies[PROFILE_COOKIE] = collector.key

    assert b"own-chip owned" in client.get("/collection/").content
    assert not hasattr(guide_units()[0], "owned")
