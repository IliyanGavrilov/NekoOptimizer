from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from neko.models import CATFOOD_PER_DRAW
from neko.scraper import DEFAULT_COUNT
from planner.forms import CatForm, PlannerForm
from planner.models import Cat, Seed, Unit
from planner.services import (
    RARITY_ORDER,
    build_tracks,
    capped_banner_limits,
    catalogue,
    equivalent_banners,
    fetch_banners,
    fetch_for_banners,
    picker_groups,
    subset_solutions,
    unit_for_cat,
)


def planner(request):
    """The planner shell: the form plus empty hosts that JS fills with tracks/plan.

    The Past picker group is ~2000 per-run rows (nearly all of the page's bytes and
    render time), so it ships as a count only; JS fetches [picker_past] on first open.
    """
    # select_related("unit"): the owned/wanted chip marks read cat.unit, one query per
    # chip otherwise.
    cats = list(Cat.objects.select_related("unit").prefetch_related("banners"))
    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    target_flat = sorted(cats, key=lambda cat: (-rank.get(cat.rarity, -1), cat.name))
    groups, past_count = [], 0
    for label, rows in picker_groups(cats):
        if label == "Past":
            past_count = len(rows)
            groups.append((label, None))  # rendered as a lazy shell in its place
        else:
            groups.append((label, rows))
    context = {
        "form": PlannerForm(),
        "target_groups": groups,
        "past_count": past_count,
        "target_flat": target_flat,
    }
    return render(request, "planner/planner.html", context)


def picker_past(request):
    """The Past picker rows, fetched when the group is first opened."""
    cats = list(Cat.objects.select_related("unit").prefetch_related("banners"))
    groups = dict(picker_groups(cats))
    return render(request, "planner/_picker_rows.html", {"sections": groups.get("Past", [])})


def _scrape(seed, chosen_banners, count):
    if chosen_banners:
        return fetch_for_banners(seed, chosen_banners, count)
    return fetch_banners(seed, count)


def _owned_names():
    """Cat names you already own, to flag Uber/Legend cats missing from your collection."""
    return set(Cat.objects.filter(unit__owned=True).values_list("name", flat=True))


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
    guaranteed = {name: rolls.guaranteed for name, rolls in result.banners.items()}
    rerolls = {name: rolls.rerolls for name, rolls in result.banners.items()}
    track = build_tracks(pulls, rerolls, equivalents, owned=_owned_names(), guaranteed=guaranteed)
    return render(request, "planner/_tracks.html", {"track": track})


@require_POST
def find_plan(request):
    """Solve every target subset; return the accordion of solutions as an HTML fragment."""
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
    # One accordion row per target subset: each reachable one carries its own
    # highlighted track + steps; the rest are listed as "Not found".
    solutions = subset_solutions(
        pulls,
        rerolls,
        equivalents,
        targets,
        tickets=tickets,
        catfood=catfood,
        guaranteed_pulls=guaranteed_pulls,
        multis=result.multis,
        ticket_value=form.cleaned_data["ticket_value"],
        prefer=form.cleaned_data["prefer"],
        banner_limits=banner_limits,
        owned=_owned_names(),
    )
    return JsonResponse(
        {
            "solutions_html": render_to_string(
                "planner/_solutions.html", {"solutions": solutions}, request
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
    cats = Cat.objects.select_related("unit").prefetch_related("banners")
    context = {"form": form, "sections": catalogue(cats)}
    return render(request, "planner/collection.html", context)


@require_POST
def apply_plan(request):
    """Mark a plan's obtained cats as owned and drop them from the wishlist."""
    names = request.POST.getlist("cats")
    applied = Unit.objects.filter(cats__name__in=names).update(owned=True, wanted=False)
    return JsonResponse({"applied": applied})


@require_POST
def wishlist_all_unowned(request):
    """Add every cat you don't own yet to the wishlist - one tap for completion play."""
    units = Cat.objects.filter(unit__owned=False).values_list("unit", flat=True)
    wanted = Unit.objects.filter(pk__in=units, owned=False).update(wanted=True)
    return JsonResponse({"wanted": wanted})


@require_POST
def collection_toggle(request):
    """Flip a single cat's owned/wanted flag and return the new state as JSON."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")
    cat = get_object_or_404(Cat, pk=request.POST.get("pk"))
    unit = cat.unit or unit_for_cat(cat.name, cat.rarity)
    setattr(unit, field, not getattr(unit, field))
    unit.save(update_fields=[field])
    if cat.unit_id is None:
        cat.unit = unit
        cat.save(update_fields=["unit"])
    return JsonResponse({"owned": unit.owned, "wanted": unit.wanted})
