import json
from dataclasses import asdict
from pathlib import Path

from neko.godfat import TrackPull
from neko.models import Rarity


class RollCache:
    """JSON-on-disk cache of parsed rolls, keyed by (seed, event, count)."""

    def __init__(self, directory: Path) -> None:
        self._dir = Path(directory)

    def _path(self, seed: int, event: str, count: int) -> Path:
        return self._dir / f"{seed}_{event}_{count}.json"

    def load(self, seed: int, event: str, count: int) -> list[TrackPull] | None:
        path = self._path(seed, event, count)
        if not path.exists():
            return None
        rows = json.loads(path.read_text(encoding="utf-8"))
        return [TrackPull(r["position"], r["track"], r["cat"], Rarity(r["rarity"])) for r in rows]

    def save(self, seed: int, event: str, count: int, pulls: list[TrackPull]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        rows = [asdict(pull) for pull in pulls]
        self._path(seed, event, count).write_text(json.dumps(rows), encoding="utf-8")
