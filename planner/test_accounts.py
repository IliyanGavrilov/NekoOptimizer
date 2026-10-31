import pytest
from django.contrib.auth.models import User

from planner.models import Profile, Unit

pytestmark = pytest.mark.django_db

PASSWORD = "correct-horse-battery-9"  # nosec B105


@pytest.fixture(autouse=True)
def fast_hashing(settings):
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


def sign_up(client):
    return client.post(
        "/accounts/signup/", {"username": "neko", "password1": PASSWORD, "password2": PASSWORD}
    )


def exported_owned(client):
    return [entry["name"] for entry in client.get("/collection/export/").json()["owned"]]


def test_signing_up_keeps_the_guests_collection(client, profile):
    profile.owned.add(Unit.objects.create(unit_id=1, name="Bahamut"))
    sign_up(client)
    assert Profile.objects.get(user__username="neko") == profile


def test_an_account_sees_its_collection_from_a_new_device(client, profile):
    profile.owned.add(Unit.objects.create(unit_id=1, name="Bahamut"))
    sign_up(client)
    client.cookies.clear()
    client.login(username="neko", password=PASSWORD)
    assert exported_owned(client) == ["Bahamut"]


def test_logging_out_hides_the_accounts_collection(client, profile):
    profile.owned.add(Unit.objects.create(unit_id=1, name="Bahamut"))
    sign_up(client)
    client.post("/accounts/logout/")
    assert exported_owned(client) == []


def test_logging_in_keeps_the_accounts_own_profile(client, profile):
    user = User.objects.create_user("neko", password=PASSWORD)
    Profile.objects.create(user=user)
    client.post("/accounts/login/", {"username": "neko", "password": PASSWORD})
    profile.refresh_from_db()
    assert profile.user is None


def test_logging_in_adopts_the_guest_when_the_account_has_none(client, profile):
    User.objects.create_user("neko", password=PASSWORD)
    client.post("/accounts/login/", {"username": "neko", "password": PASSWORD})
    profile.refresh_from_db()
    assert profile.user.username == "neko"


def test_an_accounts_first_change_is_saved_to_the_account(client):
    User.objects.create_user("neko", password=PASSWORD)
    client.login(username="neko", password=PASSWORD)
    client.post("/region/", {"region": "jp"})
    assert Profile.objects.get().user.username == "neko"


@pytest.fixture
def logged_in(client):
    User.objects.create_user("neko", password=PASSWORD)
    client.login(username="neko", password=PASSWORD)
    return client


def test_an_avatar_pick_shows_that_form_in_the_header(logged_in, settings):
    Unit.objects.create(unit_id=2, name="Axe Cat", forms=["Axe Cat", "Brave Cat", "Sexy Legs"])
    logged_in.post("/accounts/avatar/", {"avatar": "2/2"})
    page = logged_in.get("/").content.decode()
    assert f"{settings.ICON_BASE}/2/2.png" in page


def test_an_avatar_pick_must_name_a_form_the_cat_has(logged_in):
    Unit.objects.create(unit_id=2, name="Axe Cat", forms=["Axe Cat", "Brave Cat"])
    assert logged_in.post("/accounts/avatar/", {"avatar": "2/2"}).status_code == 400
    assert logged_in.post("/accounts/avatar/", {"avatar": "999/0"}).status_code == 400
    assert Profile.objects.get().avatar_unit is None


def test_a_guest_is_sent_to_log_in_before_picking_an_avatar(client):
    response = client.get("/accounts/avatar/")
    assert response.status_code == 302
    assert response["Location"].startswith("/accounts/login/")


def test_the_avatar_picker_lists_every_cat_a_to_z_with_its_marks(logged_in):
    logged_in.get("/accounts/avatar/")
    profile = Profile.objects.get()
    profile.owned.add(Unit.objects.create(unit_id=3, name="Tank Cat", rarity="Normal"))
    profile.wanted.add(Unit.objects.create(unit_id=2, name="Axe Cat", rarity="Normal"))
    Unit.objects.create(unit_id=1, name="Bahamut")

    cats = logged_in.get("/accounts/avatar/").context["cats"]

    assert [(c["name"], c["rarity"], c["owned"], c["wanted"]) for c in cats] == [
        ("Axe Cat", "Normal", False, True),
        ("Bahamut", "Unknown", False, False),
        ("Tank Cat", "Normal", True, False),
    ]
