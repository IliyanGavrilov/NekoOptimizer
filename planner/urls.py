from django.urls import path

from planner.views import planner

urlpatterns = [path("", planner, name="planner")]
