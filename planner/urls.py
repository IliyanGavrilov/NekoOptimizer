from django.urls import path

from planner.views import (
    apply_plan,
    collection,
    collection_bulk,
    collection_toggle,
    find_plan,
    picker_past,
    planner,
    tracks,
    unit_info,
)

urlpatterns = [
    path("", planner, name="planner"),
    path("picker/past/", picker_past, name="picker_past"),
    path("tracks/", tracks, name="tracks"),
    path("plan/", find_plan, name="find_plan"),
    path("apply/", apply_plan, name="apply_plan"),
    path("unit/info/", unit_info, name="unit_info"),
    path("collection/", collection, name="collection"),
    path("collection/toggle/", collection_toggle, name="collection_toggle"),
    path("collection/bulk/", collection_bulk, name="collection_bulk"),
]
