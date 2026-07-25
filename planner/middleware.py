from neko.region import using
from planner.models import Region


def region_scope(get_response):
    """Scope every request to the persisted game version: the data files it reads and
    the catalogue rows it queries both follow ``neko.region``'s active code."""

    def middleware(request):
        code = Region.current()
        request.region = code
        with using(code):
            return get_response(request)

    return middleware
