from django.urls import path

from planner.views import apply_plan, collection, collection_toggle, planner

urlpatterns = [
    path("", planner, name="planner"),
    path("apply/", apply_plan, name="apply_plan"),
    path("collection/", collection, name="collection"),
    path("collection/toggle/", collection_toggle, name="collection_toggle"),
]
