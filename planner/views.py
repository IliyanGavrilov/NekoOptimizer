from django.shortcuts import redirect, render

from neko.planning import plan
from planner.forms import CatForm, PlannerForm
from planner.models import Cat, Seed
from planner.services import fetch_banners


def planner(request):
    plans = None
    if request.method == "POST":
        form = PlannerForm(request.POST)
        if form.is_valid():
            seed = form.cleaned_data["seed"]
            Seed.store(seed)
            targets = {cat.name for cat in form.cleaned_data["targets"]}
            if form.cleaned_data["use_wishlist"]:
                targets |= set(Cat.objects.wishlist().values_list("name", flat=True))
            result = fetch_banners(seed)
            pulls = {name: rolls.pulls for name, rolls in result.banners.items()}
            guaranteed_pulls = {name: rolls.guaranteed for name, rolls in result.banners.items()}
            plans = plan(
                pulls,
                targets,
                form.cleaned_data["tickets"],
                form.cleaned_data["catfood"],
                guaranteed_pulls=guaranteed_pulls,
                multis=result.multis,
            )
    else:
        form = PlannerForm(initial={"seed": Seed.current()})
    return render(request, "planner/planner.html", {"form": form, "plans": plans})


def _save_flags(post) -> None:
    owned = set(post.getlist("owned"))
    wanted = set(post.getlist("wanted"))
    for cat in Cat.objects.all():
        cat.owned = str(cat.pk) in owned
        cat.wanted = str(cat.pk) in wanted
        cat.save(update_fields=["owned", "wanted"])


def collection(request):
    form = CatForm()
    if request.method == "POST":
        if "save" in request.POST:
            _save_flags(request.POST)
            return redirect("collection")
        if "remove" in request.POST:
            Cat.objects.filter(pk__in=request.POST.getlist("delete")).delete()
            return redirect("collection")
        form = CatForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("collection")
    return render(request, "planner/collection.html", {"cats": Cat.objects.all(), "form": form})
