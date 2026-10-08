import json
from dataclasses import asdict

from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from neko.gamedata import load_cannons, load_evolve, load_talents
from neko.guidedata import load_guide
from neko.models import CATFOOD_PER_DRAW, GACHA_RARITIES, Rarity, is_future_uber
from neko.normal import BANNERS_BY_KEY
from neko.region import CODES
from neko.region import current as active_region
from neko.rng import backtrack
from neko.roller import DEFAULT_COUNT, GUARANTEED_OPTIONS
from neko.statsdata import ABILITY_LABELS, ATTACK_LABELS, IMMUNITY_LABELS, TARGET_LABELS
from neko.tierdata import load_tiers
from planner import seekjobs
from planner.forms import (
    MAX_FUTURE_UBERS,
    MAX_SEEK_ROLLS,
    MAX_TRACK_LENGTH,
    MIN_SEEK_ROLLS,
    PlannerForm,
)
from planner.links import TOOL_DIRECTORY, unit_links
from planner.models import CannonPlan, Cat, Region, Seed, TalentPlan, Unit, UnitPlan
from planner.services import (
    CANNON_ADDONS,
    NORMAL_DEFAULT_KEYS,
    NORMAL_TARGET_PRESETS,
    PLAN_FILTER_ROWS,
    RARITY_ORDER,
    SECTION_NOTES,
    SUBSET_TARGET_LIMIT,
    banner_currencies,
    banner_debuts,
    banner_titles,
    build_normal_plan,
    build_normal_tracks,
    build_tracks,
    cat_banner_names,
    cat_options,
    collection_facets,
    collection_sections,
    combo_filter_groups,
    dictionary_sections,
    display_titles,
    equivalent_banners,
    export_collection,
    fetch_banners,
    fetch_for_banners,
    find_cats,
    import_collection,
    normal_banner_choices,
    normal_item_options,
    normal_seek_banner,
    normal_seek_pools,
    picker_groups,
    plannable_form,
    resources_board,
    seek_banner,
    seek_pool_groups,
    seek_run_choices,
    set_sections,
    subset_plan,
    subset_solutions,
    tier_badges,
    tier_list_doc,
    tier_list_index,
    tier_list_rows,
    trace_marks,
    unit_stats,
)


def _picker_cats():
    """Cats for the target picker, each carrying its tier badge (if the tier list ranks
    it) and its rendered chip. select_related("unit"): the owned/wanted chip marks read
    cat.unit, one query per chip otherwise. Banner membership comes separately, via
    cat_banner_names.

    The chip is rendered here, once per cat, because the picker repeats it on every banner
    row that carries the cat - ~20k chips over ~500 cats, and rendering per appearance was
    most of the Past fragment's cost."""
    cats = list(Cat.objects.select_related("unit"))
    badges = tier_badges()
    chip = get_template("planner/_picker_chip.html")
    for cat in cats:
        cat.tier_badge = badges.get(cat.unit.unit_id) if cat.unit else None
        cat.chip = chip.render({"cat": cat})

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
    for label, rows in picker_groups(cats, titles=banner_titles(), banner_names=cat_banner_names()):
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
    groups = dict(
        picker_groups(_picker_cats(), titles=banner_titles(), banner_names=cat_banner_names())
    )

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
    guaranteed, reroll) - or None when nothing was clicked or the post is malformed.
    ``guaranteed`` is set for a click in the guaranteed column; ``reroll`` for a click on a
    cell's "if dupe" branch (marked separately from its clean roll)."""
    tag = request.POST.get("trace_tag", "")
    try:
        index = int(request.POST.get("trace_idx", ""))
    except ValueError:
        return None

    if not (tag.isdigit() and index >= 0):
        return None

    return (
        tag,
        index,
        request.POST.get("trace_guaranteed") == "1",
        request.POST.get("trace_reroll") == "1",
    )


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


def _find_targets(request):
    """The cats the unified targets panel reports, read straight from the tracks POST.

    Returns ``(targets, wishlist, pks)``: ``targets`` and ``wishlist`` are ``{name: rarity}``
    maps - the cats you explicitly picked and (when "search my wishlist" is on) your unowned
    wanted cats; ``pks`` is ``{name: Cat pk}`` for the picks, so the panel can offer a remove.
    Both maps are always reported - at their position, a "999+" ceiling, or a ⚠ when no
    selected banner carries them - so the panel confirms a wishlist cat isn't coming, just
    like a pick."""
    picked = Cat.objects.filter(pk__in=request.POST.getlist("targets")).values_list(
        "name", "rarity", "pk"
    )
    targets = {name: rarity for name, rarity, _ in picked}
    pks = {name: pk for name, _, pk in picked}
    wishlist: dict[str, str] = {}
    if request.POST.get("use_wishlist"):
        wishlist = dict(Unit.objects.wishlist().values_list("name", "rarity"))
    return targets, wishlist, pks


def _future_targets(request):
    """The future-uber placeholders toggled as targets: a JSON list of qualified
    ``Future Uber n @ <banner>`` names posted by the legend toggle chips. Non-placeholder
    strings are dropped, so a stray post can't smuggle in an arbitrary name."""
    try:
        raw = json.loads(request.POST.get("future_targets", "") or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []

    return [str(name) for name in raw if is_future_uber(str(name))]


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
    display = _track_length(request)
    future_ubers = _future_ubers(request)
    # Roll the find window deep (godfat's Find ceiling): the "Find next" panel locates cats
    # far past the visible table, but only ``display`` rows render (build_tracks caps them).
    count = max(display, MAX_TRACK_LENGTH)
    result = _roll(
        seed,
        request.POST.getlist("banners"),
        count,
        last_cat,
        simulate_guaranteed=_simulate_guaranteed(request),
        future_ubers=future_ubers,
    )
    equivalents = equivalent_banners(result.banners)
    pulls, guaranteed, rerolls, guaranteed_rerolls = _rolls_by_banner(result)
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
            guaranteed_rerolls=guaranteed_rerolls,
            reroll=trace[3],
        )
    owned, wanted, titles = _owned_names(), _wanted_names(), display_titles()
    # The unified targets panel (godfat's Find, enriched): every cat you're searching for -
    # picks, wishlist and toggled future ubers - with its next position or a ⚠. Attached to
    # the browse track only, so the shared _tracks.html renders no panel on plan tracks.
    targets, wishlist, pks = _find_targets(request)
    # A toggled future uber searches like an explicit pick (its qualified name is already in
    # the padded pool), so fold it into the target map at uber rarity.
    future_targets = _future_targets(request)
    targets = {**targets, **{name: str(Rarity.UBER_SUPER_RARE) for name in future_targets}}
    # Scope the wishlist search to what these banners can actually drop (their unioned pools),
    # so "search my wishlist" lists only obtainable cats, not every unowned cat you want.
    obtainable = frozenset().union(*result.pools.values()) if result.pools else None
    found_cats = find_cats(
        pulls,
        targets,
        guaranteed=guaranteed,
        include_guaranteed=request.POST.get("exclude_guaranteed") != "1",
        wishlist=wishlist,
        pool=obtainable,
        owned=owned,
        wishlisted=wanted,
        pks=pks,
    )
    # Every reported target gilds all its track cells (the browse glow the legend promises) -
    # the same set the panel lists, so panel and glow stay in lockstep.
    target_names = {item["name"] for item in found_cats}
    track = build_tracks(
        pulls,
        rerolls,
        equivalents,
        marks=marks,
        owned=owned,
        guaranteed=guaranteed,
        wanted=wanted,
        titles=titles,
        rows=display,
        debuts=banner_debuts(),
        future=future_ubers,
        unit_ids=_unit_ids(),
        tiers=tier_badges(),
        target_names=target_names,
        guaranteed_rerolls=guaranteed_rerolls,
    )
    # A future-uber row is qualified by its banner's run name; show the short display title
    # instead (the same "June Bride" the legend and picker use), not the long marketing text.
    for item in found_cats:
        if item["future"] and item["banner"]:
            item["banner"] = titles.get(item["banner"], item["banner"])
    track["found_cats"] = found_cats
    # The same count a plan row carries, for the cats you're hunting: how many turn up in
    # these rolls out of everything you're searching for.
    track["found_hits"] = sum(1 for item in found_cats if item["found"])
    # The selected banners' titles, for the ⚠ row's "won't drop on: …" tooltip.
    track["selected_titles"] = ", ".join(sorted({titles.get(n, n) for n in result.banners}))

    return render(request, "planner/_tracks.html", {"track": track})


def _search_setup(request, form):
    """Everything both plan endpoints need from one posted form: the scoped target set and
    the keyword arguments the solvers take. Returns ``(targets, kwargs)``."""
    seed = form.cleaned_data["seed"]
    Seed.store(seed)
    targets = {cat.name for cat in form.cleaned_data["targets"]}
    if form.cleaned_data["use_wishlist"]:
        targets |= _wanted_names()
    # Future-uber targets are qualified placeholders, searchable only once the pool is
    # padded - so the plan must roll WITH that padding, and the target set keeps them even
    # though they're absent from the real (unpadded) pool the scoping below prunes against.
    future_targets = set(form.cleaned_data["future_targets"])
    future_ubers = _future_ubers(request)

    explore = form.cleaned_data["explore"]
    count = form.cleaned_data["horizon"] if explore else DEFAULT_COUNT
    last_cat = request.POST.get("last_cat", "").strip()
    result = _roll(
        seed, request.POST.getlist("banners"), count, last_cat, future_ubers=future_ubers
    )
    # Scope real-cat targets to what the selected banners can actually drop (their unioned
    # pools), the same rule the panel uses: a picked or wishlisted cat that isn't in these
    # banners is dropped rather than listed as a dead "Not found" row (a whole wishlist against
    # one banner). Future-uber placeholders are always in their padded pool, so keep them.
    if result.pools:
        targets &= frozenset().union(*result.pools.values())
    targets |= future_targets
    pulls, guaranteed_pulls, rerolls, guaranteed_rerolls = _rolls_by_banner(result)

    if explore:
        # Ignore the budget but still fund single pulls with tickets (their real
        # currency) so an all-singles plan reads "8 tickets", not "1200 catfood".
        horizon = form.cleaned_data["horizon"]
        tickets, catfood = horizon, horizon * CATFOOD_PER_DRAW
    else:
        tickets, catfood = form.cleaned_data["tickets"], form.cleaned_data["catfood"]

    kwargs = dict(
        pulls=pulls,
        rerolls=rerolls,
        equivalents=equivalent_banners(result.banners),
        tickets=tickets,
        catfood=catfood,
        # Platinum/Legend Capsules always run on their own scarce ticket pools, so their counts
        # come straight from the form even in explore mode (which frees only rare/catfood).
        platinum=form.cleaned_data["platinum_cap"],
        legend=form.cleaned_data["legend_cap"],
        guaranteed_pulls=guaranteed_pulls,
        multis=result.multis,
        ticket_value=form.cleaned_data["ticket_value"],
        banner_currency=banner_currencies(pulls),
        owned=_owned_names(),
        wanted=_wanted_names(),
        titles=display_titles(),
        guaranteed_rerolls=guaranteed_rerolls,
        last_cat=last_cat,
        debuts=banner_debuts(),
        unit_ids=_unit_ids(),
        tiers=tier_badges(),
    )

    return targets, kwargs


@require_POST
def find_plan(request):
    """Solve every target subset; return the accordion of solutions as an HTML fragment."""
    form = PlannerForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    targets, kwargs = _search_setup(request, form)
    # One accordion row per target subset, but only the best one arrives with its track:
    # the breakdown is 2^n rows, and a 100-row table apiece is hundreds of megabytes. The
    # rest fetch theirs from plan_row when opened.
    pulls = kwargs.pop("pulls")
    rerolls = kwargs.pop("rerolls")
    equivalents = kwargs.pop("equivalents")
    solutions = subset_solutions(pulls, rerolls, equivalents, targets, detail=1, **kwargs)

    return JsonResponse(
        {
            "solutions_html": render_to_string(
                "planner/_solutions.html",
                {
                    "solutions": solutions,
                    "target_total": len(targets),
                    "subset_limit": SUBSET_TARGET_LIMIT,
                    # The filter is dead weight over a handful of rows, so it ships only
                    # when the breakdown is big enough to need narrowing down.
                    "filter_cats": sorted(targets) if len(solutions) > PLAN_FILTER_ROWS else [],
                },
                request,
            ),
        }
    )


@require_POST
def plan_row(request):
    """One accordion row's body - its steps and highlighted track - solved when the row is
    opened. The same posted form the accordion came from, plus the row's own cats."""
    form = PlannerForm(request.POST)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    subset = {name for name in request.POST.getlist("subset") if name}
    if not subset:
        return HttpResponseBadRequest("subset must name at least one cat")

    _, kwargs = _search_setup(request, form)
    pulls = kwargs.pop("pulls")
    rerolls = kwargs.pop("rerolls")
    equivalents = kwargs.pop("equivalents")
    solution = subset_plan(pulls, rerolls, equivalents, subset, **kwargs)
    if solution is None:
        return HttpResponse("")

    return render(request, "planner/_solution_body.html", {"s": solution})


def unit_info(request):
    """A unit's forms, rarity and reference links, for the cat popup. Keyed by catalogue
    id where the caller knows it: names repeat across rarities (the Special and the Rare
    Cat Bros), so a name alone would always open the lower-id one. Roll cells carry only
    the base-form name, so that stays the fallback."""
    unit_id = request.GET.get("uid", "")
    lookup = {"unit_id": unit_id} if unit_id.isdigit() else {"name": request.GET.get("name", "")}
    unit = Unit.objects.filter(**lookup).first()
    if unit is None:
        return JsonResponse({"found": False})

    return JsonResponse(
        {
            "found": True,
            "unit_id": unit.unit_id,
            "name": unit.name,
            "rarity": unit.rarity,
            "forms": unit.forms,
            "links": [asdict(link) for link in unit_links(unit.unit_id, unit.name, unit.rarity)],
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
    """The cat dictionary in one page with the player's owned/wishlist marks, browsable
    by rarity or by gacha set. A unit can sit in several set sections (fests repeat their
    cats) - the marks are per unit, so every copy stays in step. Units this region's Cat
    Guide doesn't list are left out: the catalogue ships them, the region can't get them."""
    units = list(Unit.objects.named().in_guide())
    badges = tier_badges()
    # Each unit's chip is rendered once and reused: the page lays the whole catalogue out
    # three times over (dictionary, rarity, sets), and fests repeat their cats on top.
    chip = get_template("planner/_collection_chip.html")
    for unit in units:
        unit.tier_badge = badges.get(unit.unit_id)
        unit.chip = chip.render({"unit": unit})
    guide = load_guide()["regions"].get(active_region(), [])
    context = {
        # All views share the section partial, so a rarity bin becomes a one-row section.
        "dict_sections": [(r, "", [(r, bin)]) for r, bin in dictionary_sections(units, guide)],
        "rarity_sections": [(r, "", [(r, bin)]) for r, bin in collection_sections(units)],
        "facets": collection_facets(),
        "filter_targets": TARGET_LABELS,
        "filter_attack": ATTACK_LABELS,
        "filter_abilities": ABILITY_LABELS,
        "filter_immune": IMMUNITY_LABELS,
        "combo_groups": combo_filter_groups(),
        "set_sections": [
            (label, SECTION_NOTES.get(label, ""), rarities)
            for label, rarities in set_sections(units)
        ],
    }

    return render(request, "planner/collection.html", context)


def tier_list(request, category="", name=""):
    """A tier list, tier by tier, with catalogue names and icons: the cumulative uber
    ranking by default, or the per-set list the slug names."""
    doc = load_tiers()
    shown = doc if not category else tier_list_doc(f"{category}/{name}", doc)
    if shown is None:
        raise Http404(f"No tier list at {category}/{name}.")

    rows = tier_list_rows(shown)
    # The form picker renames entries client-side; ship each unit's form names along.
    forms = dict(Unit.objects.values_list("unit_id", "forms"))
    for row in rows:
        for entry in row["entries"]:
            entry["forms"] = "|".join(forms.get(entry["unit_id"], []))
    context = {
        "rows": rows,
        "source": shown["source"],
        "fetched": shown["fetched"],
        "label": shown.get("label", ""),
        "slug": f"{category}/{name}" if category else "",
        "index": tier_list_index(doc),
    }

    return render(request, "planner/tiers.html", context)


def about(request):
    """Static "about" page: what the tool is, who built it, and what's credited."""
    return render(request, "planner/about.html", {"tool_directory": TOOL_DIRECTORY})


@require_POST
def set_region(request):
    """Switch the game version the whole site shows. Each version ships its own
    catalogue, schedule and pools, and keeps its own collection - so this is a data
    switch, not a display language."""
    code = request.POST.get("region", "")
    if code not in CODES:
        return HttpResponseBadRequest("unknown region")

    Region.store(code)
    back = request.META.get("HTTP_REFERER", "")
    allowed = url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    )

    return redirect(back if allowed else reverse("planner"))


@require_POST
def apply_plan(request):
    """Mark the cats a plan gets you as owned. The wishlist mark is left as-is - getting a
    cat doesn't un-want it (an owned cat is already excluded from wishlist searches), so the
    star stays for when you browse your collection. Applying means "you rolled it", so the
    plan's seed-after becomes the stored seed."""
    names = request.POST.getlist("cats")
    applied = Unit.objects.filter(name__in=names).update(owned=True)

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


def resources(request):
    """The resources page: one board holding the cats you're grinding for, the Cat Base
    developments you're levelling, and the overview totalling both. The two pickers are
    rendered client-side from these static catalogues, so the board can be swapped whole
    on every change without re-shipping them."""
    context = {
        "board": resources_board(),
        "cat_options": cat_options(),
    }

    return render(request, "planner/resources.html", context)


def _board(request):
    return render(request, "planner/_res_board.html", {"board": resources_board()})


def _plan_unit(request):
    """The catalogued unit a resources POST names, or None when malformed/unknown."""
    try:
        unit_id = int(request.POST.get("unit_id", ""))
    except ValueError:
        return None

    return Unit.objects.filter(unit_id=unit_id).first()


def _set_talents(unit, slots, on):
    """Tick or clear every one of a unit's talent slots at once."""
    TalentPlan.objects.filter(unit=unit).delete()
    if on:
        TalentPlan.objects.bulk_create(TalentPlan(unit=unit, slot=index) for index in slots)


@require_POST
def resources_cat(request):
    """Put a cat on the list, tick one of its evolutions or talents, max it out, or drop
    it; responds with the whole re-rendered board.

    A bare unit_id just adds the cat - nothing is ticked for you, since what you want off
    a cat is the whole question the page asks."""
    unit = _plan_unit(request)
    if unit is None:
        return HttpResponseBadRequest("unknown unit")

    if request.POST.get("remove") == "1":
        UnitPlan.objects.filter(unit=unit).delete()
        TalentPlan.objects.filter(unit=unit).delete()
        return _board(request)

    plan, _ = UnitPlan.objects.get_or_create(unit=unit)
    slots = load_talents()["units"].get(str(unit.unit_id), [])
    cost = load_evolve()["units"].get(str(unit.unit_id), {})
    form, raw_slot = request.POST.get("form"), request.POST.get("slot")
    on = request.POST.get("on") == "1"
    if request.POST.get("all") is not None:
        plan.tf = on and plannable_form(cost, "tf") is not None
        plan.uf = on and plannable_form(cost, "uf") is not None
        plan.save()
        _set_talents(unit, range(len(slots)), on)
    elif form is not None:
        if form not in {"tf", "uf"}:
            return HttpResponseBadRequest("form must be 'tf' or 'uf'")
        setattr(plan, form, on)
        plan.save()
    elif raw_slot is not None:
        try:
            slot = int(raw_slot)
        except ValueError:
            return HttpResponseBadRequest("malformed slot")
        if not 0 <= slot < len(slots):
            return HttpResponseBadRequest("unknown slot")
        if on:
            TalentPlan.objects.get_or_create(unit=unit, slot=slot)
        else:
            TalentPlan.objects.filter(unit=unit, slot=slot).delete()

    return _board(request)


@require_POST
def resources_base(request):
    """Track a Cat Base development, switch one of its add-ons on or off, set a part to
    the level it sits at now, or drop it; responds with the whole re-rendered board.

    A bare cannon_id toggles the development itself - the picker is a row of switches,
    so the same click that adds one takes it back off."""
    raw_id = request.POST.get("cannon_id", "")
    cannon = next((c for c in load_cannons()["cannons"] if str(c["id"]) == raw_id), None)
    if cannon is None:
        return HttpResponseBadRequest("unknown cannon")

    part = request.POST.get("part")
    if part is None:
        deleted, _ = CannonPlan.objects.filter(cannon_id=cannon["id"]).delete()
        if not deleted:
            CannonPlan.objects.create(cannon_id=cannon["id"])
        return _board(request)

    if part not in cannon["parts"]:
        return HttpResponseBadRequest("unknown part")

    on = request.POST.get("on")
    if on is not None:
        if part not in CANNON_ADDONS:
            return HttpResponseBadRequest("the cannon comes with the development")
        CannonPlan.objects.update_or_create(
            cannon_id=cannon["id"], defaults={f"{part}_on": on == "1"}
        )
        return _board(request)

    try:
        level = int(request.POST.get("level", ""))
    except ValueError:
        return HttpResponseBadRequest("malformed level")
    if not 0 <= level <= len(cannon["parts"][part]["levels"]):
        return HttpResponseBadRequest("unknown level")
    CannonPlan.objects.update_or_create(cannon_id=cannon["id"], defaults={f"{part}_now": level})

    return _board(request)


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
