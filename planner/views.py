from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from neko.models import CATFOOD_PER_DRAW
from neko.planning import plan
from neko.scraper import DEFAULT_COUNT
from planner.forms import CatForm, PlannerForm
from planner.models import Cat, Seed
from planner.services import (
    RARITY_ORDER,
    build_tracks,
    capped_banner_limits,
    catalogue,
    dated_catalogue,
    equivalent_banners,
    fetch_banners,
    fetch_for_banners,
    plan_highlight,
    plan_summary,
)


def planner(request):
    """The planner shell: the form plus empty hosts that JS fills with tracks/plan."""
    cats = list(Cat.objects.prefetch_related("banners"))
    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    target_flat = sorted(cats, key=lambda cat: (-rank.get(cat.rarity, -1), cat.name))
    context = {
        "form": PlannerForm(),
        "target_groups": dated_catalogue(cats, reverse_rarity=True),
        "target_flat": target_flat,
    }
    return render(request, "planner/planner.html", context)


def _scrape(seed, chosen_banners, count):
    if chosen_banners:
        return fetch_for_banners(seed, chosen_banners, count)
    return fetch_banners(seed, count)


@require_POST
def tracks(request):
    """A/B track tables for the current seed + banners, before any plan is run."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponse("")
    result = _scrape(seed, request.POST.getlist("banners"), DEFAULT_COUNT)
    equivalents = equivalent_banners(result.banners)
    pulls = {name: rolls.pulls for name, rolls in result.banners.items()}
    rerolls = {name: rolls.rerolls for name, rolls in result.banners.items()}
    track = build_tracks(pulls, rerolls, equivalents)
    return render(request, "planner/_tracks.html", {"track": track})


@require_POST
def find_plan(request):
    """Compute a plan; return the highlighted tracks and the summary as HTML fragments."""
    form = PlannerForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)
    seed = form.cleaned_data["seed"]
    Seed.store(seed)
    targets = {cat.name for cat in form.cleaned_data["targets"]}
    if form.cleaned_data["use_wishlist"]:
        targets |= set(Cat.objects.wishlist().values_list("name", flat=True))
    explore = form.cleaned_data["explore"]
    count = form.cleaned_data["horizon"] if explore else DEFAULT_COUNT
    result = _scrape(seed, request.POST.getlist("banners"), count)
    equivalents = equivalent_banners(result.banners)
    pulls = {name: rolls.pulls for name, rolls in result.banners.items()}
    guaranteed_pulls = {name: rolls.guaranteed for name, rolls in result.banners.items()}
    rerolls = {name: rolls.rerolls for name, rolls in result.banners.items()}
    banner_limits = capped_banner_limits(pulls, form.cleaned_data["platinum_legend_cap"])
    if explore:
        # Ignore the budget but still fund single pulls with tickets (their real
        # currency) so an all-singles plan reads "8 tickets", not "1200 catfood".
        horizon = form.cleaned_data["horizon"]
        tickets, catfood = horizon, horizon * CATFOOD_PER_DRAW
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
    # Highlight the best plan's path on the tracks; the summary lists every option.
    path, target_idx = plan_highlight(plans[0], equivalents) if plans else ({}, {})
    track = build_tracks(pulls, rerolls, equivalents, path, target_idx)
    return JsonResponse(
        {
            "tracks_html": render_to_string("planner/_tracks.html", {"track": track}, request),
            "summary_html": render_to_string(
                "planner/_summary.html", {"summaries": plan_summary(plans, equivalents)}, request
            ),
        }
    )


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
