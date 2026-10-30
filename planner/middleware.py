from django.conf import settings
from django.shortcuts import redirect
from django.urls import Resolver404, get_script_prefix, resolve, set_script_prefix

from neko.region import CODES, DEFAULT_REGION, using
from planner.models import Profile
from planner.seo import REGION_PAGES

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


def split_region(path: str) -> tuple[str | None, str]:
    """The game version a path's prefix names, and the path without it: "/jp/tiers/" is
    ("jp", "/tiers/"). The default version has no prefix, so its paths give None."""
    head, _, rest = path.lstrip("/").partition("/")
    if head in CODES and head != DEFAULT_REGION:
        return head, f"/{rest}"

    return None, path


def region_path(path: str, code: str) -> str:
    """``path``, prefixed or not, as the URL of ``code``'s version of that page."""
    rest = split_region(path)[1]

    return rest if code == DEFAULT_REGION else f"/{code}{rest}"


def _is_page(request, path: str) -> bool:
    """Whether a request opens one of the pages each version has its own copy of."""
    if request.method != "GET":
        return False
    try:
        return resolve(path).url_name in REGION_PAGES
    except Resolver404:
        return False


def profile_scope(get_response):
    """Attach the visitor's profile and scope the request to its game version: the data
    files it reads and the catalogue rows it queries both follow ``neko.region``. A guest
    profile saved during the request has its key handed back as a long-lived cookie.

    The version is in the URL - /jp/, /tw/, /kr/, none for English - so every version's
    pages have addresses of their own to share and to be found by. The prefix is cut off
    before routing and set as the script prefix, so every reverse() and {% url %} stays
    inside the version. Opening a version's page makes it the profile's; an unprefixed
    page for someone whose profile is on another version sends them there, so the bare
    address always comes back to your own version."""

    def middleware(request):
        url_region, request.path_info = split_region(request.path_info)
        request.profile = profile = current_profile(request)
        if _is_page(request, request.path_info) and profile.region != (
            url_region or DEFAULT_REGION
        ):
            if url_region is None:
                return redirect(region_path(request.get_full_path(), profile.region))
            profile.region = url_region
            if profile.pk:
                profile.save(update_fields=["region"])

        request.region = url_region or profile.region
        base = get_script_prefix()
        if url_region:
            set_script_prefix(f"{base}{url_region}/")
        try:
            with using(request.region):
                response = get_response(request)
        finally:
            set_script_prefix(base)
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
