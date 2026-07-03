import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from neko.godfat import GachaEvent
from neko.search import Multi

_CONFIG_PATH = Path(__file__).parent / "data" / "gacha_configs.json"


@dataclass(frozen=True, slots=True)
class GachaRule:
    """The multi-roll options for a class of banners. A ``step_up`` rule is for step-up
    events (the forced 3/5/7 ladder); others match banners whose name holds any keyword
    (empty = any)."""

    keywords: tuple[str, ...]
    multis: tuple[Multi, ...]
    step_up: bool = False


def load_rules(path: Path = _CONFIG_PATH) -> list[GachaRule]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        GachaRule(
            tuple(kw.lower() for kw in rule["keywords"]),
            tuple(Multi(m["rolls"], m["cost"], m.get("guaranteed", True)) for m in rule["multis"]),
            rule.get("step_up", False),
        )
        for rule in data["rules"]
    ]


def match_rule(
    name: str, rules: Iterable[GachaRule], step_up: bool = False
) -> tuple[Multi, ...] | None:
    """First rule fitting the event. A step_up rule matches a step-up event (by flag)
    or, for flagless scraper-era events, by its keywords. An ordinary rule matches when
    any keyword appears in the banner name (empty keywords match any) - but never a
    step-up event: in game the forced 3/5/7 ladder REPLACES the ordinary multis, so an
    11-roll there is impossible."""
    lowered = name.lower()
    for rule in rules:
        if rule.step_up:
            if step_up or any(kw in lowered for kw in rule.keywords):
                return rule.multis
        elif not step_up and (not rule.keywords or any(kw in lowered for kw in rule.keywords)):
            return rule.multis
    return None


def multi_configs(
    events: Iterable[GachaEvent], rules: Iterable[GachaRule] | None = None
) -> dict[str, tuple[Multi, ...]]:
    """Map each event id to its multi-roll options. The schedule's flags pick the rule
    class - a guaranteed event is NOT treated as step-up even when both flags are set
    (godfat's pool.guaranteed_rolls checks guaranteed first); scraper-era events without
    flags fall back to name keywords."""
    rules = list(rules) if rules is not None else load_rules()
    configs = {}
    for event in events:
        step_up = bool(getattr(event, "step_up", False)) and not bool(
            getattr(event, "guaranteed", False)
        )
        multis = match_rule(event.name, rules, step_up=step_up)
        if multis is not None:
            configs[event.event_id] = multis
    return configs
