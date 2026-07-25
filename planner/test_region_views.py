import pytest

from planner.models import Region, Unit

pytestmark = pytest.mark.django_db


def test_switching_region_persists_the_choice(client):
    client.post("/region/", {"region": "jp"})
    assert Region.current() == "jp"


def test_switching_to_an_unknown_region_is_rejected(client):
    response = client.post("/region/", {"region": "de"})
    assert response.status_code == 400 and Region.current() == "en"


def test_switching_region_ignores_an_offsite_referer(client):
    response = client.post("/region/", {"region": "jp"}, HTTP_REFERER="https://evil.test/steal")
    assert response["Location"] == "/"


def test_requests_see_only_the_active_regions_units(client):
    Unit.objects.create(unit_id=1, name="Cat", rarity="Normal")
    Unit.all_regions.create(region="jp", unit_id=1, name="ネコ", rarity="Normal")
    Region.store("jp")
    assert client.get("/unit/info/?name=Cat").json() == {"found": False}


def test_requests_find_the_active_regions_own_names(client):
    Unit.all_regions.create(region="jp", unit_id=1, name="ネコ", rarity="Normal")
    Region.store("jp")
    assert client.get("/unit/info/?name=ネコ").json()["unit_id"] == 1


# The pages below only render if every committed document resolves for the chosen
# version - the catalogue, stats, combos, talents, guide order and materials data.
def test_the_collection_page_renders_for_another_region(client):
    Region.store("tw")
    assert client.get("/collection/").status_code == 200


def test_the_resources_page_renders_for_another_region(client):
    Region.store("kr")
    assert client.get("/resources/").status_code == 200
