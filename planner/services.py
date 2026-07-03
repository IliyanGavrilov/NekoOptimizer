from collections import Counter
from collections.abc import Iterable, Mapping
from datetime import date, timedelta
from itertools import combinations

from neko.catalogue import match_names, name_index
from neko.gachadata import GachaEventRow, load_events, load_pools, load_series, load_tickets
from neko.godfat import BannerRolls
from neko.graph import BannerGraph, build_graphs, stream_index
from neko.models import CATFOOD_PER_DRAW, Rarity, State
from neko.roller import catalogue_banners, roll_active, roll_selected
from neko.scraper import DEFAULT_COUNT, ScrapeResult
from neko.subsets import solve_subsets
from planner.models import Banner, Cat, Unit

RARITY_ORDER = ["Normal", "Special", "Rare", "Super Rare", "Uber Super Rare", "Legend Rare"]

# Platinum/Legend run on scarce tickets, not catfood, so the optimizer treats them as
# info-only: capped (0 by default) rather than modelled as ordinary catfood gacha.
_CAPPED_KEYWORDS = ("platinum", "legend")


def capped_banner_limits(names: Iterable[str], cap: int) -> dict[str, int]:
    """Cap pulls on Platinum/Legend banners (matched by name) at `cap`."""
    return {name: cap for name in names if any(kw in name.lower() for kw in _CAPPED_KEYWORDS)}


def fetch_banners(seed: int, count: int = DEFAULT_COUNT) -> ScrapeResult:
    """Roll the active banners for a seed locally (no godfat)."""
    return roll_active(seed, count=count)


def fetch_catalogue() -> ScrapeResult:
    """Every scheduled banner's droppable cats, straight from the gacha pools."""
    return catalogue_banners()


def fetch_for_banners(seed: int, names: Iterable[str], count: int = DEFAULT_COUNT) -> ScrapeResult:
    """Roll just the chosen banners for a seed locally."""
    return roll_selected(seed, names, count=count)


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

# Ticket gachas by their ItemID_Ticket: their pools mix every set, so no set name fits.
_TICKET_NAMES = {29: "Platinum Capsules", 145: "Legend Capsules"}


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

    Each Cat Guide set names its HOME series: the smallest pool carrying most of the
    set's units - its own banner, not a fest/Platinum umbrella that also has them all.
    Ticket gachas (Platinum/Legend Capsules) are named by their ticket instead; series
    the game data doesn't name (collabs) are absent, so callers fall back to the run's
    marketing text."""
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
            names.setdefault(min(carriers, key=lambda sid: len(members[sid])), name)
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


def set_sections(
    units: Iterable[Unit], events=None, pools=None, series=None
) -> list[tuple[str, list[tuple[str, list[Unit]]]]]:
    """The by-gacha-set view: every gacha unit once, under its home set, subdivided by
    rarity - ``[(set_label, [(rarity, [unit, ...]), ...]), ...]``.

    A unit's home is its official Cat Guide set name (The Dynamites, Iron Legion, ...).
    Units the guide doesn't place fall to the banner series that carries them - reruns
    share a series id, so a returning set never repeats. A series whose pool's named
    members mostly share one set (a set's own banner) counts as that set, so its unnamed
    legend joins them; a mixed pool (fest/Platinum umbrella) never claims a unit. What's
    left homes to its smallest carrier's series, labelled by the latest run's text.
    Units in more specific series than [_REGULAR_SERIES_LIMIT] are the shared rare/super
    pool -> one [REGULARS_LABEL] group first (they drop everywhere, so they lead the
    page). Units in no pool (Normal/Special/story cats) are left to the rarity view.

    After the regulars, named sets in dictionary order (lowest unit id), then series
    groups, newest run first.
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

    named: dict[str, list[Unit]] = {}
    homed: dict[int, list[Unit]] = {}
    regulars: list[Unit] = []
    for unit in units:
        if unit.set_name:
            named.setdefault(unit.set_name, []).append(unit)
            continue
        candidates = [sid for sid, ids in members.items() if unit.unit_id in ids]
        if not candidates:
            continue
        specific = [sid for sid in candidates if sid not in umbrella]
        if not specific or len(specific) > _REGULAR_SERIES_LIMIT:
            regulars.append(unit)
            continue
        home = min(specific, key=lambda sid: len(members[sid]))
        if home in series_set:
            named.setdefault(series_set[home], []).append(unit)
        else:
            homed.setdefault(home, []).append(unit)

    sections = [(REGULARS_LABEL, regulars)] if regulars else []
    sections += sorted(named.items(), key=lambda kv: min(u.unit_id for u in kv[1]))
    sections += [
        (latest[sid].name, homed[sid])
        for sid in sorted(homed, key=lambda sid: latest[sid].start, reverse=True)
    ]
    return [(label, _by_rarity(cats)) for label, cats in sections]


def _effective_runs(events) -> list[tuple[GachaEventRow, date, date]]:
    """Schedule runs with overlapping same-name reruns resolved: a rerun supersedes its
    predecessor (permanent banners carry a 2030 sentinel end, so the Platinum Capsules'
    April run really ends the day before the July rerun starts). Sorted by start;
    ends are inclusive."""
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
    """The target picker's banner sections, one row per SCHEDULED RUN, godfat-style: every
    rerun of every gacha, past and future. A recurring name (Platinum/Legend Capsules,
    reruns) gets a separate row per run, each with its own dates, so picking one names an
    exact session. Cats are joined onto rows by banner name from the roll-derived
    catalogue; only a name's newest past row carries them, so ~2000 historical rows stay
    light (a brand-new banner shows without cats until imported).

    ``titles`` maps a run's pool id to its set's display name ([banner_titles]); rows
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
    """Map each banner to every banner (itself included) with an identical roll
    sequence. Same seed + same pool = same pulls, so those banners are
    interchangeable for any plan rolled on them."""
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
    path=None,
    targets=None,
    owned=None,
    guaranteed=None,
    gpath=None,
    gtargets=None,
):
    """One merged A/B table over every selected banner: each cell stacks each banner's
    cat at that shared stream position (à la ubercarry), with rare-dupe switch arrows
    and the plan's path highlighted. Returns ``{"legend": [...], "rows": [...]}``.

    ``path``/``targets`` map a representative banner to the stream indices to light up.
    ``owned`` is the set of cat names you already have, used to flag Uber/Legend cats
    missing from your collection. ``guaranteed`` maps a banner to its guaranteed-uber
    column (godfat's: the uber a guaranteed multi awards when STARTED on that cell);
    banners without a guaranteed multi have none, and when no selected banner has any the
    columns are omitted entirely (``has_guaranteed``). ``gpath``/``gtargets`` light up
    guaranteed-column cells where the plan starts a guaranteed multi.
    """
    path = path or {}
    targets = targets or {}
    gpath = gpath or {}
    gtargets = gtargets or {}
    owned = owned or set()
    groups = _banner_groups(banner_pulls, rerolls, equivalents, guaranteed)

    avail = max((max(g["grid"]) for g in groups if g["grid"]), default=-1) // 2 + 1
    lit = [index for indices in (*path.values(), *gpath.values()) for index in indices]
    needed = max((index // 2 + 1 for index in lit), default=0)
    max_pos = max(min(avail, max(TRACK_ROW_CAP, needed)), 0)

    def entries(index):
        cells = []
        for group in groups:
            tp = group["grid"].get(index)
            if tp is None:
                continue
            outcome = group["graph"].outcome(index)
            switched = bool(outcome and outcome.switched)
            # outcome.cat is the rerolled cat on a dupe, else the normal roll; a dupe also
            # jumps to the other track.
            cat = outcome.cat if outcome else tp.cat
            rarity = str(outcome.rarity if outcome else tp.rarity)
            cells.append(
                {
                    "tag": group["tag"],
                    "cat": cat,
                    "rarity": rarity,
                    "switch": switched,
                    "arrow": {"to": _pos_label(outcome.next_position)} if switched else None,
                    "on_path": index in path.get(group["rep"], ()),
                    "target": index in targets.get(group["rep"], ()),
                    "new": rarity in _VALUABLE_RARITIES and cat not in owned,
                }
            )
        return cells

    def guaranteed_entries(index):
        cells = []
        for group in groups:
            tp = group["guaranteed"].get(index)
            if tp is None or not tp.cat:  # no guarantee on this banner, or an empty uber pool
                continue
            rarity = str(tp.rarity)
            cells.append(
                {
                    "tag": group["tag"],
                    "cat": tp.cat,
                    "rarity": rarity,
                    "on_path": index in gpath.get(group["rep"], ()),
                    "target": index in gtargets.get(group["rep"], ()),
                    "new": rarity in _VALUABLE_RARITIES and tp.cat not in owned,
                }
            )
        return cells

    has_guaranteed = any(group["guaranteed"] for group in groups)
    rows = [
        {
            "pos": pos,
            "a": entries(2 * (pos - 1)),
            "b": entries(2 * (pos - 1) + 1),
            "ga": guaranteed_entries(2 * (pos - 1)) if has_guaranteed else [],
            "gb": guaranteed_entries(2 * (pos - 1) + 1) if has_guaranteed else [],
        }
        for pos in range(1, max_pos + 1)
    ]
    legend = [{"tag": g["tag"], "names": g["names"]} for g in groups]
    return {"legend": legend, "rows": rows, "has_guaranteed": has_guaranteed}


def plan_highlight(option, equivalents):
    """Stream indices to light up for one plan, keyed by representative banner. A normal
    pull lights its track cell; a guaranteed pull lights the guaranteed COLUMN at the
    multi's first roll (where godfat shows the awarded uber), returned separately as
    ``gpath``/``gtargets``."""
    path: dict[str, set[int]] = {}
    targets: dict[str, set[int]] = {}
    gpath: dict[str, set[int]] = {}
    gtargets: dict[str, set[int]] = {}
    for pull in option.plan.pulls:
        rep = _representative(pull.banner_id, equivalents)
        into_path, into_targets = (gpath, gtargets) if pull.guaranteed else (path, targets)
        into_path.setdefault(rep, set()).add(pull.position)
        if pull.cat in option.targets:
            into_targets.setdefault(rep, set()).add(pull.position)
    return path, targets, gpath, gtargets


def plan_summary(plans, equivalents):
    """Per-option summary: targets, cost, and per-banner-leg rolls + cat sequence."""
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
                    "names": sorted(equivalents.get(leg.banner_id, [leg.banner_id])),
                    "new_banner": leg.banner_id != last_banner,
                    "kind": leg.kind,
                    "cost": leg.cost,
                    "tickets": tickets,
                    "rolls": rolls,
                    "cats": [pull.cat for pull in leg.pulls],
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
    prefer="tickets",
    banner_limits=None,
    owned=None,
):
    """Every non-empty target subset and its best plan, biggest-then-cheapest, with the
    unreachable subsets listed after. Reachable ones carry the steps + highlighted track
    to render on demand; unreachable ones are flagged so the UI can say "Not found"."""
    graphs = build_graphs(pulls, guaranteed_pulls, rerolls)
    start = State(0, tickets, catfood // CATFOOD_PER_DRAW, frozenset())
    found = solve_subsets(
        graphs,
        targets,
        start,
        multis=multis,
        ticket_value=ticket_value,
        prefer=prefer,
        banner_limits=banner_limits,
    )
    found_keys = {sp.targets for sp in found}
    solutions = []
    for sp in found:
        path, target_idx, gpath, gtargets = plan_highlight(sp, equivalents)
        solution = plan_summary([sp], equivalents)[0]
        solution["found"] = True
        solution["track"] = build_tracks(
            pulls,
            rerolls,
            equivalents,
            path,
            target_idx,
            owned,
            guaranteed_pulls,
            gpath,
            gtargets,
        )
        solutions.append(solution)
    items = sorted(set(targets))
    for size in range(len(items), 0, -1):
        for combo in combinations(items, size):
            if frozenset(combo) not in found_keys:
                solutions.append({"targets": sorted(combo), "found": False})
    return solutions


def unit_match_report() -> tuple[dict[str, int], list[str]]:
    """Match every scraped cat name against the canonical catalogue; return the
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
    """Fold each provisional unit into its now-canonical namesake: move its cats and
    owned/wishlist flags onto the canonical unit, then delete the stand-in. Returns the count
    merged and the names of any provisionals with no canonical match yet (left in place)."""
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
    """Add scraped cats and their banner membership to the catalogue; return new-cat count."""
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
