from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from neko.models import CATFOOD_PER_DRAW
from neko.roller import DEFAULT_COUNT
from planner.forms import PlannerForm
from planner.models import Cat, Seed, Unit
from planner.services import (
    RARITY_ORDER,
    SECTION_NOTES,
    banner_titles,
    build_tracks,
    capped_banner_limits,
    collection_sections,
    display_titles,
    equivalent_banners,
    fetch_banners,
    fetch_for_banners,
    picker_groups,
    set_sections,
    subset_solutions,
    wiki_url,
)


def planner(request):
    """The planner shell: the form plus empty hosts that JS fills with tracks/plan.

    The Past picker group is ~2000 per-run rows (nearly all of the page's bytes and
    render time), so it ships as a count only; JS fetches picker_past on first open.
    """
    # select_related("unit"): the owned/wanted chip marks read cat.unit, one query per
    # chip otherwise.
    cats = list(Cat.objects.select_related("unit").prefetch_related("banners"))
    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    target_flat = sorted(cats, key=lambda cat: (-rank.get(cat.rarity, -1), cat.name))

    groups, past_count = [], 0
    for label, rows in picker_groups(cats, titles=banner_titles()):
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
    groups = dict(picker_groups(cats, titles=banner_titles()))

    return render(request, "planner/_picker_rows.html", {"sections": groups.get("Past", [])})


def _roll(seed, chosen_banners, count, last_cat=""):
    if chosen_banners:
        return fetch_for_banners(seed, chosen_banners, count, last_cat=last_cat)

    return fetch_banners(seed, count, last_cat=last_cat)


def _rolls_by_banner(result):
    """A roll result split into the per-banner maps build_tracks and subset_solutions
    take: (pulls, guaranteed, rerolls, guaranteed_rerolls)."""
    banners = result.banners

    return (
        {name: rolls.pulls for name, rolls in banners.items()},
        {name: rolls.guaranteed for name, rolls in banners.items()},
        {name: rolls.rerolls for name, rolls in banners.items()},
        {name: rolls.guaranteed_rerolls for name, rolls in banners.items()},
    )


def _owned_names():
    """Cat names you already own, to flag Uber/Legend cats missing from your collection."""
    return set(Unit.objects.filter(owned=True).values_list("name", flat=True))


def _wanted_names():
    """Cat names on your wishlist, starred in the track and steps."""
    return set(Unit.objects.wishlist().values_list("name", flat=True))


@require_POST
def tracks(request):
    """A/B track tables for the current seed + banners, before any plan is run.

    ``last_cat`` is the dupe memory: the cat the previous pull got (a dice jump, an
    applied plan, or a seed you came back to) - it can dupe the very first cell."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponse("")

    last_cat = request.POST.get("last_cat", "").strip()
    result = _roll(seed, request.POST.getlist("banners"), DEFAULT_COUNT, last_cat)
    equivalents = equivalent_banners(result.banners)
    pulls, guaranteed, rerolls, _ = _rolls_by_banner(result)
    track = build_tracks(
        pulls,
        rerolls,
        equivalents,
        owned=_owned_names(),
        guaranteed=guaranteed,
        wanted=_wanted_names(),
        titles=display_titles(),
    )

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
        targets |= _wanted_names()

    explore = form.cleaned_data["explore"]
    count = form.cleaned_data["horizon"] if explore else DEFAULT_COUNT
    last_cat = request.POST.get("last_cat", "").strip()
    result = _roll(seed, request.POST.getlist("banners"), count, last_cat)
    equivalents = equivalent_banners(result.banners)
    pulls, guaranteed_pulls, rerolls, guaranteed_rerolls = _rolls_by_banner(result)
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
        banner_limits=banner_limits,
        owned=_owned_names(),
        wanted=_wanted_names(),
        titles=display_titles(),
        guaranteed_rerolls=guaranteed_rerolls,
        last_cat=last_cat,
    )

    return JsonResponse(
        {
            "solutions_html": render_to_string(
                "planner/_solutions.html", {"solutions": solutions}, request
            ),
        }
    )


def unit_info(request):
    """A unit's forms, rarity and wiki link, for the cat popup (looked up by base-form
    name - the label every cat chip and track cell carries)."""
    unit = Unit.objects.filter(name=request.GET.get("name", "")).first()
    if unit is None:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "unit_id": unit.unit_id,
            "name": unit.name,
            "rarity": unit.rarity,
            "forms": unit.forms,
            "wiki": wiki_url(unit.name, unit.rarity),
        }
    )


def collection(request):
    """The whole cat dictionary in one page with the player's owned/wishlist marks,
    browsable by rarity or by gacha set. A unit can sit in several set sections (fests
    repeat their cats) - the marks are per unit, so every copy stays in step."""
    units = list(Unit.objects.named())
    context = {
        # Both views share the section partial, so a rarity bin becomes a one-row section.
        "rarity_sections": [(r, "", [(r, bin)]) for r, bin in collection_sections(units)],
        "set_sections": [
            (label, SECTION_NOTES.get(label, ""), rarities)
            for label, rarities in set_sections(units)
        ],
    }

    return render(request, "planner/collection.html", context)


@require_POST
def apply_plan(request):
    """Mark the cats a plan gets you as owned and drop them from the wishlist. Applying
    means "you rolled it", so the plan's seed-after becomes the stored seed."""
    names = request.POST.getlist("cats")
    applied = Unit.objects.filter(name__in=names).update(owned=True, wanted=False)

    try:
        Seed.store(int(request.POST["seed_after"]))
    except KeyError, ValueError:
        pass

    return JsonResponse({"applied": applied})


@require_POST
def collection_bulk(request):
    """Mark a whole section owned/wanted in one tap - or clear it when it's already all
    marked. Wishlist marks skip owned units, like everywhere else."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")

    units = Unit.objects.filter(pk__in=request.POST.getlist("pk"))
    if field == "wanted":
        units = units.filter(owned=False)

    value = units.filter(**{field: False}).exists()
    units.update(**{field: value})

    return JsonResponse({"value": value})


@require_POST
def collection_toggle(request):
    """Flip a single unit's owned/wanted flag and return the new state as JSON."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")

    unit = get_object_or_404(Unit, pk=request.POST.get("pk"))
    setattr(unit, field, not getattr(unit, field))
    unit.save(update_fields=[field])

    return JsonResponse({"owned": unit.owned, "wanted": unit.wanted})
