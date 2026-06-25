import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from neko.godfat import GachaEvent
from neko.search import Multi

_CONFIG_PATH = Path(__file__).parent / "data" / "gacha_configs.json"


@dataclass(frozen=True, slots=True)
class GachaRule:
    """The multi-roll options for banners whose name holds any keyword (empty = any)."""

    keywords: tuple[str, ...]
    multis: tuple[Multi, ...]


def load_rules(path: Path = _CONFIG_PATH) -> list[GachaRule]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        GachaRule(
            tuple(kw.lower() for kw in rule["keywords"]),
            tuple(Multi(m["rolls"], m["cost"], m.get("guaranteed", True)) for m in rule["multis"]),
        )
        for rule in data["rules"]
    ]


def match_rule(name: str, rules: Iterable[GachaRule]) -> tuple[Multi, ...] | None:
    """First rule whose keyword appears in the banner name (empty keywords match any)."""
    lowered = name.lower()
    for rule in rules:
        if not rule.keywords or any(kw in lowered for kw in rule.keywords):
            return rule.multis
    return None


def multi_configs(
    events: Iterable[GachaEvent], rules: Iterable[GachaRule] | None = None
) -> dict[str, tuple[Multi, ...]]:
    """Map each event id to its multi-roll options, matched by banner name."""
    rules = list(rules) if rules is not None else load_rules()
    configs = {}
    for event in events:
        multis = match_rule(event.name, rules)
        if multis is not None:
            configs[event.event_id] = multis
    return configs
