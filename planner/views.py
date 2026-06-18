from django.shortcuts import render

from neko.planning import plan
from planner.forms import PlannerForm
from planner.models import Seed
from planner.services import fetch_banners


def planner(request):
    plans = None
    if request.method == "POST":
        form = PlannerForm(request.POST)
        if form.is_valid():
            seed = form.cleaned_data["seed"]
            Seed.store(seed)
            pulls = fetch_banners(seed)
            targets = [cat.name for cat in form.cleaned_data["targets"]]
            plans = plan(pulls, targets, form.cleaned_data["tickets"], form.cleaned_data["catfood"])
    else:
        form = PlannerForm(initial={"seed": Seed.current()})
    return render(request, "planner/planner.html", {"form": form, "plans": plans})
