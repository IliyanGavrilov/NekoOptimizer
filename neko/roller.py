# Rolls banners from the committed schedule/pools/catalogue with our own engine.

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from neko.bcdata import load_records
from neko.gacha import GachaRule, load_rules, multi_configs
from neko.gachadata import GachaEventRow, build_banner, load_events, load_pools
from neko.models import BannerRolls, TrackPull
from neko.roll import roll_banner
from neko.search import Multi

DEFAULT_COUNT = 100

# A picker selection can pin an exact run as "YYYY-MM-DD|name" (the run's start date).
_DATED = re.compile(r"^(\d{4}-\d{2}-\d{2})\|")


@dataclass(frozen=True, slots=True)
class RollResult:
    """The rolled banners plus each banner's multi-roll options and run dates."""

    banners: dict[str, BannerRolls]
    multis: dict[str, tuple[Multi, ...]]
    dates: dict[str, tuple[date, date]] = field(default_factory=dict)


def active_events(
    events: Iterable[GachaEventRow], today: date | None = None
) -> list[GachaEventRow]:
    today = today or date.today()
    return [event for event in events if event.start <= today <= event.end]


def units_from_records(records: Iterable[Mapping] | None = None) -> dict[int, tuple[str, str]]:
    """The catalogue as {unit_id: (name, rarity)} for pool resolution."""
    records = records if records is not None else load_records()
    return {r["id"]: (r["name"], r["rarity"]) for r in records}


def _current_run(runs: list[GachaEventRow], today: date) -> GachaEventRow | None:
    """The run a bare banner name means: live today, else the latest already started,
    else the earliest upcoming. Never a future rerun over one that's running now - a
    recurring name (e.g. the Platinum Capsules) reruns with a DIFFERENT pool."""
    if not runs:
        return None
    live = [e for e in runs if e.start <= today <= e.end]
    if live:
        return max(live, key=lambda e: e.start)
    started = [e for e in runs if e.start <= today]
    if started:
        return max(started, key=lambda e: e.start)
    return min(runs, key=lambda e: e.start)


def select_events(
    events: Iterable[GachaEventRow], selections: Iterable[str], today: date | None = None
) -> list[GachaEventRow]:
    """Resolve picker selections to concrete runs. "YYYY-MM-DD|name" pins the run of
    ``name`` starting that day (the picker posts per-run rows); a bare name resolves via
    [_current_run]. Unknown selections are dropped."""
    today = today or date.today()
    by_name: dict[str, list[GachaEventRow]] = {}
    for event in events:
        by_name.setdefault(event.name, []).append(event)
    chosen: dict[str, GachaEventRow] = {}
    for selection in selections:
        dated = _DATED.match(selection)
        run = None
        if dated:
            name = selection[dated.end() :]
            start = date.fromisoformat(dated.group(1))
            run = next((e for e in by_name.get(name, ()) if e.start == start), None)
        else:
            name = selection
        if run is None:  # bare name, or a pinned date the (resynced) schedule lost
            run = _current_run(by_name.get(name, []), today)
        if run is not None:
            chosen[run.event_id] = run
    return list(chosen.values())


def _guaranteed_rolls(event: GachaEventRow) -> int:
    """godfat's pool.guaranteed_rolls: 11 for a guaranteed event, 15 for a step-up, else 0
    - most banners run NO guaranteed multi, so their guaranteed column must stay empty."""
    if event.guaranteed:
        return 11
    if event.step_up:
        return 15
    return 0


def _event_multis(multis: tuple[Multi, ...], guaranteed_rolls: int) -> tuple[Multi, ...]:
    """The config's multis adjusted to the event: a multi only awards the guaranteed uber
    when the event actually runs a guarantee of that length (the config matches by name
    and can't know)."""
    return tuple(
        m if not m.guaranteed or m.rolls == guaranteed_rolls else Multi(m.rolls, m.cost, False)
        for m in multis
    )


def _result(
    seed: int,
    events: Iterable[GachaEventRow],
    pools: Mapping[int, list[int]],
    units: Mapping[int, tuple[str, str]],
    count: int,
    rules: Iterable[GachaRule],
) -> RollResult:
    """Roll each event and key it by banner name, keeping a recurring banner's latest run."""
    latest: dict[str, GachaEventRow] = {}
    for event in events:
        current = latest.get(event.name)
        if current is None or event.start > current.start:
            latest[event.name] = event
    configs = multi_configs(latest.values(), rules)
    banners, multis, dates = {}, {}, {}
    for name, event in latest.items():
        banner = build_banner(event, pools, units)
        guaranteed_rolls = _guaranteed_rolls(event)
        banners[name] = roll_banner(seed, banner, count, guaranteed_rolls=guaranteed_rolls)
        if event.event_id in configs:
            multis[name] = _event_multis(configs[event.event_id], guaranteed_rolls)
        dates[name] = (event.start, event.end)
    return RollResult(banners, multis, dates)


def _load(events, pools, units, rules):
    """Fill any omitted data source from the committed files / defaults."""
    return (
        events if events is not None else load_events(),
        pools if pools is not None else load_pools(),
        units if units is not None else units_from_records(),
        list(rules) if rules is not None else load_rules(),
    )


def roll_active(
    seed: int,
    *,
    count: int = DEFAULT_COUNT,
    today: date | None = None,
    events: Iterable[GachaEventRow] | None = None,
    pools: Mapping[int, list[int]] | None = None,
    units: Mapping[int, tuple[str, str]] | None = None,
    rules: Iterable[GachaRule] | None = None,
) -> RollResult:
    """Roll the banners active on ``today`` (defaults to the real date)."""
    events, pools, units, rules = _load(events, pools, units, rules)
    return _result(seed, active_events(events, today), pools, units, count, rules)


def roll_selected(
    seed: int,
    names: Iterable[str],
    *,
    count: int = DEFAULT_COUNT,
    today: date | None = None,
    events: Iterable[GachaEventRow] | None = None,
    pools: Mapping[int, list[int]] | None = None,
    units: Mapping[int, tuple[str, str]] | None = None,
    rules: Iterable[GachaRule] | None = None,
) -> RollResult:
    """Roll the selected banners: each "start|name" its pinned run, each bare name its
    current run (see [select_events])."""
    events, pools, units, rules = _load(events, pools, units, rules)
    return _result(seed, select_events(events, names, today), pools, units, count, rules)


def catalogue_banners(
    *,
    events: Iterable[GachaEventRow] | None = None,
    pools: Mapping[int, list[int]] | None = None,
    units: Mapping[int, tuple[str, str]] | None = None,
) -> RollResult:
    """Every scheduled banner's cats straight from its latest run's pool - the catalogue
    needs who CAN drop on a banner, not a rolled sample, so no seed and no rolling."""
    events, pools, units, _ = _load(events, pools, units, [])
    latest: dict[str, GachaEventRow] = {}
    for event in events:
        current = latest.get(event.name)
        if current is None or event.start > current.start:
            latest[event.name] = event
    banners, dates = {}, {}
    for name, event in latest.items():
        banner = build_banner(event, pools, units)
        cats = [
            TrackPull(1, "A", cat, rarity) for rarity, pool in banner.pools.items() for cat in pool
        ]
        banners[name] = BannerRolls(cats, [])
        dates[name] = (event.start, event.end)
    return RollResult(banners, {}, dates)
