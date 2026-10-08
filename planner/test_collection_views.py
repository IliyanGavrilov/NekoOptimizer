import json
from itertools import count

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from neko import region
from planner.middleware import PROFILE_COOKIE
from planner.models import Profile, Unit

_ids = count(1)


def unit(name, rarity="Uber Super Rare", **fields):
    return Unit.objects.create(unit_id=next(_ids), name=name, rarity=rarity, **fields)


def marked(profile, mark):
    return set(profile.units(mark).values_list("name", flat=True))


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
def test_collection_marks_the_visitors_own_units(client, profile):
    profile.owned.add(unit("Bahamut"))
    assert b"own-chip owned" in client.get("/collection/").content


@pytest.mark.django_db
def test_collection_ignores_another_visitors_marks(client, profile):
    Profile.objects.create().owned.add(unit("Bahamut"))
    assert b"own-chip owned" not in client.get("/collection/").content


@pytest.mark.django_db
def test_browsing_creates_no_profile(client):
    client.get("/collection/")
    assert not Profile.objects.exists()


@pytest.mark.django_db
def test_a_first_mark_creates_the_visitors_profile(client):
    u = unit("Bahamut")
    response = client.post("/collection/toggle/", {"pk": u.pk, "field": "owned"})
    assert response.cookies[PROFILE_COOKIE].value == Profile.objects.get().key


@pytest.mark.django_db
def test_toggle_owned_flips_flag(client, profile):
    u = unit("Bahamut")
    client.post("/collection/toggle/", {"pk": u.pk, "field": "owned"})
    assert marked(profile, "owned") == {"Bahamut"}


@pytest.mark.django_db
def test_toggle_wanted_twice_returns_to_false(client, profile):
    u = unit("Bahamut")
    client.post("/collection/toggle/", {"pk": u.pk, "field": "wanted"})
    client.post("/collection/toggle/", {"pk": u.pk, "field": "wanted"})
    assert marked(profile, "wanted") == set()


@pytest.mark.django_db
def test_toggle_leaves_another_visitors_collection_alone(client, profile):
    u = unit("Bahamut")
    other = Profile.objects.create()
    other.owned.add(u)
    client.post("/collection/toggle/", {"pk": u.pk, "field": "owned"})
    assert marked(other, "owned") == {"Bahamut"}


@pytest.mark.django_db
def test_toggle_rejects_unknown_field(client):
    u = unit("Bahamut")
    assert client.post("/collection/toggle/", {"pk": u.pk, "field": "rarity"}).status_code == 400


@pytest.mark.django_db
def test_bulk_owns_every_unit(client, profile):
    units = [unit("Bahamut"), unit("Kasli")]
    client.post("/collection/bulk/", {"field": "owned", "pk": [u.pk for u in units]})
    assert marked(profile, "owned") == {"Bahamut", "Kasli"}


@pytest.mark.django_db
def test_bulk_clears_a_fully_owned_section(client, profile):
    units = [unit("Bahamut"), unit("Kasli")]
    profile.owned.add(*units)
    client.post("/collection/bulk/", {"field": "owned", "pk": [u.pk for u in units]})
    assert marked(profile, "owned") == set()


@pytest.mark.django_db
def test_bulk_wishlist_stars_owned_units_too(client, profile):
    owned = unit("Bahamut")
    profile.owned.add(owned)
    missing = unit("Kasli")
    client.post("/collection/bulk/", {"field": "wanted", "pk": [owned.pk, missing.pk]})
    assert marked(profile, "wanted") == {"Bahamut", "Kasli"}


@pytest.mark.django_db
def test_bulk_rejects_unknown_field(client):
    assert client.post("/collection/bulk/", {"field": "rarity"}).status_code == 400


@pytest.mark.django_db
def test_export_lists_owned_and_wanted(client, profile):
    profile.owned.add(unit("Bahamut"))
    profile.wanted.add(unit("Kasli"))
    unit("Mott")  # neither, absent from the snapshot
    data = client.get("/collection/export/").json()
    assert [e["name"] for e in data["owned"]] == ["Bahamut"]
    assert [e["name"] for e in data["wanted"]] == ["Kasli"]


@pytest.mark.django_db
def test_import_round_trips_an_export(client, profile):
    profile.owned.add(unit("Bahamut"))
    profile.wanted.add(unit("Kasli"))
    snapshot = client.get("/collection/export/").json()
    profile.owned.clear()
    profile.wanted.clear()

    resp = _import(client, snapshot)

    assert resp.json() == {"owned": 1, "wanted": 1, "missing": []}
    assert (marked(profile, "owned"), marked(profile, "wanted")) == ({"Bahamut"}, {"Kasli"})


@pytest.mark.django_db
def test_import_replaces_existing_marks(client, profile):
    profile.owned.add(unit("Bahamut"))
    fresh = unit("Kasli")
    _import(client, {"neko_collection": 1, "owned": [{"id": fresh.unit_id, "name": "Kasli"}]})
    assert marked(profile, "owned") == {"Kasli"}


@pytest.mark.django_db
def test_import_leaves_the_other_regions_marks_alone(client, profile):
    profile.owned.add(Unit.all_regions.create(region="jp", unit_id=1, name="ネコ"))
    _import(client, {"neko_collection": 1, "owned": []})
    with region.using("jp"):
        assert marked(profile, "owned") == {"ネコ"}


@pytest.mark.django_db
def test_import_matches_by_name_when_id_misses(client, profile):
    unit("Bahamut")
    _import(client, {"neko_collection": 1, "owned": [{"id": 999999, "name": "Bahamut"}]})
    assert marked(profile, "owned") == {"Bahamut"}


@pytest.mark.django_db
def test_import_reports_unmatched_entries(client):
    resp = _import(client, {"neko_collection": 1, "owned": [{"id": 42, "name": "Ghost"}]})
    assert resp.json()["missing"] == ["Ghost"]


@pytest.mark.django_db
def test_import_rejects_a_non_snapshot(client):
    assert _import(client, {"just": "some json"}).status_code == 400


@pytest.mark.django_db
def test_import_rejects_non_json(client):
    resp = client.post("/collection/import/", {"file": _upload(b"not json at all", "c.json")})
    assert resp.status_code == 400


def _upload(content, name="collection.json"):
    return SimpleUploadedFile(name, content, content_type="application/json")


def _import(client, payload):
    return client.post(
        "/collection/import/",
        {"file": _upload(json.dumps(payload).encode())},
    )


@pytest.mark.django_db
def test_collection_hides_units_the_regions_cat_guide_doesnt_list(client, monkeypatch):
    listed = unit("Bahamut")
    unit("Droid Cat")
    monkeypatch.setattr("planner.models.load_guide", lambda: {"regions": {"en": [listed.unit_id]}})
    page = client.get("/collection/").content

    assert (b"Bahamut" in page, b"Droid Cat" in page) == (True, False)
