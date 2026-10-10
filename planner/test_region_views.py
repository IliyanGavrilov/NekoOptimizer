import pytest

from planner.models import Profile, Unit

pytestmark = pytest.mark.django_db


def switch(profile, code):
    profile.region = code
    profile.save()


def test_switching_region_persists_the_choice(client):
    client.post("/region/", {"region": "jp"})
    assert Profile.objects.get().region == "jp"


def test_switching_to_an_unknown_region_is_rejected(client):
    response = client.post("/region/", {"region": "de"})
    assert response.status_code == 400 and not Profile.objects.exists()


def test_switching_region_ignores_an_offsite_referer(client):
    response = client.post("/region/", {"region": "jp"}, HTTP_REFERER="https://evil.test/steal")
    assert response["Location"] == "/"


def test_requests_see_only_the_active_regions_units(client, profile):
    Unit.objects.create(unit_id=1, name="Cat", rarity="Normal")
    Unit.all_regions.create(region="jp", unit_id=1, name="ネコ", rarity="Normal")
    switch(profile, "jp")
    assert client.get("/unit/info/?name=Cat").json() == {"found": False}


def test_requests_find_the_active_regions_own_names(client, profile):
    Unit.all_regions.create(region="jp", unit_id=1, name="ネコ", rarity="Normal")
    switch(profile, "jp")
    assert client.get("/unit/info/?name=ネコ").json()["unit_id"] == 1


def test_each_visitor_sees_their_own_region(client, profile):
    Unit.all_regions.create(region="jp", unit_id=1, name="ネコ", rarity="Normal")
    Profile.objects.create(region="jp")
    assert client.get("/unit/info/?name=ネコ").json() == {"found": False}


# The pages below only render if every committed document resolves for the chosen
# version - the catalogue, stats, combos, talents, guide order and materials data.
def test_the_collection_page_renders_for_another_region(client, profile):
    switch(profile, "tw")
    assert client.get("/collection/").status_code == 200


def test_the_resources_page_renders_for_another_region(client, profile):
    switch(profile, "kr")
    assert client.get("/resources/").status_code == 200


def test_switching_region_comes_back_to_the_page_it_was_posted_from(client):
    response = client.post("/region/", {"region": "jp"}, HTTP_REFERER="http://testserver/tiers/")
    assert response["Location"] == "/tiers/"


def test_switching_region_keeps_the_pages_query_string(client):
    # The planner's permalink lives in the query (?seed=&rolls=), so a version switch that
    # dropped it would quietly throw away the view you were looking at.
    response = client.post(
        "/region/", {"region": "jp"}, HTTP_REFERER="http://testserver/?seed=7&rolls=50"
    )
    assert response["Location"] == "/?seed=7&rolls=50"


def test_switching_region_ignores_a_referer_that_is_not_one_of_our_routes(client):
    response = client.post("/region/", {"region": "jp"}, HTTP_REFERER="http://testserver/nope/")
    assert response["Location"] == "/"
