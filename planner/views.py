import json

from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.views.decorators.http import require_POST

from neko.models import CATFOOD_PER_DRAW, GACHA_RARITIES
from neko.normal import BANNERS_BY_KEY
from neko.rng import backtrack
from neko.roller import DEFAULT_COUNT, GUARANTEED_OPTIONS
from neko.tierdata import load_tiers
from planner import seekjobs
from planner.forms import (
    MAX_FUTURE_UBERS,
    MAX_SEEK_ROLLS,
    MAX_TRACK_LENGTH,
    MIN_SEEK_ROLLS,
    PlannerForm,
)
from planner.models import Cat, Seed, Unit
from planner.services import (
    NORMAL_DEFAULT_KEYS,
    NORMAL_TARGET_PRESETS,
    RARITY_ORDER,
    SECTION_NOTES,
    banner_titles,
    build_normal_plan,
    build_normal_tracks,
    build_tracks,
    capped_banner_limits,
    collection_sections,
    display_titles,
    equivalent_banners,
    export_collection,
    fetch_banners,
    fetch_for_banners,
    import_collection,
    newly_added_ubers,
    normal_banner_choices,
    normal_item_options,
    normal_seek_banner,
    normal_seek_pools,
    picker_groups,
    seek_banner,
    seek_pool_groups,
    seek_run_choices,
    set_sections,
    subset_solutions,
    tier_badges,
    tier_list_rows,
    trace_marks,
    unit_stats,
    wiki_url,
)


def _picker_cats():
    """Cats for the target picker, each carrying its tier badge (if the tier list ranks
    it). select_related("unit"): the owned/wanted chip marks read cat.unit, one query
    per chip otherwise."""
    cats = list(Cat.objects.select_related("unit").prefetch_related("banners"))
    badges = tier_badges()
    for cat in cats:
        cat.tier_badge = badges.get(cat.unit.unit_id) if cat.unit else None

    return cats


def planner(request):
    """The planner shell: the form plus empty hosts that JS fills with tracks/plan.

    The Past picker group is ~2000 per-run rows (nearly all of the page's bytes and
    render time), so it ships as a count only; JS fetches picker_past on first open.
    """
    cats = _picker_cats()
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
    groups = dict(picker_groups(_picker_cats(), titles=banner_titles()))

    return render(request, "planner/_picker_rows.html", {"sections": groups.get("Past", [])})


def _roll(seed, chosen_banners, count, last_cat="", simulate_guaranteed=0, future_ubers=None):
    if chosen_banners:
        return fetch_for_banners(
            seed,
            chosen_banners,
            count,
            last_cat=last_cat,
            simulate_guaranteed=simulate_guaranteed,
            future_ubers=future_ubers,
        )

    return fetch_banners(
        seed,
        count,
        last_cat=last_cat,
        simulate_guaranteed=simulate_guaranteed,
        future_ubers=future_ubers,
    )


def _track_length(request):
    """Rows to roll for the Rolls table (godfat's unit count), clamped to [1, MAX]."""
    try:
        n = int(request.POST.get("track_length", DEFAULT_COUNT))
    except ValueError:
        return DEFAULT_COUNT

    return max(1, min(n, MAX_TRACK_LENGTH))


def _simulate_guaranteed(request):
    """The guaranteed-multi size to force onto every banner (godfat's dropdown), or 0 for
    off. Values outside the offered set are ignored, so a stray post can't balloon the grid."""
    try:
        n = int(request.POST.get("simulate_guaranteed", 0))
    except ValueError:
        return 0

    return n if n in GUARANTEED_OPTIONS else 0


def _future_ubers(request):
    """The per-banner future-uber padding (godfat's "Count of future ubers", one counter
    per banner): a JSON {run name: count} posted by the legend steppers, counts clamped
    to [0, MAX]. Anything malformed just means no padding."""
    try:
        raw = json.loads(request.POST.get("future_ubers", "") or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}

    counts = {}
    for name, count in raw.items():
        try:
            count = int(count)
        except TypeError, ValueError:
            continue
        if count > 0:
            counts[str(name)] = min(count, MAX_FUTURE_UBERS)

    return counts


def _trace(request):
    """The cell a trace click picked (godfat's pick), as (legend tag, stream index,
    guaranteed) - or None when nothing was clicked or the post is malformed. ``guaranteed``
    is set for a click in the guaranteed column."""
    tag = request.POST.get("trace_tag", "")
    try:
        index = int(request.POST.get("trace_idx", ""))
    except ValueError:
        return None

    if not (tag.isdigit() and index >= 0):
        return None

    return (tag, index, request.POST.get("trace_guaranteed") == "1")


@require_POST
def seed_backtrack(request):
    """Step the seed back one roll (godfat's Backtrack): the pull just before the current
    first cell becomes the new first cell. Returns the earlier seed as JSON."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponseBadRequest("seed must be an integer")

    return JsonResponse({"seed": backtrack(seed)})


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


def _unit_ids():
    """{cat name: catalogue unit_id}, so the Rolls table can hotlink each cell's form
    icon for the display-mode toggle."""
    return dict(Unit.objects.values_list("name", "unit_id"))


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
    count = _track_length(request)
    future_ubers = _future_ubers(request)
    result = _roll(
        seed,
        request.POST.getlist("banners"),
        count,
        last_cat,
        simulate_guaranteed=_simulate_guaranteed(request),
        future_ubers=future_ubers,
    )
    equivalents = equivalent_banners(result.banners)
    pulls, guaranteed, rerolls, _ = _rolls_by_banner(result)
    trace = _trace(request)
    marks = None
    if trace is not None:
        marks = trace_marks(
            pulls,
            rerolls,
            equivalents,
            trace[0],
            trace[1],
            last_cat,
            result.multis,
            guaranteed_pulls=guaranteed,
            guaranteed=trace[2],
            guaranteed_sizes={
                name: rolls.guaranteed_rolls for name, rolls in result.banners.items()
            },
        )
    track = build_tracks(
        pulls,
        rerolls,
        equivalents,
        marks=marks,
        owned=_owned_names(),
        guaranteed=guaranteed,
        wanted=_wanted_names(),
        titles=display_titles(),
        rows=count,
        debuts=newly_added_ubers(),
        future=future_ubers,
        unit_ids=_unit_ids(),
        tiers=tier_badges(),
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
        debuts=newly_added_ubers(),
        unit_ids=_unit_ids(),
        tiers=tier_badges(),
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
            "tier": tier_badges().get(unit.unit_id),
            "stats": unit_stats(unit.unit_id),
        }
    )


def unit_forms(request):
    """{unit_id: form names} for every catalogued unit, in one payload: the Rolls form
    picker renames the cells client-side, without refetching the table."""
    return JsonResponse(dict(Unit.objects.values_list("unit_id", "forms")))


def seed_finder(request):
    """The seed finder: pick the banner you rolled on, enter the cats you got in
    order, and a background search recovers your seed from them."""
    return render(
        request,
        "planner/seek.html",
        {
            "run_groups": seek_run_choices(),
            "min_rolls": MIN_SEEK_ROLLS,
            "max_rolls": MAX_SEEK_ROLLS,
        },
    )


def seek_pool(request):
    """The chosen banner's rollable cats as grouped select options, so the finder can
    build its roll pickers without shipping every pool up front."""
    banner = seek_banner(request.GET.get("banner", ""))
    if banner is None:
        return HttpResponseBadRequest("unknown banner")

    return JsonResponse({"name": banner.name, "groups": seek_pool_groups(banner)})


def _observed_rolls(request, banner):
    """The posted rolls as the (rarity, slot) pairs seek_seed takes, or None when
    anything is malformed or points outside the banner's pools."""
    observed = []
    for value in request.POST.getlist("rolls"):
        index, _, slot = value.partition(":")
        try:
            index, slot = int(index), int(slot)
        except ValueError:
            return None

        if not 0 <= index < len(GACHA_RARITIES):
            return None

        rarity = GACHA_RARITIES[index]
        if not 0 <= slot < len(banner.pool(rarity)):
            return None

        observed.append((rarity, slot))

    return observed


@require_POST
def seek_start(request):
    """Kick off a seed search for the posted banner + observed rolls; returns the job
    key the page polls seek_status with."""
    banner = seek_banner(request.POST.get("banner", ""))
    if banner is None:
        return HttpResponseBadRequest("unknown banner")

    observed = _observed_rolls(request, banner)
    if observed is None:
        return HttpResponseBadRequest("malformed rolls")
    if not MIN_SEEK_ROLLS <= len(observed) <= MAX_SEEK_ROLLS:
        return HttpResponseBadRequest(f"enter between {MIN_SEEK_ROLLS} and {MAX_SEEK_ROLLS} rolls")

    rarity, slot = observed[-1]
    last_cat = banner.pool(rarity)[slot]

    return JsonResponse({"job": seekjobs.start(banner, observed, last_cat)})


def seek_status(request):
    """One poll of a running search: progress while sieving, matches once done."""
    job = seekjobs.get(request.GET.get("job", ""))
    if job is None:
        return HttpResponseBadRequest("unknown job")

    return JsonResponse(job.snapshot())


def normal_capsules(request):
    """The Normal Capsules tracker: the normal-side gacha runs on its own seed,
    independent of the rare one the planner follows. One page holds its A/B tracks
    (Catseye event machines included), its own seed finder, and the path planner."""
    return render(
        request,
        "planner/normal.html",
        {
            "banners": normal_banner_choices(),
            "default_keys": NORMAL_DEFAULT_KEYS,
            "seek_pools": normal_seek_pools(),
            "min_rolls": MIN_SEEK_ROLLS,
            "max_rolls": MAX_SEEK_ROLLS,
            "target_presets": [
                (value, label) for value, (label, _) in NORMAL_TARGET_PRESETS.items()
            ],
            "item_options": normal_item_options(),
        },
    )


@require_POST
def normal_tracks(request):
    """A/B track tables for the normal seed + chosen capsule machines. ``last_item``
    is the dupe memory: the item the pull just before this view obtained."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponse("")

    track = build_normal_tracks(
        seed,
        request.POST.getlist("banners"),
        _track_length(request),
        last_item=request.POST.get("last_item", "").strip(),
    )

    return render(request, "planner/_normal_tracks.html", {"track": track})


MAX_PLAN_ROLLS = 500  # per currency; normal_plan caps the total look-ahead anyway

# The plan panel's currencies: Normal Cat Tickets feed the plain capsule and the
# Catfruit/Catseye machines alike; each lucky ticket kind is its own stash.
_TICKET_KINDS = ("normal", "lucky", "luckyg")


def _normal_tickets(request):
    """The posted currency counts, as {kind: rolls}: a JSON object from the plan
    panel's steppers, unknown kinds dropped, counts clamped."""
    try:
        raw = json.loads(request.POST.get("tickets", "") or "{}")
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}

    tickets = {}
    for kind, count in raw.items():
        try:
            count = int(count)
        except TypeError, ValueError:
            continue
        if kind in _TICKET_KINDS and count > 0:
            tickets[kind] = min(count, MAX_PLAN_ROLLS)

    return tickets


@require_POST
def normal_plan(request):
    """Run the normal-side path planner: from the current seed, the pull sequence
    over the live machines that collects the most of the chosen target within the
    posted ticket stashes."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponseBadRequest("seed must be an integer")

    tickets = _normal_tickets(request)
    machines = [key for key in request.POST.getlist("banners") if key in BANNERS_BY_KEY]
    if not tickets or not machines:
        return HttpResponseBadRequest("give some tickets to at least one shown machine")

    plan = build_normal_plan(
        seed,
        machines,
        tickets,
        request.POST.get("target", "dark"),
        _track_length(request),
        last_item=request.POST.get("last_item", "").strip(),
    )
    if plan is None:
        return HttpResponseBadRequest("unknown target")

    return render(request, "planner/_normal_plan.html", {"plan": plan, "track": plan["track"]})


def _observed_normal_rolls(request, banner):
    """The posted rolls as the (pool, slot) pairs seek_normal takes, or None when
    anything is malformed or points outside the banner's pools."""
    observed = []
    for value in request.POST.getlist("rolls"):
        pool, _, slot = value.partition(":")
        try:
            pool, slot = int(pool), int(slot)
        except ValueError:
            return None

        if not 0 <= pool < len(banner.pools):
            return None
        if not 0 <= slot < len(banner.pools[pool].items):
            return None

        observed.append((pool, slot))

    return observed


@require_POST
def normal_seek_start(request):
    """Kick off a normal-seed search for the posted banner + observed rolls; returns
    the job key the page polls seek_status with (the finders share the registry)."""
    banner = normal_seek_banner(request.POST.get("banner", ""))
    if banner is None:
        return HttpResponseBadRequest("unknown banner")

    observed = _observed_normal_rolls(request, banner)
    if observed is None:
        return HttpResponseBadRequest("malformed rolls")
    if not MIN_SEEK_ROLLS <= len(observed) <= MAX_SEEK_ROLLS:
        return HttpResponseBadRequest(f"enter between {MIN_SEEK_ROLLS} and {MAX_SEEK_ROLLS} rolls")

    pool, slot = observed[-1]
    last_item = banner.pools[pool].items[slot]

    return JsonResponse({"job": seekjobs.start_normal(banner, observed, last_item)})


def collection(request):
    """The whole cat dictionary in one page with the player's owned/wishlist marks,
    browsable by rarity or by gacha set. A unit can sit in several set sections (fests
    repeat their cats) - the marks are per unit, so every copy stays in step."""
    units = list(Unit.objects.named())
    badges = tier_badges()
    for unit in units:
        unit.tier_badge = badges.get(unit.unit_id)
    context = {
        # Both views share the section partial, so a rarity bin becomes a one-row section.
        "rarity_sections": [(r, "", [(r, bin)]) for r, bin in collection_sections(units)],
        "set_sections": [
            (label, SECTION_NOTES.get(label, ""), rarities)
            for label, rarities in set_sections(units)
        ],
    }

    return render(request, "planner/collection.html", context)


def tier_list(request):
    """The cumulative uber tier list, tier by tier, with catalogue names and icons."""
    doc = load_tiers()
    rows = tier_list_rows(doc)
    # The form picker renames entries client-side; ship each unit's form names along.
    forms = dict(Unit.objects.values_list("unit_id", "forms"))
    for row in rows:
        for entry in row["entries"]:
            entry["forms"] = "|".join(forms.get(entry["unit_id"], []))
    context = {
        "rows": rows,
        "source": doc["source"],
        "fetched": doc["fetched"],
    }

    return render(request, "planner/tiers.html", context)


def about(request):
    """Static "about" page: what the tool is, who built it, and what's credited."""
    return render(request, "planner/about.html")


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
    marked. Bulk wishlist stars owned units too, matching the per-cat star; the planner
    still ignores wishlisted cats you own (_wanted_names excludes owned)."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")

    units = Unit.objects.filter(pk__in=request.POST.getlist("pk"))
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


def collection_export(request):
    """Download the owned/wishlist marks as a JSON snapshot the player can back up or move
    to another install."""
    resp = JsonResponse(export_collection(), json_dumps_params={"indent": 2})
    resp["Content-Disposition"] = 'attachment; filename="neko-collection.json"'

    return resp


@require_POST
def collection_import(request):
    """Restore owned/wishlist marks from an uploaded export snapshot, replacing the current
    ones. Returns the applied counts (the page reloads to show them)."""
    upload = request.FILES.get("file")
    if upload is None:
        return HttpResponseBadRequest("no file uploaded")

    try:
        data = json.load(upload)
    except json.JSONDecodeError, UnicodeDecodeError:
        return HttpResponseBadRequest("not a JSON file")

    try:
        result = import_collection(data)
    except ValueError, TypeError:
        return HttpResponseBadRequest("not a Neko collection export")

    return JsonResponse(result)
