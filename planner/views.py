from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from neko.planning import plan
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
)


def planner(request):
    plans = None
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
            result = (
                fetch_for_banners(seed, chosen_banners) if chosen_banners else fetch_banners(seed)
            )
            equivalents = equivalent_banners(result.banners)
            pulls = {name: rolls.pulls for name, rolls in result.banners.items()}
            guaranteed_pulls = {name: rolls.guaranteed for name, rolls in result.banners.items()}
            banner_limits = capped_banner_limits(pulls, form.cleaned_data["platinum_legend_cap"])
            plans = plan(
                pulls,
                targets,
                form.cleaned_data["tickets"],
                form.cleaned_data["catfood"],
                guaranteed_pulls=guaranteed_pulls,
                multis=result.multis,
                ticket_value=form.cleaned_data["ticket_value"],
                prefer=form.cleaned_data["prefer"],
                banner_limits=banner_limits,
            )
    else:
        form = PlannerForm(initial={"seed": Seed.current()})
    unowned = list(Cat.objects.unowned().prefetch_related("banners"))
    owned_names = set(Cat.objects.filter(owned=True).values_list("name", flat=True))
    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    target_flat = sorted(unowned, key=lambda cat: (-rank.get(cat.rarity, -1), cat.name))
    context = {
        "form": form,
        "plans": plans,
        "target_groups": dated_catalogue(unowned, reverse_rarity=True),
        "target_flat": target_flat,
        "owned_names": owned_names,
        "equivalents": equivalents,
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
def collection_toggle(request):
    """Flip a single cat's owned/wanted flag and return the new state as JSON."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")
    cat = get_object_or_404(Cat, pk=request.POST.get("pk"))
    setattr(cat, field, not getattr(cat, field))
    cat.save(update_fields=[field])
    return JsonResponse({"owned": cat.owned, "wanted": cat.wanted})
