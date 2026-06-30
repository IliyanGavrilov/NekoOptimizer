from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from neko.models import CATFOOD_PER_DRAW
from neko.planning import plan
from neko.scraper import DEFAULT_COUNT
from planner.forms import CatForm, PlannerForm
from planner.models import Cat, Seed
from planner.services import (
    RARITY_ORDER,
    capped_banner_limits,
    catalogue,
    dated_catalogue,
    equivalent_banners,
    fetch_banners,
    fetch_for_banners,
    plan_views,
)


def planner(request):
    plans = None
    pulls: dict = {}
    equivalents: dict[str, list[str]] = {}
    if request.method == "POST":
        form = PlannerForm(request.POST)
        if form.is_valid():
            seed = form.cleaned_data["seed"]
            Seed.store(seed)
            targets = {cat.name for cat in form.cleaned_data["targets"]}
            if form.cleaned_data["use_wishlist"]:
                targets |= set(Cat.objects.wishlist().values_list("name", flat=True))
            chosen_banners = request.POST.getlist("banners")
            # Explore mode looks deeper into the seed and ignores the player's
            # budget, so the plan's cost shows the cheapest way to reach a target.
            explore = form.cleaned_data["explore"]
            count = form.cleaned_data["horizon"] if explore else DEFAULT_COUNT
            result = (
                fetch_for_banners(seed, chosen_banners, count)
                if chosen_banners
                else fetch_banners(seed, count)
            )
            equivalents = equivalent_banners(result.banners)
            pulls = {name: rolls.pulls for name, rolls in result.banners.items()}
            guaranteed_pulls = {name: rolls.guaranteed for name, rolls in result.banners.items()}
            rerolls = {name: rolls.rerolls for name, rolls in result.banners.items()}
            banner_limits = capped_banner_limits(pulls, form.cleaned_data["platinum_legend_cap"])
            if explore:
                tickets, catfood = 0, form.cleaned_data["horizon"] * CATFOOD_PER_DRAW
            else:
                tickets, catfood = form.cleaned_data["tickets"], form.cleaned_data["catfood"]
            plans = plan(
                pulls,
                targets,
                tickets,
                catfood,
                guaranteed_pulls=guaranteed_pulls,
                multis=result.multis,
                ticket_value=form.cleaned_data["ticket_value"],
                prefer=form.cleaned_data["prefer"],
                banner_limits=banner_limits,
                rerolls=rerolls,
            )
    else:
        form = PlannerForm()
    # Every cat is targetable, owned or not, so you can always look up a unit.
    cats = list(Cat.objects.prefetch_related("banners"))
    owned_names = set(Cat.objects.filter(owned=True).values_list("name", flat=True))
    views = plan_views(plans, pulls, equivalents, owned_names) if plans is not None else None
    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    target_flat = sorted(cats, key=lambda cat: (-rank.get(cat.rarity, -1), cat.name))
    context = {
        "form": form,
        "plan_views": views,
        "target_groups": dated_catalogue(cats, reverse_rarity=True),
        "target_flat": target_flat,
    }
    return render(request, "planner/planner.html", context)


def collection(request):
    form = CatForm()
    if request.method == "POST":
        form = CatForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect("collection")
    cats = Cat.objects.prefetch_related("banners")
    context = {"form": form, "sections": catalogue(cats)}
    return render(request, "planner/collection.html", context)


@require_POST
def apply_plan(request):
    """Mark a plan's obtained cats as owned and drop them from the wishlist."""
    names = request.POST.getlist("cats")
    applied = Cat.objects.filter(name__in=names).update(owned=True, wanted=False)
    return JsonResponse({"applied": applied})


@require_POST
def collection_toggle(request):
    """Flip a single cat's owned/wanted flag and return the new state as JSON."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")
    cat = get_object_or_404(Cat, pk=request.POST.get("pk"))
    setattr(cat, field, not getattr(cat, field))
    cat.save(update_fields=[field])
    return JsonResponse({"owned": cat.owned, "wanted": cat.wanted})
