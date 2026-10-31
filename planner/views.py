import json
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.views import LoginView, RedirectURLMixin
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template, render_to_string
from django.urls import Resolver404, resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language, gettext
from django.views.decorators.http import require_POST
from django.views.generic import FormView

from neko.gamedata import load_cannons, load_evolve, load_talents
from neko.guidedata import load_guide
from neko.models import CATFOOD_PER_DRAW, GACHA_RARITIES, Rarity, is_future_uber
from neko.normal import BANNERS_BY_KEY, NORMAL_BANNERS
from neko.region import CODES
from neko.region import current as active_region
from neko.rng import backtrack
from neko.roller import DEFAULT_COUNT, GUARANTEED_OPTIONS, prepare_active, prepare_selected
from neko.seekspec import MAX_MATCHES, normal_spec, seed_spec
from neko.statsdata import ABILITY_LABELS, ATTACK_LABELS, IMMUNITY_LABELS, TARGET_LABELS
from neko.tierdata import load_tiers
from planner.changelog import CHANGES
from planner.forms import (
    MAX_FUTURE_UBERS,
    MAX_SEEK_ROLLS,
    MAX_TRACK_LENGTH,
    MIN_SEEK_ROLLS,
    PlannerForm,
)
from planner.labels import stat_forms
from planner.links import TOOL_DIRECTORY, unit_links
from planner.middleware import adopt_guest, owner, region_path, split_region
from planner.models import CannonPlan, Cat, Seed, TalentPlan, Unit, UnitPlan
from planner.seo import (
    BRAND,
    GUIDES,
    INDEXED_PAGES,
    REGION_PAGES,
    breadcrumbs,
    ld_json,
    tier_set_meta,
)
from planner.services import (
    ALPHA_LABEL,
    CANNON_ADDONS,
    GUIDE_PAGE_CELLS,
    NORMAL_DEFAULT_KEYS,
    NORMAL_MOVES,
    NORMAL_TARGET_PRESETS,
    PLAN_FILTER_ROWS,
    RARITY_ORDER,
    SUBSET_TARGET_LIMIT,
    apply_guide,
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
    guide_pages,
    import_collection,
    live_run_debuts,
    normal_banner_choices,
    normal_budgets,
    normal_item_options,
    normal_plan_targets,
    normal_request,
    normal_seek_banner,
    normal_seek_pools,
    picker_groups,
    plan_request,
    plannable_form,
    read_guide,
    resources_board,
    section_notes,
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
    tier_set_label,
    trace_marks,
    tracks_request,
    unit_stats,
)


def _picker_cats(profile):
    """Cats for the target picker, each carrying the player's owned/wanted marks, its tier
    badge (if the tier list ranks it) and its rendered chip. select_related("unit"): the
    badge reads cat.unit, one query per chip otherwise. Banner membership comes separately,
    via cat_banner_names.

    The chip is rendered here, once per cat, because the picker repeats it on every banner
    row that carries the cat - ~20k chips over ~500 cats, and rendering per appearance was
    most of the Past fragment's cost."""
    cats = list(Cat.objects.select_related("unit"))
    owned, wanted = profile.marks()
    badges = tier_badges()
    chip = get_template("planner/_picker_chip.html")
    for cat in cats:
        cat.owned, cat.wanted = cat.unit_id in owned, cat.unit_id in wanted
        cat.tier_badge = badges.get(cat.unit.unit_id) if cat.unit else None
        cat.chip = chip.render({"cat": cat})

    return cats


def planner(request):
    """The planner shell: the form plus empty hosts that JS fills with tracks/plan.

    The Past picker group is ~2000 per-run rows (nearly all of the page's bytes and
    render time), so it ships as a count only; JS fetches picker_past on first open.
    """
    cats = _picker_cats(request.profile)
    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    target_flat = sorted(cats, key=lambda cat: (-rank.get(cat.rarity, -1), cat.name))

    groups, past_count = [], 0
    for label, rows in picker_groups(
        cats, titles=banner_titles(), banner_names=cat_banner_names(), debuts=live_run_debuts()
    ):
        if label == "Past":
            past_count = len(rows)
            groups.append((label, None))  # rendered as a lazy shell in its place
        else:
            groups.append((label, rows))

    saved = Seed.saved(request.profile)
    context = {
        "form": PlannerForm(initial={"seed": saved.value} if saved else None),
        "saved_seed": saved,
        "target_groups": groups,
        "past_count": past_count,
        "target_flat": target_flat,
    }

    return render(request, "planner/planner.html", context)


def picker_past(request):
    """The Past picker rows, fetched when the group is first opened."""
    groups = dict(
        picker_groups(
            _picker_cats(request.profile), titles=banner_titles(), banner_names=cat_banner_names()
        )
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


@require_POST
def save_seed(request):
    """Store the seed the page is on, as the player's own: the rare one (``kind=rare``) or
    the Normal Capsules one. Pages call this on every change, so the seed lives with the
    profile - not only in one browser's storage."""
    kind = request.POST.get("kind", Seed.RARE)
    if kind not in {Seed.RARE, Seed.NORMAL}:
        return HttpResponseBadRequest("kind must be 'rare' or 'normal'")
    try:
        value = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponseBadRequest("seed must be an integer")
    if not 0 <= value < 2**32:
        return HttpResponseBadRequest("seed must be between 0 and 4294967295")

    last = request.POST.get("last", "")[:100]
    Seed.store(owner(request), value, kind, last)

    return JsonResponse({"seed": value, "account": request.user.is_authenticated})


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


def _owned_names(profile):
    """Cat names you already own, to flag Uber/Legend cats missing from your collection."""
    return set(profile.units("owned").values_list("name", flat=True))


def _wanted_names(profile):
    """Cat names on your wishlist, starred in the track and steps."""
    return set(profile.wishlist().values_list("name", flat=True))


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
        wishlist = dict(request.profile.wishlist().values_list("name", "rarity"))
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


@dataclass(frozen=True)
class _TracksPost:
    """One Rolls-table POST, read once for the server-rendered table and the engine
    request alike. ``last_cat`` is the dupe memory: the cat the previous pull got (a dice
    jump, an applied plan, or a seed you came back to) - it can dupe the very first cell.
    ``targets`` folds the toggled future ubers in as explicit uber picks."""

    seed: int
    banners: list[str]
    last_cat: str
    display: int
    future_ubers: dict[str, int]
    simulate_guaranteed: int
    trace: tuple | None
    targets: dict[str, str]
    wishlist: dict[str, str]
    pks: dict[str, int]
    include_guaranteed: bool


def _tracks_post(request):
    """The posted Rolls-table inputs, or None when the seed isn't a number."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return None

    targets, wishlist, pks = _find_targets(request)
    # A toggled future uber searches like an explicit pick (its qualified name is already in
    # the padded pool), so fold it into the target map at uber rarity.
    future = {name: str(Rarity.UBER_SUPER_RARE) for name in _future_targets(request)}

    return _TracksPost(
        seed=seed,
        banners=request.POST.getlist("banners"),
        last_cat=request.POST.get("last_cat", "").strip(),
        display=_track_length(request),
        future_ubers=_future_ubers(request),
        simulate_guaranteed=_simulate_guaranteed(request),
        trace=_trace(request),
        targets={**targets, **future},
        wishlist=wishlist,
        pks=pks,
        include_guaranteed=request.POST.get("exclude_guaranteed") != "1",
    )


@require_POST
def tracks_engine(request):
    """The Rolls table as a request for the page's own engine (neko.wasm) to roll and
    render - the same POST ``tracks`` takes, with none of its rolling done here."""
    post = _tracks_post(request)
    if post is None:
        return HttpResponseBadRequest("the seed must be a number")

    options = {"simulate_guaranteed": post.simulate_guaranteed, "future_ubers": post.future_ubers}
    prepared = (
        prepare_selected(post.banners, **options) if post.banners else prepare_active(**options)
    )

    return JsonResponse(
        tracks_request(
            post.seed,
            prepared,
            max(post.display, MAX_TRACK_LENGTH),
            post.last_cat,
            rows=post.display,
            owned=_owned_names(request.profile),
            wanted=_wanted_names(request.profile),
            unit_ids=_unit_ids(),
            tiers=tier_badges(),
            titles=display_titles(),
            debuts=banner_debuts(),
            future=post.future_ubers,
            targets=post.targets,
            wishlist=post.wishlist,
            pks=post.pks,
            include_guaranteed=post.include_guaranteed,
            trace=post.trace,
        )
    )


@require_POST
def tracks(request):
    """A/B track tables for the current seed + banners, before any plan is run."""
    post = _tracks_post(request)
    if post is None:
        return HttpResponse("")

    seed, last_cat, display, future_ubers = (
        post.seed,
        post.last_cat,
        post.display,
        post.future_ubers,
    )
    # Roll the find window deep (godfat's Find ceiling): the "Find next" panel locates cats
    # far past the visible table, but only ``display`` rows render (build_tracks caps them).
    count = max(display, MAX_TRACK_LENGTH)
    result = _roll(
        seed,
        post.banners,
        count,
        last_cat,
        simulate_guaranteed=post.simulate_guaranteed,
        future_ubers=future_ubers,
    )
    equivalents = equivalent_banners(result.banners)
    pulls, guaranteed, rerolls, guaranteed_rerolls = _rolls_by_banner(result)
    trace = post.trace
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
    owned, wanted = _owned_names(request.profile), _wanted_names(request.profile)
    titles = display_titles()
    # The unified targets panel (godfat's Find, enriched): every cat you're searching for -
    # picks, wishlist and toggled future ubers - with its next position or a ⚠. Attached to
    # the browse track only, so the shared _tracks.html renders no panel on plan tracks.
    targets, wishlist, pks = post.targets, post.wishlist, post.pks
    # Scope the wishlist search to what these banners can actually drop (their unioned pools),
    # so "search my wishlist" lists only obtainable cats, not every unowned cat you want.
    obtainable = frozenset().union(*result.pools.values()) if result.pools else None
    found_cats = find_cats(
        pulls,
        targets,
        guaranteed=guaranteed,
        include_guaranteed=post.include_guaranteed,
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


@dataclass(frozen=True)
class _PlanSetup:
    """What a plan search reads off one posted form, before any rolling: the selected
    banners (unrolled), the rows to roll, the scoped targets and the budget."""

    seed: int
    banners: list[str]
    prepared: dict
    count: int
    last_cat: str
    future_ubers: dict[str, int]
    picked: set[str]
    future_targets: set[str]
    tickets: int
    catfood: int
    platinum: int
    legend: int
    ticket_value: int

    def targets(self, pools) -> set[str]:
        """The targets scoped to what these banners can actually drop (their unioned
        ``pools``), the same rule the panel uses: a picked or wishlisted cat that isn't in
        them is dropped rather than listed as a dead "Not found" row (a whole wishlist
        against one banner). Future-uber placeholders are always in their padded pool."""
        pools = list(pools)
        scoped = self.picked & frozenset().union(*pools) if pools else set(self.picked)
        return scoped | self.future_targets


def _plan_setup(request, form):
    seed = form.cleaned_data["seed"]
    targets = {cat.name for cat in form.cleaned_data["targets"]}
    if form.cleaned_data["use_wishlist"]:
        targets |= _wanted_names(request.profile)
    # Future-uber targets are qualified placeholders, searchable only once the pool is
    # padded - so the plan must roll WITH that padding, and the target set keeps them even
    # though they're absent from the real (unpadded) pool the scoping below prunes against.
    future_targets = set(form.cleaned_data["future_targets"])
    future_ubers = _future_ubers(request)

    explore = form.cleaned_data["explore"]
    banners = request.POST.getlist("banners")
    prepare = prepare_selected if banners else prepare_active
    prepared = prepare(*([banners] if banners else []), future_ubers=future_ubers)

    if explore:
        # Ignore the budget but still fund single pulls with tickets (their real
        # currency) so an all-singles plan reads "8 tickets", not "1200 catfood".
        horizon = form.cleaned_data["horizon"]
        tickets, catfood = horizon, horizon * CATFOOD_PER_DRAW
    else:
        tickets, catfood = form.cleaned_data["tickets"], form.cleaned_data["catfood"]

    return _PlanSetup(
        seed=seed,
        banners=banners,
        prepared=prepared,
        count=form.cleaned_data["horizon"] if explore else DEFAULT_COUNT,
        last_cat=request.POST.get("last_cat", "").strip(),
        future_ubers=future_ubers,
        picked=targets,
        future_targets=future_targets,
        tickets=tickets,
        catfood=catfood,
        # Platinum/Legend Capsules always run on their own scarce ticket pools, so their counts
        # come straight from the form even in explore mode (which frees only rare/catfood).
        platinum=form.cleaned_data["platinum_cap"],
        legend=form.cleaned_data["legend_cap"],
        ticket_value=form.cleaned_data["ticket_value"],
    )


def _plan_engine_request(request, setup, op, **extra):
    """A plan search for the page's engine to run (neko.wasm) - the same search, nothing
    rolled or solved here."""
    return plan_request(
        op,
        setup.seed,
        setup.prepared,
        setup.count,
        setup.last_cat,
        targets=setup.targets(run.pool for run in setup.prepared.values()),
        tickets=setup.tickets,
        catfood=setup.catfood,
        platinum=setup.platinum,
        legend=setup.legend,
        ticket_value=setup.ticket_value,
        owned=_owned_names(request.profile),
        wanted=_wanted_names(request.profile),
        unit_ids=_unit_ids(),
        tiers=tier_badges(),
        titles=display_titles(),
        debuts=banner_debuts(),
        apply_url=reverse("apply_plan"),
        row_url=reverse("plan_row"),
        **extra,
    )


@require_POST
def find_plan_engine(request):
    """find_plan for the page's engine: every target subset's plan, as a request the
    page solves and renders itself."""
    form = PlannerForm(request.POST, profile=request.profile)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    return JsonResponse(
        _plan_engine_request(request, _plan_setup(request, form), "solutions", detail=1)
    )


@require_POST
def plan_row_engine(request):
    """plan_row for the page's engine: one opened row's subset, as a request."""
    form = PlannerForm(request.POST, profile=request.profile)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    subset = {name for name in request.POST.getlist("subset") if name}
    if not subset:
        return HttpResponseBadRequest("subset must name at least one cat")

    setup = _plan_setup(request, form)
    return JsonResponse(_plan_engine_request(request, setup, "plan_row", subset=subset))


def _search_setup(request, form):
    """Everything both reference plan views need from one posted form: the scoped target
    set and the keyword arguments the solvers take. Returns ``(targets, kwargs)``."""
    setup = _plan_setup(request, form)
    result = _roll(
        setup.seed, setup.banners, setup.count, setup.last_cat, future_ubers=setup.future_ubers
    )
    targets, last_cat = setup.targets(result.pools.values()), setup.last_cat
    tickets, catfood = setup.tickets, setup.catfood
    pulls, guaranteed_pulls, rerolls, guaranteed_rerolls = _rolls_by_banner(result)

    kwargs = dict(
        pulls=pulls,
        rerolls=rerolls,
        equivalents=equivalent_banners(result.banners),
        tickets=tickets,
        catfood=catfood,
        platinum=setup.platinum,
        legend=setup.legend,
        guaranteed_pulls=guaranteed_pulls,
        multis=result.multis,
        ticket_value=setup.ticket_value,
        banner_currency=banner_currencies(pulls),
        owned=_owned_names(request.profile),
        wanted=_wanted_names(request.profile),
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
    form = PlannerForm(request.POST, profile=request.profile)
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
    form = PlannerForm(request.POST, profile=request.profile)
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

    stats = unit_stats(unit.unit_id)
    if stats:
        stats = {**stats, "forms": stat_forms(stats["forms"])}

    return JsonResponse(
        {
            "found": True,
            "unit_id": unit.unit_id,
            "name": unit.name,
            "rarity": unit.rarity,
            "rarity_label": gettext(unit.rarity) if unit.rarity else "",
            "forms": unit.forms,
            "links": [asdict(link) for link in unit_links(unit.unit_id, unit.name, unit.rarity)],
            "tier": tier_badges().get(unit.unit_id),
            "stats": stats,
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
        return HttpResponseBadRequest(gettext("unknown banner"))

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
    """Validate the posted banner + observed rolls and hand back the seed search for the
    page to run."""
    banner = seek_banner(request.POST.get("banner", ""))
    if banner is None:
        return HttpResponseBadRequest(gettext("unknown banner"))

    observed = _observed_rolls(request, banner)
    if observed is None:
        return HttpResponseBadRequest(gettext("malformed rolls"))
    if not MIN_SEEK_ROLLS <= len(observed) <= MAX_SEEK_ROLLS:
        return HttpResponseBadRequest(
            gettext("enter between %(min)s and %(max)s rolls")
            % {"min": MIN_SEEK_ROLLS, "max": MAX_SEEK_ROLLS}
        )

    rarity, slot = observed[-1]

    return _search(seed_spec(banner, observed), banner.pool(rarity)[slot])


def _search(spec, last_cat):
    """The search the page runs itself (neko.wasm on every core) for a validated window,
    plus the last pull's name - the found seed's dupe memory."""
    return JsonResponse(
        {
            "cats": spec.cats,
            "bands": spec.bands,
            "sizes": spec.sizes,
            "rerollable": sorted(spec.rerollable),
            "limit": MAX_MATCHES,
            "last_cat": last_cat,
        }
    )


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
            "saved_seed": Seed.saved(request.profile, Seed.NORMAL),
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


@require_POST
def normal_tracks_engine(request):
    """normal_tracks for the page's engine: the machines' bands and the seed, as a request
    the page rolls and renders itself."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponseBadRequest("seed must be an integer")

    return JsonResponse(
        normal_request(
            "normal_tracks",
            seed,
            request.POST.getlist("banners"),
            _track_length(request),
            request.POST.get("last_item", "").strip(),
        )
    )


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


def _normal_moves(request):
    """The posted stash the plan's walking pulls come out of (NORMAL_MOVES)."""
    moves = request.POST.get("moves", "")
    return moves if moves in NORMAL_MOVES else "lucky"


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
        return HttpResponseBadRequest(gettext("give some tickets to at least one shown machine"))

    plan = build_normal_plan(
        seed,
        machines,
        tickets,
        request.POST.get("target", "dark"),
        _track_length(request),
        last_item=request.POST.get("last_item", "").strip(),
        moves=_normal_moves(request),
    )
    if plan is None:
        return HttpResponseBadRequest(gettext("unknown target"))

    return render(request, "planner/_normal_plan.html", {"plan": plan, "track": plan["track"]})


@require_POST
def normal_plan_engine(request):
    """normal_plan for the page's engine: the search's machines, budgets and target, as a
    request the page solves and renders itself."""
    try:
        seed = int(request.POST.get("seed", ""))
    except ValueError:
        return HttpResponseBadRequest("seed must be an integer")

    tickets = _normal_tickets(request)
    machines = [key for key in request.POST.getlist("banners") if key in BANNERS_BY_KEY]
    if not tickets or not machines:
        return HttpResponseBadRequest(gettext("give some tickets to at least one shown machine"))

    resolved = normal_plan_targets(request.POST.get("target", "dark"))
    if resolved is None:
        return HttpResponseBadRequest(gettext("unknown target"))

    label, targets = resolved
    # The table shows the live machines in the page's fixed order, plus any lucky one your
    # stash brings in once the plan pulls it; the search tries them in the order posted, as
    # the server's planner did.
    budgets = normal_budgets(machines, tickets, _normal_moves(request))
    fed = {key for _, keys in budgets for key in keys}
    columns = [
        banner.key for banner in NORMAL_BANNERS if banner.key in machines or banner.key in fed
    ]
    return JsonResponse(
        normal_request(
            "normal_plan",
            seed,
            columns,
            _track_length(request),
            request.POST.get("last_item", "").strip(),
            label=label,
            targets=targets,
            budgets=budgets,
            optional=[key for key in columns if key not in machines],
        )
    )


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
    """seek_start for the normal seed: validate the posted rolls, hand back the search."""
    banner = normal_seek_banner(request.POST.get("banner", ""))
    if banner is None:
        return HttpResponseBadRequest(gettext("unknown banner"))

    observed = _observed_normal_rolls(request, banner)
    if observed is None:
        return HttpResponseBadRequest(gettext("malformed rolls"))
    if not MIN_SEEK_ROLLS <= len(observed) <= MAX_SEEK_ROLLS:
        return HttpResponseBadRequest(
            gettext("enter between %(min)s and %(max)s rolls")
            % {"min": MIN_SEEK_ROLLS, "max": MAX_SEEK_ROLLS}
        )

    pool, slot = observed[-1]

    return _search(normal_spec(banner, observed), banner.pools[pool].items[slot])


def collection(request):
    """The cat dictionary in one page with the player's owned/wishlist marks, browsable
    by rarity or by gacha set. A unit can sit in several set sections (fests repeat their
    cats) - the marks are per unit, so every copy stays in step. Units this region's Cat
    Guide doesn't list are left out: the catalogue ships them, the region can't get them."""
    units = list(Unit.objects.named().in_guide())
    owned, wanted = request.profile.marks()
    badges = tier_badges()
    # Each unit's chip is rendered once and reused: the page lays the whole catalogue out
    # three times over (dictionary, rarity, sets), and fests repeat their cats on top.
    chip = get_template("planner/_collection_chip.html")
    for unit in units:
        unit.owned, unit.wanted = unit.pk in owned, unit.pk in wanted
        unit.tier_badge = badges.get(unit.unit_id)
        unit.chip = chip.render({"unit": unit})
    guide = load_guide()["regions"].get(active_region(), [])
    notes = section_notes()
    context = {
        # All views share the section partial, so a rarity bin becomes a one-row section.
        "dict_sections": [(r, "", [(r, bin)]) for r, bin in dictionary_sections(units, guide)],
        "rarity_sections": [(r, "", [(r, bin)]) for r, bin in collection_sections(units)],
        "set_sections": [
            (label, notes.get(label, ""), rarities) for label, rarities in set_sections(units)
        ],
        # One row with no rarity; app.js re-sorts it by the form the picker shows.
        "alpha_sections": [(ALPHA_LABEL, "", [("", sorted(units, key=lambda unit: unit.name))])]
        if units
        else [],
        **_cat_filters(units),
    }

    return render(request, "planner/collection.html", context)


def _cat_filters(units) -> dict:
    """The context _cat_filters.html renders: the rarities present, the facet pills and
    the per-unit facet data they test."""
    return {
        "filter_rarities": [rarity for rarity, _ in collection_sections(units)],
        "facets": collection_facets(),
        "filter_targets": TARGET_LABELS,
        "filter_attack": ATTACK_LABELS,
        "filter_abilities": ABILITY_LABELS,
        "filter_immune": IMMUNITY_LABELS,
        "combo_groups": combo_filter_groups(),
    }


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
        "label": tier_set_label(shown) if category else "",
        "slug": f"{category}/{name}" if category else "",
        "index": tier_list_index(doc),
    }
    if category:
        context["page_meta"] = tier_set_meta(context["label"])
        context["structured_data"] = ld_json(
            breadcrumbs(
                (BRAND, reverse("planner")),
                ("Tier List", reverse("tier_list")),
                (context["label"], request.path),
            )
        )

    return render(request, "planner/tiers.html", context)


def whats_new(request):
    """What's changed lately, newest first."""
    return render(request, "planner/whats_new.html", {"changes": CHANGES})


def _localized(name: str) -> list[str]:
    """A long-form page's template in the interface language, English as the fallback:
    prose reads better written whole than stitched from translated fragments."""
    return [f"planner/{get_language()}/{name}", f"planner/{name}"]


def _guide_links() -> list[tuple[str, str, str]]:
    """Each guide as (slug, heading, summary), in reading order."""
    return [(slug, meta.name, meta.description) for slug, meta in GUIDES.items()]


def guides(request):
    """The how-to guides, listed."""
    return render(request, "planner/guides.html", {"guides": _guide_links()})


def guide(request, slug):
    """One how-to guide, with the others linked at its foot."""
    meta = GUIDES.get(slug)
    if meta is None:
        raise Http404("no such guide")

    links = _guide_links()
    heading = str(next(name for key, name, _ in links if key == slug))
    context = {
        "heading": heading,
        "page_meta": meta,
        "others": [link for link in links if link[0] != slug],
        "structured_data": ld_json(
            breadcrumbs(
                (BRAND, reverse("planner")),
                ("Guides", reverse("guides")),
                (heading, request.path),
            )
        ),
    }

    return render(request, _localized(f"guides/{slug}.html"), context)


def sitemap_pages() -> list[dict]:
    """Every page worth a search listing, at every game version's URL: the tools, the
    guides and each gacha set's tier list."""
    pages = [{"loc": reverse(name)} for name in INDEXED_PAGES if name not in REGION_PAGES]
    regional = [{"loc": reverse(name)} for name in INDEXED_PAGES if name in REGION_PAGES]
    regional += [{"loc": reverse("guide", args=[slug])} for slug in GUIDES]
    regional += [
        {
            "loc": reverse("tier_list_page", args=entry["slug"].split("/")),
            "lastmod": entry["fetched"],
        }
        for _, entries in tier_list_index(load_tiers())
        for entry in entries
    ]
    pages += [
        {**page, "loc": region_path(page["loc"], code)} for code in CODES for page in regional
    ]

    return pages


def sitemap(request):
    """The sitemap: every listed page under the public site URL."""
    context = {"site_url": settings.SITE_URL, "pages": sitemap_pages()}

    return render(request, "planner/sitemap.xml", context, content_type="application/xml")


def robots(request):
    """Crawl everything but the admin, and say where the sitemap is."""
    sitemap_url = f"{settings.SITE_URL}{reverse('sitemap')}"
    body = f"User-agent: *\nDisallow: /admin/\n\nSitemap: {sitemap_url}\n"

    return HttpResponse(body, content_type="text/plain")


def indexnow_key(request, key):
    """IndexNow's ownership proof: the key, served at /<key>.txt and nowhere else."""
    if not settings.INDEXNOW_KEY or key != settings.INDEXNOW_KEY:
        raise Http404

    return HttpResponse(key, content_type="text/plain")


def about(request):
    """Static "about" page: what the tool is, who built it, and what's credited."""
    return render(request, _localized("about.html"), {"tool_directory": TOOL_DIRECTORY})


class Signup(RedirectURLMixin, FormView):
    """Create an account. The visitor's guest profile - collection, plans, seed - becomes
    the account's, so signing up never starts them over."""

    form_class = UserCreationForm
    template_name = "planner/account.html"
    next_page = "planner"
    extra_context = {"signup": True}

    def form_valid(self, form):
        user = form.save()
        adopt_guest(self.request, user)
        login(self.request, user)

        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        return super().get_context_data(next=self.get_redirect_url(), **kwargs)


class Login(LoginView):
    """Log in. An account with no profile yet takes over the visitor's guest one."""

    template_name = "planner/account.html"

    def form_valid(self, form):
        adopt_guest(self.request, form.get_user())

        return super().form_valid(form)


@login_required
def avatar(request):
    """Pick the header's picture: any cat, in any of its forms. The catalogue rides in the
    page, A-Z, for its search and the Collection's filters; a pick posts "<unit id>/<form>"."""
    profile = owner(request)
    if request.method == "POST":
        unit_id, _, form = request.POST.get("avatar", "").partition("/")
        unit = Unit.objects.filter(unit_id=unit_id).first() if unit_id.isdigit() else None
        if unit is None or not form.isdigit() or int(form) >= max(len(unit.forms), 1):
            return HttpResponseBadRequest("Pick a cat and one of its forms.")

        profile.avatar_unit, profile.avatar_form = unit.unit_id, int(form)
        profile.save(update_fields=["avatar_unit", "avatar_form"])
        return redirect("avatar")

    units = list(Unit.objects.named().order_by("name"))
    owned, wanted = profile.marks()
    cats = [
        {
            "id": unit.unit_id,
            "name": unit.name,
            "forms": unit.forms,
            "rarity": unit.rarity or "Unknown",
            "owned": unit.pk in owned,
            "wanted": unit.pk in wanted,
        }
        for unit in units
    ]

    return render(request, "planner/avatar.html", {"cats": cats, **_cat_filters(units)})


def _posted_from(request, code: str) -> str:
    """The page a post was made from, at ``code``'s version of it, as a URL this site
    generated for itself.

    The Referer header is attacker-controllable, so it never becomes the redirect target:
    it only picks one of our own routes. Off-site or wrong-scheme referers are rejected,
    the path is resolved against our own URLconf, and what we hand back is reverse()'s
    output for the view that matched - so the destination is ours by construction, not by
    inspection. Only the query string rides along, which cannot change where it points.
    Anything that doesn't resolve lands on the planner."""
    home = region_path(reverse("planner"), code)
    back = request.META.get("HTTP_REFERER", "")
    if not url_has_allowed_host_and_scheme(
        back, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return home

    parts = urlsplit(back)
    try:
        match = resolve(split_region(parts.path)[1])
    except Resolver404:
        return home

    here = region_path(reverse(match.view_name, args=match.args, kwargs=match.kwargs), code)

    return f"{here}?{parts.query}" if parts.query else here


@require_POST
def set_language(request):
    """Pick the interface language for every page, or - blank - go back to each game
    version speaking its own. Lands back on the page it was posted from."""
    code = request.POST.get("language", "")
    if code and code not in dict(settings.LANGUAGES):
        return HttpResponseBadRequest("unknown language")

    response = redirect(_posted_from(request, request.region))
    if code:
        response.set_cookie(
            settings.LANGUAGE_COOKIE_NAME,
            code,
            max_age=settings.LANGUAGE_COOKIE_AGE,
            secure=settings.SESSION_COOKIE_SECURE,
            samesite="Lax",
        )
    else:
        response.delete_cookie(settings.LANGUAGE_COOKIE_NAME)

    return response


@require_POST
def set_region(request):
    """Switch the game version the whole site shows: back to the same page at that
    version's URL. Each version ships its own catalogue, schedule and pools, and keeps
    its own collection - so this is a data switch, not a display language."""
    code = request.POST.get("region", "")
    if code not in CODES:
        return HttpResponseBadRequest("unknown region")

    profile = owner(request)
    profile.region = code
    profile.save(update_fields=["region"])

    return redirect(_posted_from(request, code))


@require_POST
def apply_plan(request):
    """Mark the cats a plan gets you as owned. The wishlist mark is left as-is - getting a
    cat doesn't un-want it (an owned cat is already excluded from wishlist searches), so the
    star stays for when you browse your collection. The page moves the seed on itself
    (save_seed), along with the cat the plan's last pull got."""
    profile = owner(request)
    units = Unit.objects.filter(name__in=request.POST.getlist("cats"))
    profile.owned.add(*units)

    return JsonResponse({"applied": len(units)})


@require_POST
def collection_bulk(request):
    """Mark a whole section owned/wanted in one tap - or clear it when it's already all
    marked. Bulk wishlist stars owned units too, matching the per-cat star; the planner
    still ignores wishlisted cats you own (_wanted_names excludes owned)."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")

    profile = owner(request)
    units = Unit.objects.filter(pk__in=request.POST.getlist("pk"))
    value = units.exclude(**{f"{field}_by": profile}).exists()
    marked = getattr(profile, field)
    if value:
        marked.add(*units)
    else:
        marked.remove(*units)

    return JsonResponse({"value": value})


def resources(request):
    """The resources page: one board holding the cats you're grinding for, the Cat Base
    developments you're levelling, and the overview totalling both. The two pickers are
    rendered client-side from these static catalogues, so the board can be swapped whole
    on every change without re-shipping them."""
    context = {
        "board": resources_board(request.profile),
        "cat_options": cat_options(),
    }

    return render(request, "planner/resources.html", context)


def _board(request):
    return render(request, "planner/_res_board.html", {"board": resources_board(request.profile)})


def _plan_unit(request):
    """The catalogued unit a resources POST names, or None when malformed/unknown."""
    try:
        unit_id = int(request.POST.get("unit_id", ""))
    except ValueError:
        return None

    return Unit.objects.filter(unit_id=unit_id).first()


def _set_talents(profile, unit, slots, on):
    """Tick or clear every one of a unit's talent slots at once."""
    profile.talent_plans.filter(unit=unit).delete()
    if on:
        TalentPlan.objects.bulk_create(
            TalentPlan(profile=profile, unit=unit, slot=index) for index in slots
        )


@require_POST
def resources_cat(request):
    """Put a cat on the list, tick one of its evolutions or talents, max it out, or drop
    it; responds with the whole re-rendered board.

    A bare unit_id just adds the cat - nothing is ticked for you, since what you want off
    a cat is the whole question the page asks."""
    unit = _plan_unit(request)
    if unit is None:
        return HttpResponseBadRequest("unknown unit")

    profile = owner(request)
    if request.POST.get("remove") == "1":
        profile.unit_plans.filter(unit=unit).delete()
        profile.talent_plans.filter(unit=unit).delete()
        return _board(request)

    plan, _ = UnitPlan.objects.get_or_create(profile=profile, unit=unit)
    slots = load_talents()["units"].get(str(unit.unit_id), [])
    cost = load_evolve()["units"].get(str(unit.unit_id), {})
    form, raw_slot = request.POST.get("form"), request.POST.get("slot")
    on = request.POST.get("on") == "1"
    if request.POST.get("all") is not None:
        plan.tf = on and plannable_form(cost, "tf") is not None
        plan.uf = on and plannable_form(cost, "uf") is not None
        plan.save()
        _set_talents(profile, unit, range(len(slots)), on)
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
            TalentPlan.objects.get_or_create(profile=profile, unit=unit, slot=slot)
        else:
            profile.talent_plans.filter(unit=unit, slot=slot).delete()

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

    profile = owner(request)
    part = request.POST.get("part")
    if part is None:
        deleted, _ = profile.cannon_plans.filter(cannon_id=cannon["id"]).delete()
        if not deleted:
            CannonPlan.objects.create(profile=profile, cannon_id=cannon["id"])
        return _board(request)

    if part not in cannon["parts"]:
        return HttpResponseBadRequest("unknown part")

    on = request.POST.get("on")
    if on is not None:
        if part not in CANNON_ADDONS:
            return HttpResponseBadRequest("the cannon comes with the development")
        CannonPlan.objects.update_or_create(
            profile=profile, cannon_id=cannon["id"], defaults={f"{part}_on": on == "1"}
        )
        return _board(request)

    try:
        level = int(request.POST.get("level", ""))
    except ValueError:
        return HttpResponseBadRequest("malformed level")
    if not 0 <= level <= len(cannon["parts"][part]["levels"]):
        return HttpResponseBadRequest("unknown level")
    CannonPlan.objects.update_or_create(
        profile=profile, cannon_id=cannon["id"], defaults={f"{part}_now": level}
    )

    return _board(request)


@require_POST
def collection_toggle(request):
    """Set a single unit's owned/wanted flag to the posted value. The page has already
    shown the change, so a repeated or reordered request lands on the same state."""
    field = request.POST.get("field")
    if field not in {"owned", "wanted"}:
        return HttpResponseBadRequest("field must be 'owned' or 'wanted'")

    unit = get_object_or_404(Unit, pk=request.POST.get("pk"))
    marked = getattr(owner(request), field)
    if request.POST.get("on") == "1":
        marked.add(unit)
    else:
        marked.remove(unit)

    return HttpResponse(status=204)


@require_POST
def collection_auto_wishlist(request):
    """Turn auto-wishlisting of newly released gacha cats on or off."""
    profile = owner(request)
    profile.auto_wishlist = request.POST.get("on") == "1"
    profile.save(update_fields=["auto_wishlist"])

    return JsonResponse({"auto_wishlist": profile.auto_wishlist})


def collection_export(request):
    """Download the owned/wishlist marks as a JSON snapshot the player can back up or move
    to another install."""
    resp = JsonResponse(export_collection(request.profile), json_dumps_params={"indent": 2})
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
        result = import_collection(owner(request), data)
    except ValueError, TypeError:
        return HttpResponseBadRequest("not a Neko collection export")

    return JsonResponse(result)


MAX_GUIDE_SHOTS = 100  # a guide runs to ~35 pages; room for duplicates, not for abuse


def _guide_shots(raw):
    """The posted shots in read_guide's shape, or None when anything isn't the page
    reader's: a 0..1 position (null when not found), 24 marks, a ms timestamp."""
    if not isinstance(raw, list) or not 0 < len(raw) <= MAX_GUIDE_SHOTS:
        return None

    shots = []
    for shot in raw:
        if not isinstance(shot, dict):
            return None

        position, marks, taken = shot.get("position"), shot.get("marks"), shot.get("taken")
        number = (int, float)
        if position is not None and (
            isinstance(position, bool) or not isinstance(position, number) or not 0 <= position <= 1
        ):
            return None
        if marks is not None and (
            not isinstance(marks, str) or len(marks) != GUIDE_PAGE_CELLS or set(marks) - set("O?.")
        ):
            return None
        if isinstance(taken, bool) or not isinstance(taken, number):
            return None

        name = str(shot.get("name", ""))[:80]
        shots.append({"name": name, "position": position, "marks": marks, "taken": taken})

    return shots


@require_POST
def collection_guide_import(request):
    """Check Cat Guide screenshots - as the page's reader measured them - against our
    guide, and with ``apply`` set and nothing wrong, make the owned marks match them."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError, UnicodeDecodeError:
        return HttpResponseBadRequest("not JSON")

    shots = _guide_shots(data.get("shots") if isinstance(data, dict) else None)
    if shots is None:
        return HttpResponseBadRequest("malformed screenshots")

    units = list(Unit.objects.named().in_guide())
    pages = guide_pages(units, load_guide()["regions"].get(active_region(), []))
    result = read_guide(shots, pages)
    applied = bool(data.get("apply")) and not result.errors
    if applied:
        apply_guide(owner(request), result.owned, units)

    return JsonResponse(
        {
            "errors": result.errors,
            "owned": len(result.owned),
            "total": len(units),
            "applied": applied,
        }
    )
