import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from neko.gachadata import GachaEventRow
from neko.search import Multi

_CONFIG_PATH = Path(__file__).parent / "data" / "gacha_configs.json"


@dataclass(frozen=True, slots=True)
class GachaRule:
    """The multi-roll options for a group of banners. A ``step_up`` rule is for step-up
    events (the forced 3/5/7 ladder); others match banners whose name contains any of
    the keywords (empty = matches anything)."""

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
    """First rule fitting the event. A step_up rule matches step-up events only (the
    schedule flag decides - marketing names rarely say "step up"). An ordinary rule
    matches when any keyword appears in the banner name (empty keywords match any) -
    but never a step-up event: in game the forced 3/5/7 ladder REPLACES the ordinary
    multis, so an 11-roll there is impossible."""
    lowered = name.lower()
    for rule in rules:
        if rule.step_up:
            if step_up:
                return rule.multis
        elif not step_up and (not rule.keywords or any(kw in lowered for kw in rule.keywords)):
            return rule.multis

    return None


def multi_configs(
    events: Iterable[GachaEventRow], rules: Iterable[GachaRule] | None = None
) -> dict[str, tuple[Multi, ...]]:
    """Map each event id to its multi-roll options. The schedule's flags pick which kind
    of rule to use - a guaranteed event is NOT treated as step-up even when both flags
    are set (godfat's pool.guaranteed_rolls checks guaranteed first)."""
    rules = list(rules) if rules is not None else load_rules()
    configs = {}

    for event in events:
        step_up = event.step_up and not event.guaranteed
        multis = match_rule(event.name, rules, step_up=step_up)

        if multis is not None:
            configs[event.event_id] = multis

    return configs
