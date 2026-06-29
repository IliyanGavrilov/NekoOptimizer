import json
from dataclasses import asdict
from pathlib import Path

from neko.godfat import BannerRolls, TrackPull
from neko.models import Rarity


def _to_pulls(rows: list[dict]) -> list[TrackPull]:
    return [TrackPull(r["position"], r["track"], r["cat"], Rarity(r["rarity"])) for r in rows]


class RollCache:
    """JSON-on-disk cache of a banner's rolls, keyed by (seed, event, count)."""

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def _path(self, seed: int, event: str, count: int) -> Path:
        return self._dir / f"{seed}_{event}_{count}.json"

    def load(self, seed: int, event: str, count: int) -> BannerRolls | None:
        path = self._path(seed, event, count)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return BannerRolls(
            _to_pulls(data["pulls"]),
            _to_pulls(data["guaranteed"]),
            _to_pulls(data.get("rerolls", [])),
        )

    def save(self, seed: int, event: str, count: int, rolls: BannerRolls) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        data = {
            "pulls": [asdict(pull) for pull in rolls.pulls],
            "guaranteed": [asdict(pull) for pull in rolls.guaranteed],
            "rerolls": [asdict(pull) for pull in rolls.rerolls],
        }
        self._path(seed, event, count).write_text(json.dumps(data), encoding="utf-8")
