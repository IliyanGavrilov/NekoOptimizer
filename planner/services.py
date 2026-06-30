import asyncio
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path

from neko.cache import RollCache
from neko.godfat import BannerRolls
from neko.graph import stream_index
from neko.scraper import (
    DEFAULT_COUNT,
    ScrapeResult,
    scrape_active,
    scrape_catalogue,
    scrape_selected,
)
from planner.models import Banner, Cat

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


def track_rows(leg_pulls, grid, targets, owned):
    """Two-track (A/B) rows over the window a leg's path covers.

    ``leg_pulls`` are one leg's Pulls (``Pull.position`` is a shared-stream index);
    ``grid`` maps stream index -> TrackPull for that banner. Returns
    ``[{"pos", "a", "b"}, ...]`` where each cell is ``None`` (empty slot) or
    ``{"cat", "rarity", "on_path", "target", "switch", "unowned"}``.
    """
    path = [pull.position for pull in leg_pulls]
    pull_at = {pull.position: pull for pull in leg_pulls}
    # A switch lands on an index whose track flips from the previous path step
    # (godfat's +1 guaranteed / +3 rare-dupe half-steps cross tracks; +2 stays).
    switched = {idx for prev, idx in zip(path, path[1:], strict=False) if prev % 2 != idx % 2}

    def cell(index):
        pull = pull_at.get(index)
        base = grid.get(index)
        if pull is None and base is None:
            return None
        cat = pull.cat if pull else base.cat
        rarity = pull.rarity if pull else base.rarity
        return {
            "cat": cat,
            "rarity": str(rarity),
            "on_path": pull is not None,
            "target": pull is not None and cat in targets,
            "switch": index in switched,
            "unowned": pull is not None and cat not in owned,
        }

    positions = [index // 2 + 1 for index in path]
    return [
        {"pos": pos, "a": cell(2 * (pos - 1)), "b": cell(2 * (pos - 1) + 1)}
        for pos in range(min(positions), max(positions) + 1)
    ]


def cost_label(tickets, catfood):
    """Spell out a plan's price in both currencies; pulls are ticket-funded first,
    so a plan can be pure tickets, pure catfood, or a mix."""
    parts = []
    if tickets:
        parts.append(f"{tickets} ticket{'s' if tickets != 1 else ''}")
    if catfood:
        parts.append(f"{catfood} catfood")
    return " + ".join(parts) or "free"


def plan_views(plans, banner_pulls, equivalents, owned):
    """Render model: each plan option with per-leg A/B track tables."""
    grids = {
        name: {stream_index(pull.position, pull.track): pull for pull in pulls}
        for name, pulls in banner_pulls.items()
    }
    views = []
    for option in plans:
        segments = []
        last_banner = None
        for leg in option.plan.legs:
            segments.append(
                {
                    "names": equivalents.get(leg.banner_id, [leg.banner_id]),
                    "new_banner": leg.banner_id != last_banner,
                    "kind": leg.kind,
                    "cost": leg.cost,
                    "pulls": len(leg.pulls),
                    "rows": track_rows(
                        leg.pulls, grids.get(leg.banner_id, {}), option.targets, owned
                    ),
                }
            )
            last_banner = leg.banner_id
        views.append(
            {
                "targets": sorted(option.targets),
                "cost": option.plan.cost,
                "tickets_used": option.plan.tickets_used,
                "cost_label": cost_label(option.plan.tickets_used, option.plan.cost),
                "cats": "|".join(option.plan.cats),
                "segments": segments,
            }
        )
    return views


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
            banner.cats.add(cat)
    return created
