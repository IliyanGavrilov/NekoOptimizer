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
