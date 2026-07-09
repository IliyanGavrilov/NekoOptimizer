import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations
from urllib.parse import quote

from neko.catalogue import match_names, name_index
from neko.gachadata import GachaEventRow, load_events, load_pools, load_series, load_tickets
from neko.graph import BannerGraph, build_graphs, stream_index
from neko.models import (
    CATFOOD_PER_DRAW,
    BannerRolls,
    Leg,
    Path,
    Pull,
    Rarity,
    State,
    is_future_uber,
)
from neko.roller import (
    DEFAULT_COUNT,
    RollResult,
    catalogue_banners,
    roll_active,
    roll_selected,
    units_from_records,
)
from neko.search import astar, beam_search, obtainable
from neko.subsets import SubsetPlan, solve_subsets
from planner.models import Banner, Cat, Unit

RARITY_ORDER = ["Normal", "Special", "Rare", "Super Rare", "Uber Super Rare", "Legend Rare"]

WIKI_BASE = "https://battlecats.miraheze.org/wiki/"

# The wiki titles every cat page '{name} ({rarity} Cat)' and its rarity labels differ
# from the game's internal names (internal 'Uber Super Rare' -> wiki 'Uber Rare').
_WIKI_RARITY = {
    Rarity.NORMAL.value: "Normal Cat",
    Rarity.SPECIAL.value: "Special Cat",
    Rarity.RARE.value: "Rare Cat",
    Rarity.SUPER_RARE.value: "Super Rare Cat",
    Rarity.UBER_SUPER_RARE.value: "Uber Rare Cat",
    Rarity.LEGEND_RARE.value: "Legend Rare Cat",
}


def wiki_url(name: str, rarity: str = "") -> str:
    """The unit's Battle Cats Wiki (Miraheze) page URL; if the rarity is unknown it falls
    back to just the name, with no rarity in brackets."""
    label = _WIKI_RARITY.get(rarity)
    title = f"{name} ({label})" if label else name

    return WIKI_BASE + quote(title.replace(" ", "_"), safe="()'")


# Platinum/Legend run on scarce tickets, not catfood, so the optimizer treats them as
# info-only: capped (0 by default) rather than modelled as ordinary catfood gacha. Match
# the ticket-capsule PHRASE, not a bare "legend"/"platinum" - loads of ordinary banners
# (Evangelion's "Limited Legend", the fests' "Legend Rare drop rate") mention the word.
_CAPPED_KEYWORDS = ("platinum capsules", "legend capsules")


def capped_banner_limits(names: Iterable[str], cap: int) -> dict[str, int]:
    """Cap pulls on Platinum/Legend Capsule banners (matched by name) at `cap`."""
    return {name: cap for name in names if any(kw in name.lower() for kw in _CAPPED_KEYWORDS)}


def fetch_banners(
    seed: int,
    count: int = DEFAULT_COUNT,
    last_cat: str = "",
    simulate_guaranteed: int = 0,
    future_ubers: Mapping[str, int] | None = None,
) -> RollResult:
    """Roll the active banners for a seed locally (no godfat). ``last_cat`` is the pull
    you got just before this view (the dupe memory) - it can dupe a first cell.
    ``simulate_guaranteed`` (a roll count) forces a guaranteed column onto banners without
    one; ``future_ubers`` maps a banner name to how many unreleased placeholders pad ITS
    uber pool."""
    return roll_active(
        seed,
        count=count,
        last_cat=last_cat,
        simulate_guaranteed=simulate_guaranteed,
        future_ubers=future_ubers,
    )


def fetch_catalogue() -> RollResult:
    """Every scheduled banner's droppable cats, straight from the gacha pools."""
    return catalogue_banners()


def fetch_for_banners(
    seed: int,
    names: Iterable[str],
    count: int = DEFAULT_COUNT,
    last_cat: str = "",
    simulate_guaranteed: int = 0,
    future_ubers: Mapping[str, int] | None = None,
) -> RollResult:
    """Roll just the chosen banners for a seed locally. ``last_cat``,
    ``simulate_guaranteed`` and ``future_ubers`` work like in fetch_banners."""
    return roll_selected(
        seed,
        names,
        count=count,
        last_cat=last_cat,
        simulate_guaranteed=simulate_guaranteed,
        future_ubers=future_ubers,
    )


def newly_added_ubers(events=None, pools=None, units=None) -> dict[str, set[str]]:
    """Per banner, the ubers making their game DEBUT with that run - the game's "New
    units added" set. Debut means no event anywhere started earlier carrying the unit:
    a returning banner absorbs whatever premiered elsewhere since its last run (festival
    banners usually debut units months before a series banner picks them up), and none
    of that counts as new here. Keyed by run name via each name's latest run (how the
    roller keys banners), so a track cell can flag an uber that debuts on the banner
    it's rolled on."""
    events = load_events() if events is None else events
    pools = load_pools() if pools is None else pools
    units = units_from_records() if units is None else units

    def ubers(pool_id: int) -> set[str]:
        return {
            units[u][0]
            for u in pools.get(pool_id, ())
            if u in units and units[u][1] == Rarity.UBER_SUPER_RARE.value
        }

    debut: dict[str, date] = {}
    latest: dict[str, GachaEventRow] = {}
    for event in events:
        for name in ubers(event.pool_id):
            if name not in debut or event.start < debut[name]:
                debut[name] = event.start
        held = latest.get(event.name)
        if held is None or event.start > held.start:
            latest[event.name] = event

    added: dict[str, set[str]] = {}
    for event in latest.values():
        new = {name for name in ubers(event.pool_id) if debut[name] == event.start}
        if new:
            added[event.name] = new

    return added


def _by_rarity(cats: Iterable[Cat], reverse: bool = False) -> list[tuple[str, list[Cat]]]:
    """Bin cats by rarity; cheapest-to-rarest, or rarest-first when ``reverse``.

    Blank rarities fall under 'Unknown' (always last).
    """
    bins: dict[str, list[Cat]] = {}
    for cat in cats:
        bins.setdefault(cat.rarity or "Unknown", []).append(cat)

    rank = {name: i for i, name in enumerate(RARITY_ORDER)}
    unknown = len(rank)
    ordered = sorted(bins.items(), key=lambda kv: (rank.get(kv[0], unknown), kv[0]))
    if reverse:
        known = [kv for kv in ordered if kv[0] in rank]
        rest = [kv for kv in ordered if kv[0] not in rank]
        ordered = known[::-1] + rest

    return ordered


def collection_sections(units: Iterable[Unit]) -> list[tuple[str, list[Unit]]]:
    """Units binned by rarity in game order (Normal first, Legend Rare last), keeping
    the given order within each bin; blank rarities fall under 'Unknown', always last."""
    return _by_rarity(units)


# A unit carried by more series than this is part of the shared rare/super pool that
# every capsule banner offers, not exclusive to any set.
_REGULAR_SERIES_LIMIT = 3

REGULARS_LABEL = "Rare Capsule Regulars"
ADDONS_LABEL = "Rare Capsule Add-ons"

# True regulars ride along on at least this share of all scheduled series; the rest of
# the shared crowd are add-ons (Grandon Mining Corps, the Neneko gang, Reinforcement,
# the Brainwashed cats) that many banners bolt on but fests and collabs skip.
_REGULAR_CARRY = 0.6

# Ticket gachas by their ItemID_Ticket: their pools mix every set, so no set name fits.
_TICKET_NAMES = {29: "Platinum Capsules", 145: "Legend Capsules"}

# Display respellings over the Cat Guide's own set names, applied wherever a set name
# becomes a label (collection sections, picker titles).
_SET_DISPLAY = {"UBER FEST": "UBERFEST", "Royalfest": "RoyalFest"}


def _display(set_name: str) -> str:
    return _SET_DISPLAY.get(set_name, set_name)


# The recurring fest capsules by their stable series id (GatyaData_Option_SetR seriesID,
# unchanged across reruns). Their pools mix every set, so neither the Cat Guide nor the
# run's marketing text names them; where the guide DOES name one (UBERFEST, EPICFEST,
# RoyalFest), the label here matches its displayed name so both name the same section.
FEST_SERIES = {
    19: "UBERFEST",
    27: "EPICFEST",
    35: "Best of the Best",
    39: "Neo Best of the Best",
    42: "SUPERFEST",
    47: "Dynasty Fest",
    50: "RoyalFest",
    59: "Busterfest",
    70: "Best of the Best: Milestone Editions",
}

# A fest carrying at least this share of a set (or of the standard legends) features it.
_FEST_COVER = 0.6
# A set carried by more fests than this is the general Uber pool every fest drops
# (Uberfest, Epicfest and Superfest all carry the classic sets), not a fest's feature.
_FEST_SET_CAP = 2

# One-line section explainers for the collection's by-set view.
_FEST_NOTE = "Fest exclusives; every standard-set Uber also drops here."
_BOTB_NOTE = "Anniversary capsules: a rotating best-of selection plus these exclusives."
_LEGEND_NOTE = "Boosted Legend Rare rates; every standard Legend drops here."
SECTION_NOTES = {
    REGULARS_LABEL: "The shared Rare/Super pool; these drop on every Rare Capsule banner.",
    ADDONS_LABEL: "Extra regulars many banners add to the shared pool; fests skip them.",
    "UBERFEST": _FEST_NOTE,
    "EPICFEST": _FEST_NOTE,
    "SUPERFEST": "Uberfest and Epicfest exclusives combined; every standard-set Uber drops too.",
    "Dynasty Fest": "Every seasonal set in one capsule.",
    "Busterfest": "Every Buster unit in one capsule.",
    "RoyalFest": _LEGEND_NOTE,
    "Best of the Best: Milestone Editions": _LEGEND_NOTE,
    "Best of the Best": _BOTB_NOTE,
    "Neo Best of the Best": _BOTB_NOTE,
}


def _series_pools(events, pools, series):
    """Each series' latest scheduled run and that run's pool: ({sid: event}, {sid: ids})."""
    latest: dict[int, GachaEventRow] = {}
    for event in events:
        sid = series.get(event.pool_id)
        current = latest.get(sid)
        if sid is not None and (current is None or event.start > current.start):
            latest[sid] = event

    members = {sid: set(pools.get(event.pool_id, ())) for sid, event in latest.items()}

    return latest, members


def series_names(units, events=None, pools=None, series=None, tickets=None) -> dict[int, str]:
    """The official display name per series id, e.g. {1: 'The Dynamites'}.

    Each Cat Guide set names its HOME series: the smallest pool that carries most of the
    set's units - the set's own banner, not a fest/Platinum umbrella that also happens to
    have them all. Recurring fests get their FEST_SERIES name, ticket gachas
    (Platinum/Legend Capsules) get their ticket's name; series the game data doesn't name
    (collabs) aren't here, so callers fall back to the run's marketing text."""
    events = events if events is not None else load_events()
    pools = pools if pools is not None else load_pools()
    series = series if series is not None else load_series()
    tickets = tickets if tickets is not None else load_tickets()
    latest, members = _series_pools(events, pools, series)

    by_set: dict[str, set[int]] = {}
    for unit in units:
        if unit.set_name:
            by_set.setdefault(unit.set_name, set()).add(unit.unit_id)

    names: dict[int, str] = {}
    # Biggest set first, so it wins if two sets share a home pool.
    for name, ids in sorted(by_set.items(), key=lambda kv: -len(kv[1])):
        carriers = [sid for sid, member in members.items() if len(member & ids) * 2 >= len(ids)]
        if carriers:
            names.setdefault(min(carriers, key=lambda sid: len(members[sid])), _display(name))

    for sid in latest:
        if sid in FEST_SERIES:
            names.setdefault(sid, FEST_SERIES[sid])

    for sid, event in latest.items():
        ticket = tickets.get(event.pool_id)
        if ticket in _TICKET_NAMES:
            names[sid] = _TICKET_NAMES[ticket]

    return names


def banner_titles(units=None, events=None, pools=None, series=None, tickets=None) -> dict[int, str]:
    """{pool_id: display title} for picker rows - the pool's series name where one is
    known; pools without one keep their marketing text as the title."""
    units = units if units is not None else Unit.objects.exclude(set_name="")
    series = series if series is not None else load_series()
    names = series_names(units, events, pools, series, tickets)

    return {pid: names[sid] for pid, sid in series.items() if sid in names}


def display_titles(events=None) -> dict[str, str]:
    """{run name: short display title} - the picker's set-derived titles rekeyed by the
    banner names the roller uses, so track legends and step headers can lead with 'The
    Dynamites' instead of the run's marketing text. Untitled names are absent (callers
    fall back to the name itself)."""
    events = events if events is not None else load_events()
    titles = banner_titles(events=events)

    return {event.name: titles[event.pool_id] for event in events if event.pool_id in titles}


def _titled(names, titles):
    """The display titles for a banner-name list, deduped (reruns share a title)."""
    return sorted({titles.get(name, name) for name in names})


def set_sections(
    units: Iterable[Unit], events=None, pools=None, series=None
) -> list[tuple[str, list[tuple[str, list[Unit]]]]]:
    """The by-gacha-set view: every gacha unit under its home set(s), split by rarity -
    ``[(set_label, [(rarity, [unit, ...]), ...]), ...]``.

    A unit's home is its official Cat Guide set name (The Dynamites, Iron Legion, ...).
    Units the guide doesn't place fall back to the banner series that carries them -
    reruns share a series id, so a returning set never shows up twice. A series whose
    pool's named members mostly belong to one set (that set's own banner) counts as that
    set, so its unnamed legend joins them; a mixed pool (a fest/Platinum umbrella) never
    claims a home. Whatever's left homes to its smallest carrier's series, labelled by
    the latest run's text. Units in more series than _REGULAR_SERIES_LIMIT are the shared
    pool that leads the page: true regulars (carried almost everywhere) under
    REGULARS_LABEL, the rest - banner add-ons that fests skip - under ADDONS_LABEL. Units
    in no pool (Normal/Special/story cats) are left to the rarity view.

    The recurring fests (FEST_SERIES) get their own sections, and unlike homes they can
    repeat units - it's the same cat everywhere, so its marks stay in sync. A fest lists
    its exclusives (umbrella-only units like Izanagi, on EVERY fest that carries them),
    any set it (almost) fully bundles - Superfest = Uberfest + Epicfest, Dynasty Fest =
    the seasonal sets, Busterfest = the Busters - unless every fest carries that set
    anyway (the classic sets), and the standard legends when it carries nearly all of
    them (the legend-rate fests: Royalfest, the Milestone capsules).

    Order: regulars and add-ons first, then named sets and fests by dictionary order
    (lowest unit id), then series groups, newest run first.
    """
    events = events if events is not None else load_events()
    pools = pools if pools is not None else load_pools()
    series = series if series is not None else load_series()
    latest, members = _series_pools(events, pools, series)

    # A series speaks for a set when most of its pool's set-named members agree; a pool
    # naming many sets about equally is an umbrella (fests, Platinum) and claims nobody.
    unit_sets = {unit.unit_id: unit.set_name for unit in units if unit.set_name}
    series_set: dict[int, str] = {}
    umbrella: set[int] = set()
    for sid, ids in members.items():
        counts = Counter(unit_sets[uid] for uid in ids if uid in unit_sets)
        if counts:
            top, hits = counts.most_common(1)[0]
            if hits * 2 > counts.total():
                series_set[sid] = top
            else:
                umbrella.add(sid)

    named: dict[str, dict[int, Unit]] = {}
    homed: dict[int, list[Unit]] = {}
    regulars: list[Unit] = []
    addons: list[Unit] = []
    fests: dict[int, dict[int, Unit]] = {sid: {} for sid in FEST_SERIES if sid in members}
    standard_legends: set[int] = set()
    for unit in units:
        if unit.set_name:
            named.setdefault(_display(unit.set_name), {})[unit.unit_id] = unit
            continue

        candidates = [sid for sid, ids in members.items() if unit.unit_id in ids]
        if not candidates:
            continue

        specific = [sid for sid in candidates if sid not in umbrella]
        if not specific:
            # Fest exclusives have no banner of their own; they live on every fest
            # that carries them (Izanagi on both Uberfest and Superfest).
            carried = [sid for sid in candidates if sid in fests]
            for sid in carried:
                fests[sid][unit.unit_id] = unit

            if not carried:
                addons.append(unit)
            continue

        if unit.rarity == Rarity.LEGEND_RARE.value:
            standard_legends.add(unit.unit_id)

        if len(specific) > _REGULAR_SERIES_LIMIT:
            shared = len(candidates) >= _REGULAR_CARRY * len(members)
            (regulars if shared else addons).append(unit)
            continue

        home = min(specific, key=lambda sid: len(members[sid]))
        if home in series_set:
            named.setdefault(_display(series_set[home]), {})[unit.unit_id] = unit
        else:
            homed.setdefault(home, []).append(unit)

    by_id = {unit.unit_id: unit for unit in units}
    by_set: dict[str, set[int]] = {}
    for uid, name in unit_sets.items():
        by_set.setdefault(name, set()).add(uid)

    for ids in by_set.values():
        carriers = [sid for sid in fests if len(members[sid] & ids) >= _FEST_COVER * len(ids)]
        if 0 < len(carriers) <= _FEST_SET_CAP:
            for sid in carriers:
                for uid in sorted(members[sid] & ids):
                    fests[sid][uid] = by_id[uid]

    if standard_legends:
        for sid in fests:
            hit = members[sid] & standard_legends
            if len(hit) >= _FEST_COVER * len(standard_legends):
                for uid in sorted(hit):
                    fests[sid][uid] = by_id[uid]

    # A fest sharing its label with a Cat Guide set (UBER FEST, EPICFEST, Royalfest) IS
    # that set's banner, so merging by label folds the extras into the named section.
    for sid, extras in fests.items():
        if extras:
            named.setdefault(FEST_SERIES[sid], {}).update(extras)

    sections = [
        (label, cats)
        for label, cats in ((REGULARS_LABEL, regulars), (ADDONS_LABEL, addons))
        if cats
    ]
    sections += sorted(
        ((label, list(group.values())) for label, group in named.items()),
        key=lambda kv: (min(u.unit_id for u in kv[1]), kv[0]),
    )
    sections += [
        (latest[sid].name, homed[sid])
        for sid in sorted(homed, key=lambda sid: latest[sid].start, reverse=True)
    ]

    return [(label, _by_rarity(cats)) for label, cats in sections]


def _effective_runs(events) -> list[tuple[GachaEventRow, date, date]]:
    """Schedule runs with overlapping same-name reruns sorted out: a rerun replaces the
    one before it (permanent banners carry a placeholder 2030 end, so the Platinum
    Capsules' April run really ends the day before the July rerun starts). Sorted by
    start; ends are inclusive."""
    by_name: dict[str, list] = {}
    for event in events:
        by_name.setdefault(event.name, []).append(event)

    capped = []
    for runs in by_name.values():
        runs.sort(key=lambda e: e.start)
        for event, successor in zip(runs, runs[1:] + [None], strict=True):
            end = min(event.end, successor.start - timedelta(days=1)) if successor else event.end
            capped.append((event, event.start, end))

    return sorted(capped, key=lambda run: run[1])


def picker_groups(
    cats: Iterable[Cat], today: date | None = None, events=None, titles: Mapping[int, str] = ()
) -> list:
    """The target picker's banner sections, one row per SCHEDULED RUN, like godfat: every
    rerun of every gacha, past and future. A recurring name (Platinum/Legend Capsules,
    reruns) gets its own row per run, each with its own dates, so picking one names an
    exact session. Cats are matched onto rows by banner name from the roll-derived
    catalogue; only a name's newest past row carries them, so the ~2000 old rows stay
    light (a brand-new banner shows up without cats until it's imported).

    ``titles`` maps a run's pool id to its set's display name (banner_titles); rows
    without one fall back to the run's marketing text. Returns
    ``[(label, [(name, title, (start, end), rarities)])]``."""
    today = today or date.today()

    if events is None:
        events = load_events()

    titles = titles or {}

    by_name: dict[str, list[Cat]] = {}
    other: list[Cat] = []
    for cat in cats:
        names = [banner.name for banner in cat.banners.all()]
        for name in names:
            by_name.setdefault(name, []).append(cat)

        if not names:
            other.append(cat)

    def row(name, dates, title="", with_cats=True):
        cats_here = _by_rarity(by_name.get(name, []), reverse=True) if with_cats else []
        return (name, title or name, dates, cats_here)

    def run_row(event, start, end, with_cats=True):
        return row(event.name, (start, end), titles.get(event.pool_id, ""), with_cats)

    runs = _effective_runs(events)
    now = [run_row(e, start, end) for e, start, end in runs if start <= today <= end]
    upcoming = [run_row(e, start, end) for e, start, end in runs if start > today]
    past_runs = sorted(
        (run for run in runs if run[2] < today), key=lambda run: run[1], reverse=True
    )

    carried: set[str] = set()
    past = []
    for event, start, end in past_runs:
        past.append(run_row(event, start, end, with_cats=event.name not in carried))
        carried.add(event.name)

    # DB-dated banners the schedule doesn't know (old godfat-era names) still get a row.
    scheduled = {event.name for event, _start, _end in runs}
    banners = {b.name: b for b in Banner.objects.filter(name__in=by_name)}
    past += [
        row(name, (banner.start, banner.end))
        for name, banner in banners.items()
        if name not in scheduled and banner.end and banner.end < today
    ]
    past.sort(key=lambda r: r[2][0], reverse=True)
    dated = scheduled | {name for name, banner in banners.items() if banner.end}
    leftovers = [row(name, None) for name in sorted(by_name) if name not in dated]
    if other:
        leftovers.append(("Other", "Other", None, _by_rarity(other, reverse=True)))

    groups = [
        ("Available now", now),
        ("Upcoming", upcoming),
        ("Past", past),
        ("Other", leftovers),
    ]

    return [group for group in groups if group[1]]


def equivalent_banners(banners: Mapping[str, BannerRolls]) -> dict[str, list[str]]:
    """Map each banner to every banner (itself included) with the exact same roll
    sequence. Same seed + same pool = same pulls, so those banners are swappable for any
    plan rolled on them."""
    groups: dict[tuple, list[str]] = {}
    for name, rolls in banners.items():
        key = (tuple(rolls.pulls), tuple(rolls.guaranteed))
        groups.setdefault(key, []).append(name)

    return {name: names for names in groups.values() for name in names}


TRACK_ROW_CAP = 100  # A/B rows rendered by default, before a plan extends the window

# Only Uber/Legend cats are worth flagging as "not yet in your collection" in the grid.
_VALUABLE_RARITIES = {Rarity.UBER_SUPER_RARE.value, Rarity.LEGEND_RARE.value}


def cost_label(tickets, catfood):
    """Spell out a plan's price in both currencies; pulls are ticket-funded first,
    so a plan can be pure tickets, pure catfood, or a mix."""
    parts = []

    if tickets:
        parts.append(f"{tickets} ticket{'s' if tickets != 1 else ''}")
    if catfood:
        parts.append(f"{catfood} catfood")

    return " + ".join(parts) or "free"


def _pos_label(index):
    """A stream index back to its godfat slot, e.g. 5 -> '3B'."""
    return f"{index // 2 + 1}{'A' if index % 2 == 0 else 'B'}"


def _collection_marks(cat, rarity, owned, wanted, debuts=()):
    """The collection marks every rendered cat carries: ✓ owned, ★ wishlisted, a green
    "new" name for an Uber/Legend not yet in the collection, and a "debut" flag for an uber
    making its first-ever appearance on an upcoming banner (``debuts``). A future-uber
    placeholder is by definition uncollected and new to the banner, so it's green and
    "new"-pilled; ``future`` renders it as plain text (not a real unit - no popup)."""
    if is_future_uber(cat):
        return {"new": True, "owned": False, "wanted": False, "debut": True, "future": True}

    return {
        "new": rarity in _VALUABLE_RARITIES and cat not in owned,
        "owned": cat in owned,
        "wanted": cat in wanted,
        "debut": cat in debuts,
        "future": False,
    }


def _dupe_branch(outcome, obtained):
    """A cell's "if dupe" line: the reroll you get when a dupe lands here, where it jumps
    to, and the seed just after it (its own dice). ``obtained`` - the cat the plan pulled
    at this cell, if lit - puts the gold target pill on this branch when it collected it."""
    return {
        "cat": outcome.cat,
        "to": _pos_label(outcome.next_position),
        "left": outcome.next_position % 2 == 0,
        "seed": outcome.seed,
        "target": obtained == outcome.cat,
    }


@dataclass(slots=True)
class TrackMarks:
    """Where a plan lights up the track, each keyed by its representative banner: the lit
    stream indices (``path``), the cat you get at each lit index (``targets`` - the gold
    pill follows the branch actually pulled), and the indices another banner can do
    instead (``shared``, plan_shared); ``g*`` twins mark the guaranteed columns. Defaults
    give an unhighlighted track (the browse view)."""

    path: dict[str, set[int]] = field(default_factory=dict)
    targets: dict[str, dict[int, str]] = field(default_factory=dict)
    gpath: dict[str, set[int]] = field(default_factory=dict)
    gtargets: dict[str, dict[int, str]] = field(default_factory=dict)
    shared: dict[str, set[int]] = field(default_factory=dict)
    gshared: dict[str, set[int]] = field(default_factory=dict)


def _representative(name, equivalents):
    """The single banner an equivalent group is rendered under (its first name)."""
    return sorted(equivalents.get(name, [name]))[0]


def _banner_groups(banner_pulls, rerolls, equivalents, guaranteed=None):
    """Distinct selected banners (equivalent ones merged), each tagged 1, 2, 3...
    with its stream grid, outcome graph and guaranteed-uber grid."""
    guaranteed = guaranteed or {}
    groups = []
    seen = set()

    for name, pulls in banner_pulls.items():
        names = sorted(equivalents.get(name, [name]))
        rep = names[0]
        if rep in seen:
            continue

        seen.add(rep)
        grid = {stream_index(p.position, p.track): p for p in pulls}
        graph = BannerGraph(rep, pulls, rerolls=rerolls.get(name, ()))
        groups.append(
            {
                "tag": str(len(groups) + 1),
                "names": names,
                "rep": rep,
                "grid": grid,
                "graph": graph,
                "guaranteed": {
                    stream_index(p.position, p.track): p for p in guaranteed.get(name, ())
                },
            }
        )

    return groups


def build_tracks(
    banner_pulls,
    rerolls,
    equivalents,
    marks=None,
    owned=None,
    guaranteed=None,
    wanted=None,
    titles=None,
    rows=TRACK_ROW_CAP,
    debuts=None,
    future=None,
    unit_ids=None,
):
    """One merged A/B table over every selected banner: each cell stacks each banner's
    cat at that shared stream position (like ubercarry), with rare-dupe switch arrows
    and the plan's path highlighted. Returns ``{"legend": [...], "rows": [...]}``.

    ``marks`` (TrackMarks) is the plan's highlighting; leave it out for the browse view.
    ``owned``/``wanted`` are the cat names you already have / wishlisted, shown with the
    same ✓ / ★ marks the picker uses (``new`` flags Uber/Legend cats missing from your
    collection). ``guaranteed`` maps a banner to its guaranteed-uber column (godfat's:
    the uber a guaranteed multi gives you when STARTED on that cell); banners without a
    guaranteed multi have none, and when no selected banner has any, the columns are left
    out entirely (``has_guaranteed``). ``titles`` (display_titles) shortens the legend's
    banner names. ``rows`` is how many A/B rows to render (the browse view passes the
    user's "rolls to show"); a plan always extends past it to reach its furthest lit cell.
    ``future`` ({banner name: future-uber count}, browse view only) puts a per-banner
    stepper in the legend, pre-filled with the counts the rolls were padded with; leave
    it out (plan tracks) and no steppers render. ``unit_ids`` ({cat name: unit_id}) tags
    each cell with its catalogue id so the Rolls display-mode toggle can hotlink a form
    icon; names with no catalogued unit (or an empty map) just fall back to text.
    """
    marks = marks or TrackMarks()
    owned = owned or set()
    wanted = wanted or set()
    titles = titles or {}
    debuts = debuts or {}
    unit_ids = unit_ids or {}
    groups = _banner_groups(banner_pulls, rerolls, equivalents, guaranteed)
    # "New to this banner" is per banner (newly_added_ubers keys by name); a group merges
    # equivalent banners, so its debut set is the union over the names it stands for.
    for group in groups:
        group["debuts"] = set().union(*(debuts.get(name, set()) for name in group["names"]))

    avail = max((max(g["grid"]) for g in groups if g["grid"]), default=-1) // 2 + 1
    lit = [index for indices in (*marks.path.values(), *marks.gpath.values()) for index in indices]
    needed = max((index // 2 + 1 for index in lit), default=0)
    max_pos = max(min(avail, max(rows, needed)), 0)

    def entries(index):
        cells = []
        for group in groups:
            tp = group["grid"].get(index)
            if tp is None:
                continue

            graph = group["graph"]
            outcome = graph.outcome(index)
            switched = bool(outcome and outcome.switched)
            rarity = str(tp.rarity)
            on_path = index in marks.path.get(group["rep"], ())

            # Every cell shows the clean roll first: the cat you get if you arrive
            # cleanly. Its dupe branch - a rare that repeats the previous pull rerolls
            # and jumps tracks - shows underneath as one "if dupe" line, whether the
            # straight chain takes it (a static dupe, `switch`), only a bounce path does
            # (godfat's extra R cells), or the remembered last pull dupes the first cell.
            branch = None
            if switched:
                branch = outcome
            elif graph.realized(index):
                reroll = graph.reroll(index)
                if reroll is not None and reroll.cat:
                    branch = reroll

            # The cat the plan got here, if lit: the gold pill follows the branch the
            # plan actually pulls (a dupe-collected target lights the "if dupe" name,
            # not the clean one).
            obtained = marks.targets.get(group["rep"], {}).get(index)
            cells.append(
                {
                    "tag": group["tag"],
                    "idx": index,
                    "cat": tp.cat,
                    "uid": unit_ids.get(tp.cat),
                    "rarity": rarity,
                    "switch": switched,
                    "alt": _dupe_branch(branch, obtained) if branch is not None else None,
                    "on_path": on_path,
                    "target": obtained == tp.cat,
                    "shared": not on_path and index in marks.shared.get(group["rep"], ()),
                    **_collection_marks(tp.cat, rarity, owned, wanted, group["debuts"]),
                }
            )

        return cells

    def cell_seed(index):
        # The cell's docked dice: "I rolled this cell" - the state just after its normal
        # pull, so the next cell becomes the new 1A. It doesn't depend on the banner (a
        # clean roll uses the same two stream values whatever the pool), so one dice
        # serves the whole cell - read it off any banner rolled there. The dupe branch's
        # different state lives on the branch dice.
        for group in groups:
            tp = group["grid"].get(index)
            if tp is not None:
                return tp.seed

        return 0

    def cell_cat(index):
        # What the docked dice got, feeding the dupe memory - we only know it when every
        # banner stacked in the cell rolls the same name there.
        names = {g["grid"][index].cat for g in groups if index in g["grid"]}

        return names.pop() if len(names) == 1 else ""

    def cell_details(index):
        # The cell's raw RNG values for the details view (godfat's seed column): the
        # rarity seed the roll started from (the rarity band is read off it) and the slot
        # seed that indexes the pool. Both are stream values, the same for every banner
        # rolled here, so read them off any stacked pull.
        for group in groups:
            tp = group["grid"].get(index)
            if tp is not None:
                return {"rarity_seed": tp.rarity_seed, "slot_seed": tp.seed}

        return None

    def guaranteed_entries(index):
        cells = []
        for group in groups:
            tp = group["guaranteed"].get(index)
            if tp is None or not tp.cat:  # no guarantee on this banner, or an empty uber pool
                continue

            rarity = str(tp.rarity)
            on_path = index in marks.gpath.get(group["rep"], ())
            cells.append(
                {
                    "tag": group["tag"],
                    "idx": index,
                    "cat": tp.cat,
                    "uid": unit_ids.get(tp.cat),
                    "rarity": rarity,
                    # The state after the multi's final (guaranteed) draw - "as if you
                    # rolled this multi": what its dice jumps to. Rolling TO the multi
                    # is the track cell's own dice (same start anchor).
                    "seed": tp.seed,
                    "on_path": on_path,
                    "target": marks.gtargets.get(group["rep"], {}).get(index) == tp.cat,
                    "shared": not on_path and index in marks.gshared.get(group["rep"], ()),
                    **_collection_marks(tp.cat, rarity, owned, wanted, group["debuts"]),
                }
            )

        return cells

    has_guaranteed = any(group["guaranteed"] for group in groups)
    rows = [
        {
            "pos": pos,
            "a": entries(2 * (pos - 1)),
            "b": entries(2 * (pos - 1) + 1),
            "a_seed": cell_seed(2 * (pos - 1)),
            "b_seed": cell_seed(2 * (pos - 1) + 1),
            "a_cat": cell_cat(2 * (pos - 1)),
            "b_cat": cell_cat(2 * (pos - 1) + 1),
            "a_details": cell_details(2 * (pos - 1)),
            "b_details": cell_details(2 * (pos - 1) + 1),
            "ga": guaranteed_entries(2 * (pos - 1)) if has_guaranteed else [],
            "gb": guaranteed_entries(2 * (pos - 1) + 1) if has_guaranteed else [],
        }
        for pos in range(1, max_pos + 1)
    ]
    legend = [{"tag": g["tag"], "names": _titled(g["names"], titles)} for g in groups]
    if future is not None:
        # The stepper posts its count for every run name its group merges (equivalent
        # banners share one pool, so one padding count). ``keys`` carries the raw run
        # names - the legend shows titles, but the roller keys banners by run name.
        for entry, group in zip(legend, groups, strict=True):
            entry["keys"] = json.dumps(group["names"])
            entry["future"] = max((future.get(name, 0) for name in group["names"]), default=0)

    return {
        "legend": legend,
        "rows": rows,
        "has_guaranteed": has_guaranteed,
        "has_shared": bool(marks.shared or marks.gshared),
        "show_future": future is not None,
        "padded": bool(future) and any(future.values()),
    }


def plan_highlight(option, equivalents):
    """The plan's TrackMarks: a normal pull lights its track cell, a guaranteed pull the
    guaranteed COLUMN at the multi's first roll (where godfat shows the uber you get). The
    swappable-banner marks (``shared``/``gshared``, plan_shared) are left empty for the
    caller to fill in."""
    marks = TrackMarks()
    for pull in option.plan.pulls:
        rep = _representative(pull.banner_id, equivalents)
        path, targets = (
            (marks.gpath, marks.gtargets) if pull.guaranteed else (marks.path, marks.targets)
        )
        path.setdefault(rep, set()).add(pull.position)
        if pull.cat in option.targets:
            targets.setdefault(rep, {})[pull.position] = pull.cat

    return marks


def _move_walk(graph, move, last):
    """Replay one plan move on ``graph``, carrying the cat you got last (``last``) the
    same way the search walked it: a rare that repeats it rerolls, and a guaranteed multi
    whose first roll comes up as a dupe gives the duped column's uber. Returns (outcomes
    lined up with move.pulls, the cat you have after the move), or None when the walk runs
    off the end of the rolled window or the guaranteed column is missing."""
    first = graph.resolve(move.pulls[0].position, last)
    if first is None:
        return None

    outcomes = []
    for pull in move.pulls:
        if pull.guaranteed:
            outcome = graph.guaranteed(pull.position, duped=first.switched)
        else:
            outcome = graph.resolve(pull.position, last)
        if outcome is None:
            return None

        outcomes.append(outcome)
        last = outcome.cat

    return outcomes, last


def _serves_move(other, other_names, own_outcomes, move, targets, multis, last):
    """The cat banner ``other`` would end up holding after rolling this whole move, or
    None when the move doesn't fit there: the multi must be on offer at the same size and
    price, every pull must land where the original walk did (a dupe on one side steps
    differently), and a pull that collects a target must still give that exact cat - a
    filler pull is allowed to give a different one."""
    if move.kind != "Single pull":
        guaranteed = any(pull.guaranteed for pull in move.pulls)
        offered = (m for name in other_names for m in multis.get(name, ()))
        if not any(
            m.rolls == len(move.pulls) and m.cost == move.cost and m.guaranteed == guaranteed
            for m in offered
        ):
            return None

    walk = _move_walk(other, move, last)
    if walk is None:
        return None

    outcomes, end = walk
    for pull, own, mine in zip(move.pulls, own_outcomes, outcomes, strict=True):
        if not pull.guaranteed and mine.next_position != own.next_position:
            return None
        if pull.cat in targets and mine.cat != pull.cat:
            return None

    return end


def plan_shared(option, graphs, equivalents, multis=None, exclude=()):
    """Which OTHER selected banners each of a plan's moves can be rolled on without
    breaking the plan - the swappable steps. Stricter than equivalent_banners in one way
    and looser in another: only the pulls the plan actually makes have to line up, not
    the whole rolled window, and a filler pull just has to keep the same walk (the cat
    there can differ); but a pull that collects a target still has to give that cat.

    A move is one in-game action: a single pull matches where the walk holds; a multi
    needs its whole chain to walk the same way and the same multi on offer at the same
    price. The plan's walk is replayed path-aware (_move_walk): the cat you got before
    each move decides its dupes. A swapped move that ends on a different filler cat is
    only shared when the plan's NEXT pull still comes out the same - a dupe that fires on
    one side only would break everything after it. Banners named in ``exclude`` (the
    capped Platinum/Legend gachas - they run on their own scarce tickets, a totally
    different price) never count.

    Returns ``(shared, gshared)``: the stream indices to mark, per other representative
    banner - normal cells and guaranteed columns."""
    multis = multis or {}
    by_name = {graph.banner_id: graph for graph in graphs}

    groups: dict[str, list[str]] = {}
    for name in by_name:
        groups.setdefault(_representative(name, equivalents), []).append(name)

    excluded = {rep for rep, names in groups.items() if any(name in exclude for name in names)}
    shared: dict[str, set[int]] = {}
    gshared: dict[str, set[int]] = {}
    moves = option.plan.moves
    last = ""
    for index, move in enumerate(moves):
        own = _representative(move.banner_id, equivalents)
        walk = _move_walk(by_name[move.banner_id], move, last)
        if walk is None:  # can't happen for a plan the search produced; stay safe
            break

        own_outcomes, own_end = walk
        follow = moves[index + 1] if index + 1 < len(moves) else None
        for rep, names in groups.items():
            if rep == own or rep in excluded:
                continue

            end = _serves_move(
                by_name[rep], names, own_outcomes, move, option.targets, multis, last
            )
            if end is None:
                continue

            if follow is not None and end != own_end:
                nxt = by_name[follow.banner_id]
                start = follow.pulls[0].position
                if nxt.resolve(start, own_end) != nxt.resolve(start, end):
                    continue

            for pull in move.pulls:
                into = gshared if pull.guaranteed else shared
                into.setdefault(rep, set()).add(pull.position)

        last = own_end

    return shared, gshared


def trace_marks(banner_pulls, rerolls, equivalents, tag, index, last_cat="", multis=None):
    """Plan-style marks for a clicked cell (godfat's pick): the single-pull walk from the
    table start UP TO the cell, on the clicked banner (its legend ``tag``), with the gold
    target pill on the cell itself - plus plan_shared's dashes on every walked step that
    another selected banner could roll without changing the path. A dupe hop that jumps
    the walk past the cell leaves the tail unlit (straight singles can't reach it), and a
    stale click (unknown tag, cell beyond the rolled window) marks nothing."""
    groups = _banner_groups(banner_pulls, rerolls, equivalents)
    picked = next((g for g in groups if g["tag"] == str(tag)), None)
    if picked is None or index not in picked["grid"]:
        return TrackMarks()

    graph, rep = picked["graph"], picked["rep"]
    walk, last, at = [], last_cat, 0
    while at <= index:
        outcome = graph.resolve(at, last)
        if outcome is None:
            break

        walk.append((at, outcome))
        if at == index:
            break
        last, at = outcome.cat, outcome.next_position

    reached = bool(walk) and walk[-1][0] == index
    target = walk[-1][1].cat if reached else picked["grid"][index].cat
    marks = TrackMarks(
        path={rep: {step for step, _ in walk}},
        targets={rep: {index: target}},
    )

    # The walk replayed as a plan of single pulls: exactly what plan_shared swaps.
    pulls = tuple(Pull(step, rep, outcome.cat, outcome.rarity) for step, outcome in walk)
    moves = tuple(Leg(rep, "Single pull", 0, (pull,)) for pull in pulls)
    option = SubsetPlan(frozenset({target} if reached else ()), Path(pulls, 0, 0, moves))
    graphs = [group["graph"] for group in groups]
    marks.shared, marks.gshared = plan_shared(option, graphs, equivalents, multis)

    return marks


def plan_seed(plan, graphs):
    """The RNG state after a plan's last draw - what the seed becomes once the plan is
    actually rolled ("apply plan" jumps to it). The plan records its whole walk, so the
    last pull is worked out from the cat you got just before it: a dupe - even one only
    this path triggers - lands on its reroll's seed, and a guaranteed multi whose first
    roll came up duped reads the duped column's. The recorded cat decides it when the
    graph's data can't say on its own (a plan replayed without its history)."""
    if not plan.pulls:
        return None

    last = plan.pulls[-1]
    graph = next((g for g in graphs if g.banner_id == last.banner_id), None)
    if graph is None:
        return None

    if last.guaranteed:
        # The multi started duped iff its first roll (the recorded pull at the same
        # position) got the reroll rather than the clean cat.
        inner = next(
            (
                p
                for p in plan.pulls
                if p.position == last.position
                and p.banner_id == last.banner_id
                and not p.guaranteed
            ),
            None,
        )
        nominal = graph.resolve(last.position)
        duped = inner is not None and nominal is not None and inner.cat != nominal.cat
        forced = graph.guaranteed(last.position, duped=duped) or graph.guaranteed(last.position)

        return forced.seed if forced else None

    before = plan.pulls[-2].cat if len(plan.pulls) > 1 else ""
    resolved = graph.resolve(last.position, before)
    for outcome in (resolved, graph.reroll(last.position)):
        if outcome is not None and outcome.cat == last.cat:
            return outcome.seed

    return resolved.seed if resolved else None


def plan_summary(plans, equivalents, owned=None, wanted=None, titles=None):
    """Per-option summary: targets, cost, and per-banner-leg rolls + cat sequence.
    Each cat carries the same marks as its track cell (target / owned / wanted / new).
    ``titles`` (display_titles) shortens the leg headers' banner names."""
    owned = owned or set()
    wanted = wanted or set()
    titles = titles or {}
    summaries = []

    for option in plans:
        legs = []
        last_banner = None

        for leg in option.plan.legs:
            rolls = len(leg.pulls)
            # Single pulls are paid per draw with a ticket (free) or 150 catfood;
            # leg.cost only counts the catfood ones, so the rest are ticket-funded.
            tickets = rolls - leg.cost // CATFOOD_PER_DRAW if leg.kind == "Single pull" else 0
            legs.append(
                {
                    "names": _titled(equivalents.get(leg.banner_id, [leg.banner_id]), titles),
                    "new_banner": leg.banner_id != last_banner,
                    "kind": leg.kind,
                    "cost": leg.cost,
                    "tickets": tickets,
                    "rolls": rolls,
                    "cats": [
                        {
                            "name": pull.cat,
                            "target": pull.cat in option.targets,
                            **_collection_marks(pull.cat, str(pull.rarity), owned, wanted),
                        }
                        for pull in leg.pulls
                    ],
                }
            )
            last_banner = leg.banner_id

        summaries.append(
            {
                "targets": sorted(option.targets),
                "cost": option.plan.cost,
                "tickets_used": option.plan.tickets_used,
                "cost_label": cost_label(option.plan.tickets_used, option.plan.cost),
                "cats": "|".join(option.plan.cats),
                "legs": legs,
            }
        )

    return summaries


# The exact per-subset breakdown is exponential in the target count - 2^n searches AND
# 2^n accordion rows - so it only runs for target sets this small. Bigger sets (wishlist
# searches) get the bounded view instead: plans over the targets actually obtainable in
# the selected banners, and one flat "Not found" row per unobtainable target.
SUBSET_TARGET_LIMIT = 10

# Frontier width for the big-wishlist fallback's whole-set beam search.
_WISHLIST_BEAM_WIDTH = 200


def _missing_subsets(items, found_keys):
    """Every not-yet-found subset of ``items``, biggest first. Exponential in ``items`` -
    callers keep it under SUBSET_TARGET_LIMIT."""
    return [
        sorted(combo)
        for size in range(len(items), 0, -1)
        for combo in combinations(items, size)
        if frozenset(combo) not in found_keys
    ]


def _wishlist_plans(graphs, wanted, start, multis, ticket_value, banner_limits):
    """Bounded plans for when even the obtainable targets are too many to list out one by
    one: the whole set in a single beam search (fast, not guaranteed optimal) plus each
    target on its own, exactly. Linear in the wishlist where the full breakdown would be
    exponential."""
    found = []
    full = beam_search(
        graphs,
        wanted,
        start,
        _WISHLIST_BEAM_WIDTH,
        multis=multis,
        ticket_value=ticket_value,
        banner_limits=banner_limits,
    )
    if full is not None:
        found.append(SubsetPlan(frozenset(wanted), full))

    for cat in wanted:
        single = astar(
            graphs,
            {cat},
            start,
            multis=multis,
            ticket_value=ticket_value,
            banner_limits=banner_limits,
        )
        if single is not None:
            found.append(SubsetPlan(frozenset({cat}), single))

    found.sort(key=lambda sp: (-len(sp.targets), sp.plan.cost))

    return found


def _subset_plans(graphs, targets, start, multis, ticket_value, banner_limits):
    """The plan rows behind subset_solutions: ``(found plans, missing target-lists)``.

    Up to SUBSET_TARGET_LIMIT targets get the exact per-subset breakdown. Past that there
    are too many subsets to list (a 100-cat wishlist is 2^100 rows), so it narrows down to
    the targets you can actually get on the selected banners - still per-subset when there
    are few, otherwise the bounded whole-set + per-cat view (_wishlist_plans) - and every
    target you can't get goes straight to missing."""
    search = dict(multis=multis, ticket_value=ticket_value, banner_limits=banner_limits)
    items = sorted(set(targets))

    if len(items) <= SUBSET_TARGET_LIMIT:
        pool, unobtainable = items, []
    else:
        pool = sorted(obtainable(graphs, targets))
        pooled = set(pool)
        unobtainable = [[cat] for cat in items if cat not in pooled]

    if len(pool) <= SUBSET_TARGET_LIMIT:
        found = solve_subsets(graphs, pool, start, **search)
        missing = _missing_subsets(pool, {sp.targets for sp in found})
    else:
        found = _wishlist_plans(graphs, pool, start, **search)
        found_keys = {sp.targets for sp in found}
        missing = [pool] if frozenset(pool) not in found_keys else []
        missing += [[cat] for cat in pool if frozenset({cat}) not in found_keys]

    return found, missing + unobtainable


def subset_solutions(
    pulls,
    rerolls,
    equivalents,
    targets,
    *,
    tickets,
    catfood,
    guaranteed_pulls=None,
    multis=None,
    ticket_value=CATFOOD_PER_DRAW,
    banner_limits=None,
    owned=None,
    wanted=None,
    titles=None,
    guaranteed_rerolls=None,
    last_cat="",
    debuts=None,
    unit_ids=None,
):
    """Every non-empty target subset and its best plan, biggest-then-cheapest, with the
    unreachable subsets listed after. Reachable ones carry the steps + highlighted track
    to render on demand; unreachable ones are flagged so the UI can say "Not found".

    ``last_cat`` is the pull you got just before this view (the dupe memory): if the
    search's first roll lands on a cell that repeats it, it comes up as a dupe. The
    subset/plan breakdown itself is _subset_plans."""
    graphs = build_graphs(pulls, guaranteed_pulls, rerolls, guaranteed_rerolls)
    start = State(0, tickets, catfood // CATFOOD_PER_DRAW, frozenset(), last_cat=last_cat)
    found, missing = _subset_plans(graphs, targets, start, multis, ticket_value, banner_limits)
    solutions = []

    for sp in found:
        marks = plan_highlight(sp, equivalents)
        marks.shared, marks.gshared = plan_shared(
            sp, graphs, equivalents, multis, exclude=banner_limits or ()
        )
        solution = plan_summary([sp], equivalents, owned, wanted, titles)[0]
        solution["found"] = True
        solution["seed_after"] = plan_seed(sp.plan, graphs)
        # The plan's final pull, remembered with seed_after: applying the plan can then
        # flag a dupe on the very first roll of the advanced view.
        solution["last_cat"] = sp.plan.pulls[-1].cat if sp.plan.pulls else ""
        solution["track"] = build_tracks(
            pulls,
            rerolls,
            equivalents,
            marks,
            owned=owned,
            guaranteed=guaranteed_pulls,
            wanted=wanted,
            titles=titles,
            debuts=debuts,
            unit_ids=unit_ids,
        )
        solutions.append(solution)

    for row in missing:
        solutions.append({"targets": row, "found": False})

    return solutions


def unit_match_report() -> tuple[dict[str, int], list[str]]:
    """Match every imported cat name against the canonical catalogue; return the
    {name: unit_id} matches and the names with no canonical unit (gaps to chase)."""
    return match_names(Cat.objects.values_list("name", flat=True), name_index(Unit.objects.all()))


def import_units(records: Iterable[Mapping]) -> int:
    """Upsert the canonical catalogue from units.json records; return the new-unit count."""
    created = 0
    for record in records:
        _, was_created = Unit.objects.update_or_create(
            unit_id=record["id"],
            defaults={
                "name": record["name"],
                "rarity": record.get("rarity", ""),
                "forms": record.get("forms", []),
                "set_name": record.get("set", ""),
            },
        )
        created += int(was_created)

    return created


def reconcile_provisional_units() -> tuple[int, list[str]]:
    """Merge each provisional unit into its now-canonical version by the same name: move
    its cats and owned/wishlist flags onto the canonical unit, then delete the stand-in.
    Returns how many were merged and the names of any provisionals that still have no
    canonical match (left in place)."""
    merged = 0
    orphaned = []

    for prov in Unit.objects.filter(canonical=False):
        canonical = Unit.objects.filter(canonical=True, name=prov.name).order_by("unit_id").first()
        if canonical is None:
            orphaned.append(prov.name)
            continue

        Cat.objects.filter(unit=prov).update(unit=canonical)
        carried = [
            flag
            for flag in ("owned", "wanted")
            if getattr(prov, flag) and not getattr(canonical, flag)
        ]
        if carried:
            for flag in carried:
                setattr(canonical, flag, True)

            canonical.save(update_fields=carried)

        prov.delete()
        merged += 1

    return merged, orphaned


PROVISIONAL_BASE = 1_000_000  # synthetic ids for cats not yet in the catalogue


def unit_for_cat(name: str, rarity: str = "") -> Unit:
    """The catalogue unit for a cat name, creating a provisional stand-in if it isn't in the
    catalogue yet - so every cat has a stable home for its owned/wishlist flags."""
    unit = Unit.objects.filter(name=name).first()
    if unit is None:
        last = Unit.objects.filter(unit_id__gte=PROVISIONAL_BASE).order_by("-unit_id").first()
        next_id = (last.unit_id + 1) if last else PROVISIONAL_BASE
        unit = Unit.objects.create(unit_id=next_id, name=name, rarity=rarity, canonical=False)

    return unit


def import_cats(
    banners: Mapping[str, BannerRolls],
    dates: Mapping[str, tuple[date, date]] | None = None,
) -> int:
    """Add rolled cats and their banner membership to the catalogue; return new-cat count."""
    dates = dates or {}
    created = 0

    for banner_name, rolls in banners.items():
        banner, _ = Banner.objects.get_or_create(name=banner_name)
        run = dates.get(banner_name)
        if run and (banner.start, banner.end) != run:
            banner.start, banner.end = run
            banner.save(update_fields=["start", "end"])

        for pull in (*rolls.pulls, *rolls.guaranteed):
            cat, was_created = Cat.objects.get_or_create(
                name=pull.cat, defaults={"rarity": pull.rarity.value}
            )
            created += int(was_created)

            if not was_created and pull.rarity.value and cat.rarity != pull.rarity.value:
                cat.rarity = pull.rarity.value
                cat.save(update_fields=["rarity"])

            if cat.unit_id is None:
                cat.unit = unit_for_cat(pull.cat, pull.rarity.value)
                cat.save(update_fields=["unit"])

            banner.cats.add(cat)

    return created
