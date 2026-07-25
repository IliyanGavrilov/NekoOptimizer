from django.conf import settings

from neko.region import DEFAULT_REGION, REGIONS
from planner.links import PAGE_LINKS


def region(request) -> dict:
    """The active game version and the switcher's options, for the shared header."""
    return {"region": getattr(request, "region", DEFAULT_REGION), "regions": REGIONS}


def icons(request) -> dict:
    """Where cat icons are served from, for the templates and app.js alike."""
    return {"icon_base": settings.ICON_BASE}


def tools(request) -> dict:
    """The community tools worth linking from whichever page is being rendered."""
    match = getattr(request, "resolver_match", None)

    return {"page_links": PAGE_LINKS.get(match.url_name, ()) if match else ()}
