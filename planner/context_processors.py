from django.conf import settings

from neko.region import DEFAULT_REGION, REGIONS
from planner.links import PAGE_LINKS
from planner.seo import home_graph, ld_json, page_meta


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
    """The page's search listing, the URL it is filed under, and the home page's
    structured data; a view with a listing of its own passes page_meta itself."""
    match = getattr(request, "resolver_match", None)
    url_name = match.url_name if match else None

    return {
        "page_meta": page_meta(url_name),
        "site_url": settings.SITE_URL,
        "canonical_url": f"{settings.SITE_URL}{request.path}",
        "structured_data": ld_json(home_graph()) if url_name == "planner" else "",
        "google_verification": settings.GOOGLE_SITE_VERIFICATION,
        "bing_verification": settings.BING_SITE_VERIFICATION,
    }
