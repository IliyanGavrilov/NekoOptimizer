from django.urls import path

from planner.views import (
    apply_plan,
    collection,
    collection_bulk,
    collection_toggle,
    find_plan,
    picker_past,
    planner,
    seed_backtrack,
    tracks,
    unit_forms,
    unit_info,
)

urlpatterns = [
    path("", planner, name="planner"),
    path("picker/past/", picker_past, name="picker_past"),
    path("tracks/", tracks, name="tracks"),
    path("seed/backtrack/", seed_backtrack, name="seed_backtrack"),
    path("plan/", find_plan, name="find_plan"),
    path("apply/", apply_plan, name="apply_plan"),
    path("unit/info/", unit_info, name="unit_info"),
    path("unit/forms/", unit_forms, name="unit_forms"),
    path("collection/", collection, name="collection"),
    path("collection/toggle/", collection_toggle, name="collection_toggle"),
    path("collection/bulk/", collection_bulk, name="collection_bulk"),
]
