from django.urls import path

from planner.views import collection, collection_toggle, planner

urlpatterns = [
    path("", planner, name="planner"),
    path("collection/", collection, name="collection"),
    path("collection/toggle/", collection_toggle, name="collection_toggle"),
]
