# The site's URLs plus the server-rendered Rolls table and plan views, which the page no
# longer calls (neko.wasm rolls, solves and renders them): kept as the reference the engine
# is held to, and routed only for the tests that hit it, so they cost the live server
# nothing.

from django.urls import path

from nekosite.urls import urlpatterns as site
from planner.views import find_plan, normal_plan, normal_tracks, plan_row, tracks

urlpatterns = [
    *site,
    path("tracks/", tracks),
    path("reference/plan/", find_plan),
    path("reference/plan/row/", plan_row),
    path("reference/normal/tracks/", normal_tracks),
    path("reference/normal/plan/", normal_plan),
]
