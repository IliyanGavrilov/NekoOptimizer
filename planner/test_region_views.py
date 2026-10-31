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
    assert response["Location"] == "/jp/"


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
    assert client.get("/tw/collection/").status_code == 200


def test_the_resources_page_renders_for_another_region(client, profile):
    assert client.get("/kr/resources/").status_code == 200


def test_switching_region_comes_back_to_the_page_it_was_posted_from(client):
    response = client.post("/region/", {"region": "jp"}, HTTP_REFERER="http://testserver/tiers/")
    assert response["Location"] == "/jp/tiers/"


def test_switching_back_to_english_drops_the_version_prefix(client, profile):
    response = client.post(
        "/jp/region/", {"region": "en"}, HTTP_REFERER="http://testserver/jp/tiers/"
    )
    assert response["Location"] == "/tiers/"


def test_switching_region_keeps_the_pages_query_string(client):
    # The planner's permalink lives in the query (?seed=&rolls=), so a version switch that
    # dropped it would quietly throw away the view you were looking at.
    response = client.post(
        "/region/", {"region": "jp"}, HTTP_REFERER="http://testserver/?seed=7&rolls=50"
    )
    assert response["Location"] == "/jp/?seed=7&rolls=50"


def test_switching_region_ignores_a_referer_that_is_not_one_of_our_routes(client):
    response = client.post("/region/", {"region": "jp"}, HTTP_REFERER="http://testserver/nope/")
    assert response["Location"] == "/jp/"


def test_a_version_prefix_picks_that_versions_data(client, profile):
    Unit.all_regions.create(region="jp", unit_id=1, name="ネコ", rarity="Normal")
    assert client.get("/jp/unit/info/?name=ネコ").json()["unit_id"] == 1


def test_opening_a_versions_page_makes_it_the_profiles(client, profile):
    client.get("/jp/collection/")
    profile.refresh_from_db()
    assert profile.region == "jp"


def test_a_bare_page_sends_you_to_your_own_version(client, profile):
    switch(profile, "jp")
    response = client.get("/?seed=7")
    assert (response.status_code, response["Location"]) == (302, "/jp/?seed=7")


def test_a_first_time_visitor_gets_the_english_page_where_they_asked(client):
    assert client.get("/collection/").status_code == 200


def test_links_on_a_versions_page_stay_in_that_version(client, profile):
    content = client.get("/jp/collection/").content.decode()
    assert 'action="/jp/region/"' in content
    assert 'href="/static/planner/style.css"' in content


def test_a_versions_page_speaks_its_language(client, profile):
    content = client.get("/jp/collection/").content.decode()
    assert '<html lang="ja">' in content
    assert "コレクション" in content


def test_a_picked_language_wins_over_the_versions(client, profile):
    client.cookies["neko_lang"] = "en"
    assert '<html lang="en">' in client.get("/jp/collection/").content.decode()


def test_picking_a_language_remembers_it_and_comes_back(client, profile):
    response = client.post(
        "/jp/language/", {"language": "ko"}, HTTP_REFERER="http://testserver/jp/tiers/"
    )
    assert (response["Location"], response.cookies["neko_lang"].value) == ("/jp/tiers/", "ko")


def test_picking_the_games_language_forgets_the_pick(client, profile):
    client.cookies["neko_lang"] = "ko"
    response = client.post("/jp/language/", {"language": ""})
    assert response.cookies["neko_lang"].value == ""


def test_picking_an_unknown_language_is_rejected(client, profile):
    assert client.post("/language/", {"language": "de"}).status_code == 400
