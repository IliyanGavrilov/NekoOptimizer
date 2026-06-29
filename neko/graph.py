from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from neko.godfat import TrackPull
from neko.models import Rarity


def stream_index(position: int, track: str) -> int:
    """Map a 1-based (position, track) to its index in the shared seed stream."""
    return 2 * (position - 1) + int(track == "B")


@dataclass(frozen=True, slots=True)
class Outcome:
    """Result of pulling a banner at one stream position."""

    cat: str
    rarity: Rarity
    next_position: int
    switched: bool


class BannerGraph:
    """A banner's pulls indexed by shared-seed position, with track switches resolved."""

    def __init__(
        self,
        banner_id: str,
        pulls: Iterable[TrackPull],
        guaranteed: Iterable[TrackPull] = (),
        rerolls: Iterable[TrackPull] = (),
    ) -> None:
        self.banner_id = banner_id
        cats: dict[int, str] = {}
        rarities: dict[int, Rarity] = {}
        for pull in pulls:
            index = stream_index(pull.position, pull.track)
            cats[index] = pull.cat
            rarities[index] = pull.rarity
        # The cat you actually obtain when a position's roll is a rare dupe (godfat
        # rerolls it), keyed by the position you rolled from.
        reroll: dict[int, TrackPull] = {
            stream_index(pull.position, pull.track): pull for pull in rerolls
        }
        self._outcomes: dict[int, Outcome] = {}
        for index, cat in cats.items():
            # Consecutive rare dupe rerolls once: +3 (extra step) flips track
            switched = rarities[index] == Rarity.RARE and cats.get(index - 2) == cat
            out = reroll[index] if switched and index in reroll else None
            self._outcomes[index] = Outcome(
                out.cat if out else cat,
                out.rarity if out else rarities[index],
                index + (3 if switched else 2),
                switched,
            )
        # Guaranteed roll: +1 step flips track
        self._guaranteed: dict[int, Outcome] = {}
        for pull in guaranteed:
            index = stream_index(pull.position, pull.track)
            self._guaranteed[index] = Outcome(pull.cat, pull.rarity, index + 1, switched=False)

    def outcome(self, position: int) -> Outcome | None:
        return self._outcomes.get(position)

    def guaranteed(self, position: int) -> Outcome | None:
        return self._guaranteed.get(position)

    def positions(self) -> list[int]:
        return sorted(self._outcomes)


def build_graphs(
    parsed: Mapping[str, Iterable[TrackPull]],
    guaranteed: Mapping[str, Iterable[TrackPull]] | None = None,
    rerolls: Mapping[str, Iterable[TrackPull]] | None = None,
) -> list[BannerGraph]:
    guaranteed = guaranteed or {}
    rerolls = rerolls or {}
    return [
        BannerGraph(banner_id, pulls, guaranteed.get(banner_id, ()), rerolls.get(banner_id, ()))
        for banner_id, pulls in parsed.items()
    ]
