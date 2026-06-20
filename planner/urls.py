from django.urls import path

from planner.views import collection, planner

urlpatterns = [
    path("", planner, name="planner"),
    path("collection/", collection, name="collection"),
]
