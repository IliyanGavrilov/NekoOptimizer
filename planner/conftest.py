import pytest

from planner.middleware import PROFILE_COOKIE
from planner.models import Profile


@pytest.fixture
def profile(db, client):
    """A returning visitor: a saved guest profile that the test client's cookie names."""
    profile = Profile.objects.create()
    client.cookies[PROFILE_COOKIE] = profile.key

    return profile
