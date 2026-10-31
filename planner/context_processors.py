from django.conf import settings
from django.utils.translation import gettext_lazy as _

from neko.region import CODES, DEFAULT_REGION, REGIONS
from planner.links import PAGE_LINKS
from planner.middleware import region_path, split_region
from planner.seo import HREFLANG, REGION_PAGES, home_graph, ld_json, page_meta

# The switcher's version names, in the interface language.
REGION_NAMES = {"en": _("English"), "jp": _("Japan"), "tw": _("Taiwan"), "kr": _("Korea")}


def region(request) -> dict:
    """The active game version and the switcher's options, plus the interface language the
    visitor picked ("" when the page follows its version), for the shared header."""
    picked = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME, "")

    return {
        "region": getattr(request, "region", DEFAULT_REGION),
        "regions": [(option.code, REGION_NAMES[option.code]) for option in REGIONS],
        "language_pick": picked if picked in dict(settings.LANGUAGES) else "",
    }


def icons(request) -> dict:
    """Where cat and material icons are served from, for the templates and app.js alike."""
    return {"icon_base": settings.ICON_BASE, "item_base": settings.ITEM_BASE}


def tools(request) -> dict:
    """The community tools worth linking from whichever page is being rendered."""
    match = getattr(request, "resolver_match", None)

    return {"page_links": PAGE_LINKS.get(match.url_name, ()) if match else ()}


def seo(request) -> dict:
    """The page's search listing, the URL it is filed under, its other versions' URLs, and
    the home page's structured data; a view with a listing of its own passes page_meta
    itself. A version's own page is filed under its own URL and names its siblings
    (hreflang); a page that reads the same everywhere is filed under the English one."""
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else None
    url_region, path = split_region(request.path)
    regional = url_name in REGION_PAGES
    alternates = []
    if regional:
        alternates = [(HREFLANG[code], region_path(path, code)) for code in CODES]
        alternates.append(("x-default", path))

    return {
        "page_meta": page_meta(url_name),
        "site_url": settings.SITE_URL,
        "canonical_url": f"{settings.SITE_URL}{request.path if regional else path}",
        "alternates": alternates,
        "structured_data": ld_json(home_graph())
        if url_name == "planner" and not url_region
        else "",
        "google_verification": settings.GOOGLE_SITE_VERIFICATION,
        "bing_verification": settings.BING_SITE_VERIFICATION,
        "vercel_analytics": settings.VERCEL_ANALYTICS,
    }
