import asyncio
from collections.abc import Iterable, Mapping
from datetime import date
from itertools import combinations
from pathlib import Path

from neko.cache import RollCache
from neko.catalogue import match_names, name_index
from neko.godfat import BannerRolls
from neko.graph import BannerGraph, build_graphs, stream_index
from neko.models import CATFOOD_PER_DRAW, State
from neko.scraper import (
    DEFAULT_COUNT,
    ScrapeResult,
    scrape_active,
    scrape_catalogue,
    scrape_selected,
)
from neko.subsets import solve_subsets
from planner.models import Banner, Cat, Unit

_CACHE = RollCache(Path("rollcache"))

RARITY_ORDER = ["Normal", "Rare", "Super Rare", "Uber Super Rare", "Legend Rare"]

# Platinum/Legend run on scarce tickets, not catfood, so the optimizer treats them as
# info-only: capped (0 by default) rather than modelled as ordinary catfood gacha.
_CAPPED_KEYWORDS = ("platinum", "legend")


def capped_banner_limits(names: Iterable[str], cap: int) -> dict[str, int]:
    """Cap pulls on Platinum/Legend banners (matched by name) at `cap`."""
    return {name: cap for name in names if any(kw in name.lower() for kw in _CAPPED_KEYWORDS)}


def fetch_banners(seed: int, count: int = DEFAULT_COUNT) -> ScrapeResult:
    """Scrape the active banners for a seed (blocking wrapper around the async scraper)."""
    return asyncio.run(scrape_active(seed, count=count, cache=_CACHE))


def fetch_catalogue(seed: int) -> ScrapeResult:
    """Scrape every banner for a seed (blocking wrapper), to broaden the catalogue."""
    return asyncio.run(scrape_catalogue(seed, cache=_CACHE))


def fetch_for_banners(seed: int, names: Iterable[str], count: int = DEFAULT_COUNT) -> ScrapeResult:
    """Scrape just the chosen banners for a seed (blocking wrapper)."""
    return asyncio.run(scrape_selected(seed, names, count=count, cache=_CACHE))


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


def catalogue(
    cats: Iterable[Cat], reverse_rarity: bool = False
) -> list[tuple[str, list[tuple[str, list[Cat]]]]]:
    """Section cats by banner, then by rarity within each banner.

    Returns ``[(banner_name, [(rarity, [cat, ...]), ...]), ...]``; cats with no
    banner are collected under 'Other'. Cats in several banners appear in each.
    Rarity runs cheapest-to-rarest, or rarest-first when ``reverse_rarity``.
    """
    banners: dict[str, list[Cat]] = {}
    other: list[Cat] = []
    for cat in cats:
        names = [banner.name for banner in cat.banners.all()]
        for name in names:
            banners.setdefault(name, []).append(cat)
        if not names:
            other.append(cat)
    sections = [(name, _by_rarity(banners[name], reverse_rarity)) for name in sorted(banners)]
    if other:
        sections.append(("Other", _by_rarity(other, reverse_rarity)))
    return sections


def dated_catalogue(
    cats: Iterable[Cat], today: date | None = None, reverse_rarity: bool = False
) -> list[tuple[str, list]]:
    """Split the catalogue into date-ordered groups for a less crowded page.

    Returns ``[(group_label, [(banner, (start, end), [(rarity, [cat, ...])])])]``
    with three possible groups: active/upcoming banners (earliest date first),
    past banners (most recent first), and undated/bannerless cats (``None`` dates).
    Empty groups are dropped.
    """
    today = today or date.today()
    by_name: dict[str, list[Cat]] = {}
    other: list[Cat] = []
    for cat in cats:
        names = [banner.name for banner in cat.banners.all()]
        for name in names:
            by_name.setdefault(name, []).append(cat)
        if not names:
            other.append(cat)

    banners = {b.name: b for b in Banner.objects.filter(name__in=by_name)}
    now, upcoming, past, undated = [], [], [], []
    for name in by_name:
        banner = banners.get(name)
        if banner is None or banner.end is None:
            undated.append(name)
        elif banner.end < today:
            past.append(name)
        elif banner.start <= today:
            now.append(name)
        else:
            upcoming.append(name)
    now.sort(key=lambda name: banners[name].start)
    upcoming.sort(key=lambda name: banners[name].start)
    past.sort(key=lambda name: banners[name].start, reverse=True)
    undated.sort()

    def nest(names: list[str]):
        return [
            (
                name,
                (banners[name].start, banners[name].end),
                _by_rarity(by_name[name], reverse_rarity),
            )
            for name in names
        ]

    leftovers = nest(undated)
    if other:
        leftovers.append(("Other", None, _by_rarity(other, reverse_rarity)))

    groups = [
        ("Available now", nest(now)),
        ("Upcoming", nest(upcoming)),
        ("Past", nest(past)),
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


def _banner_groups(banner_pulls, rerolls, equivalents):
    """Distinct selected banners (equivalent ones merged), each tagged 1, 2, 3...
    with its stream grid and outcome graph."""
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
            }
        )
    return groups


def build_tracks(banner_pulls, rerolls, equivalents, path=None, targets=None, pulled=None):
    """One merged A/B table over every selected banner: each cell stacks each banner's
    cat at that shared stream position (à la ubercarry), with rare-dupe switch arrows
    and the plan's path highlighted. Returns ``{"legend": [...], "rows": [...]}``.

    ``path``/``targets`` map a representative banner to the stream indices to light up;
    ``pulled`` maps those indices to the plan's actual pull there (a guaranteed uber differs
    from the position's normal roll).
    """
    path = path or {}
    targets = targets or {}
    pulled = pulled or {}
    groups = _banner_groups(banner_pulls, rerolls, equivalents)

    avail = max((max(g["grid"]) for g in groups if g["grid"]), default=-1) // 2 + 1
    needed = max((index // 2 + 1 for indices in path.values() for index in indices), default=0)
    max_pos = max(min(avail, max(TRACK_ROW_CAP, needed)), 0)

    def entries(index):
        cells = []
        for group in groups:
            tp = group["grid"].get(index)
            if tp is None:
                continue
            outcome = group["graph"].outcome(index)
            switched = bool(outcome and outcome.switched)
            on_path = index in path.get(group["rep"], ())
            # On the plan's path show the cat it actually pulled: a guaranteed multi obtains an
            # uber, not this position's normal roll. Off-path use outcome.cat (the rerolled cat
            # on a dupe, else the normal roll); a dupe also jumps to the other track.
            plan_pull = pulled.get(group["rep"], {}).get(index) if on_path else None
            if plan_pull is not None:
                cat, rarity = plan_pull.cat, str(plan_pull.rarity)
            else:
                cat = outcome.cat if outcome else tp.cat
                rarity = str(outcome.rarity if outcome else tp.rarity)
            cells.append(
                {
                    "tag": group["tag"],
                    "cat": cat,
                    "rarity": rarity,
                    "switch": switched,
                    "arrow": {"to": _pos_label(outcome.next_position)} if switched else None,
                    "on_path": on_path,
                    "target": index in targets.get(group["rep"], ()),
                }
            )
        return cells

    rows = [
        {"pos": pos, "a": entries(2 * (pos - 1)), "b": entries(2 * (pos - 1) + 1)}
        for pos in range(1, max_pos + 1)
    ]
    legend = [{"tag": g["tag"], "names": g["names"]} for g in groups]
    return {"legend": legend, "rows": rows}


def plan_highlight(option, equivalents):
    """Stream indices to light up for one plan, keyed by representative banner, plus the pull
    the plan made at each - a guaranteed multi obtains an uber that isn't the position's normal
    roll, so the cell must render `pulled`, not the grid."""
    path: dict[str, set[int]] = {}
    targets: dict[str, set[int]] = {}
    pulled: dict[str, dict[int, object]] = {}
    for pull in option.plan.pulls:
        rep = _representative(pull.banner_id, equivalents)
        path.setdefault(rep, set()).add(pull.position)
        pulled.setdefault(rep, {})[pull.position] = pull
        if pull.cat in option.targets:
            targets.setdefault(rep, set()).add(pull.position)
    return path, targets, pulled


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
        path, target_idx, pulled = plan_highlight(sp, equivalents)
        solution = plan_summary([sp], equivalents)[0]
        solution["found"] = True
        solution["track"] = build_tracks(pulls, rerolls, equivalents, path, target_idx, pulled)
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
