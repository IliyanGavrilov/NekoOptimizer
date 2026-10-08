from django.conf import settings

from neko.region import using
from planner.models import Profile

PROFILE_COOKIE = "neko_profile"
_COOKIE_AGE = 2 * 365 * 24 * 60 * 60


def current_profile(request) -> Profile:
    """The visitor's profile: their account's once they log in, else the anonymous one
    their cookie names. A first-time visitor gets an unsaved one - it costs a row only
    once they change something (see owner)."""
    if request.user.is_authenticated:
        try:
            return request.user.profile
        except Profile.DoesNotExist:
            return Profile(user=request.user)

    key = request.COOKIES.get(PROFILE_COOKIE)
    found = Profile.objects.filter(key=key, user=None).first() if key else None

    return found or Profile()


def owner(request) -> Profile:
    """The visitor's profile, saved - what every view that changes their state writes to."""
    if request.profile.pk is None:
        request.profile.save()

    return request.profile


def adopt_guest(request, user) -> None:
    """Hand the visitor's guest profile to an account that has none yet, so signing up
    keeps everything they built before it."""
    key = request.COOKIES.get(PROFILE_COOKIE)
    if key and not Profile.objects.filter(user=user).exists():
        Profile.objects.filter(key=key, user=None).update(user=user)


def profile_scope(get_response):
    """Attach the visitor's profile and scope the request to its game version: the data
    files it reads and the catalogue rows it queries both follow ``neko.region``. A guest
    profile saved during the request has its key handed back as a long-lived cookie."""

    def middleware(request):
        request.profile = profile = current_profile(request)
        request.region = profile.region
        with using(profile.region):
            response = get_response(request)
        if (
            profile.pk
            and not profile.user_id
            and request.COOKIES.get(PROFILE_COOKIE) != profile.key
        ):
            response.set_cookie(
                PROFILE_COOKIE,
                profile.key,
                max_age=_COOKIE_AGE,
                secure=settings.SESSION_COOKIE_SECURE,
                httponly=True,
                samesite="Lax",
            )

        return response

    return middleware
