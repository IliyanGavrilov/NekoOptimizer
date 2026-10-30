from django.conf import settings

from neko.region import CODES, DEFAULT_REGION, REGIONS, spec
from planner.links import PAGE_LINKS
from planner.middleware import region_path, split_region
from planner.seo import HREFLANG, REGION_PAGES, home_graph, ld_json, page_meta


def region(request) -> dict:
    """The active game version and the switcher's options, for the shared header."""
    return {"region": getattr(request, "region", DEFAULT_REGION), "regions": REGIONS}


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
        "region_label": spec(url_region).label if regional and url_region else "",
        "site_url": settings.SITE_URL,
        "canonical_url": f"{settings.SITE_URL}{request.path if regional else path}",
        "alternates": alternates,
        "structured_data": ld_json(home_graph())
        if url_name == "planner" and not url_region
        else "",
        "google_verification": settings.GOOGLE_SITE_VERIFICATION,
        "bing_verification": settings.BING_SITE_VERIFICATION,
    }
