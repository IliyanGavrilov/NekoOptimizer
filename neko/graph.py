from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from neko.models import Rarity, TrackPull


def stream_index(position: int, track: str) -> int:
    """Map a 1-based (position, track) to its index in the shared seed stream."""
    return 2 * (position - 1) + int(track == "B")


@dataclass(frozen=True, slots=True)
class Outcome:
    """Result of pulling a banner at one stream position. ``seed`` is the RNG state
    after the pull (the reroll's on a dupe) - what "apply plan" advances to when this
    is the plan's final draw."""

    cat: str
    rarity: Rarity
    next_position: int
    switched: bool
    seed: int = 0


class BannerGraph:
    """A banner's pulls indexed by shared-seed position, with track switches resolved.

    A rare cell's result depends on the path: repeating the cat obtained just before
    it rerolls and jumps the track. ``resolve`` takes that previous cat; ``outcome``
    is the static straight-chain view (the previous cat is the same-track
    predecessor's nominal roll), which is what godfat renders."""

    def __init__(
        self,
        banner_id: str,
        pulls: Iterable[TrackPull],
        guaranteed: Iterable[TrackPull] = (),
        rerolls: Iterable[TrackPull] = (),
        guaranteed_rerolls: Iterable[TrackPull] = (),
    ) -> None:
        self.banner_id = banner_id
        self._pulls: dict[int, TrackPull] = {
            stream_index(pull.position, pull.track): pull for pull in pulls
        }
        # The cat a dupe arrival at a position rerolls into; `realized` ones are on the
        # straight chains (godfat's R cells), the rest only trigger on other paths.
        self._rerolls: dict[int, TrackPull] = {
            stream_index(pull.position, pull.track): pull for pull in rerolls
        }
        # Guaranteed columns are keyed by the multi's FIRST roll (godfat semantics): the
        # uber awarded when a guaranteed multi STARTS here - one column for a clean
        # arrival, one for a dupe arrival (the reroll's chain ends elsewhere). The true
        # landing depends on the multi's length (the search walks the chain and lands
        # one step past the final roll, track flipped), so next_position is a placeholder.
        self._guaranteed: dict[int, Outcome] = self._column(guaranteed)
        self._guaranteed_rerolls: dict[int, Outcome] = self._column(guaranteed_rerolls)

    @staticmethod
    def _column(pulls: Iterable[TrackPull]) -> dict[int, Outcome]:
        return {
            stream_index(pull.position, pull.track): Outcome(
                pull.cat,
                pull.rarity,
                stream_index(pull.position, pull.track) + 1,
                switched=False,
                seed=pull.seed,
            )
            for pull in pulls
        }

    def resolve(self, position: int, last_cat: str = "") -> Outcome | None:
        """The pull at ``position`` on a path whose previous pull obtained ``last_cat``:
        a rare repeating it rerolls (the extra steps push the continue point past the
        usual +2, flipping the track); anything else rolls the nominal cat."""
        pull = self._pulls.get(position)
        if pull is None:
            return None
        if pull.rarity is Rarity.RARE and pull.cat != "" and pull.cat == last_cat:
            reroll = self._rerolls.get(position)
            if reroll is None:
                # No reroll data for this cell: keep the dupe's name, assume one step.
                return Outcome(pull.cat, pull.rarity, position + 3, True, pull.seed)
            return Outcome(
                reroll.cat, reroll.rarity, position + 2 + (reroll.steps or 1), True, reroll.seed
            )
        return Outcome(pull.cat, pull.rarity, position + 2, False, pull.seed)

    def outcome(self, position: int) -> Outcome | None:
        """The static straight-chain view of ``position`` (godfat's grid)."""
        prev = self._pulls.get(position - 2)
        return self.resolve(position, prev.cat if prev else "")

    def reroll(self, position: int) -> Outcome | None:
        """The conditional reroll at ``position``: what a dupe arrival there obtains,
        whether or not the straight chain realizes it."""
        reroll = self._rerolls.get(position)
        if reroll is None:
            return None
        return Outcome(
            reroll.cat, reroll.rarity, position + 2 + (reroll.steps or 1), True, reroll.seed
        )

    def realized(self, position: int) -> bool:
        """Whether the straight play chains actually hit the reroll at ``position``
        (godfat renders exactly those R cells)."""
        reroll = self._rerolls.get(position)
        return reroll is not None and reroll.realized

    def guaranteed(self, position: int, duped: bool = False) -> Outcome | None:
        """The uber a guaranteed multi started at ``position`` awards; ``duped`` reads
        the column for a start whose first roll arrives as a dupe."""
        column = self._guaranteed_rerolls if duped else self._guaranteed
        return column.get(position)

    def positions(self) -> list[int]:
        return sorted(self._pulls)

    def guaranteed_positions(self, duped: bool = False) -> list[int]:
        return sorted(self._guaranteed_rerolls if duped else self._guaranteed)

    def max_advance(self) -> int:
        """The farthest one pull can move the position: +2 nominal, +2+steps on a dupe."""
        return 2 + max((reroll.steps or 1 for reroll in self._rerolls.values()), default=1)


def build_graphs(
    parsed: Mapping[str, Iterable[TrackPull]],
    guaranteed: Mapping[str, Iterable[TrackPull]] | None = None,
    rerolls: Mapping[str, Iterable[TrackPull]] | None = None,
    guaranteed_rerolls: Mapping[str, Iterable[TrackPull]] | None = None,
) -> list[BannerGraph]:
    guaranteed = guaranteed or {}
    rerolls = rerolls or {}
    guaranteed_rerolls = guaranteed_rerolls or {}
    return [
        BannerGraph(
            banner_id,
            pulls,
            guaranteed.get(banner_id, ()),
            rerolls.get(banner_id, ()),
            guaranteed_rerolls.get(banner_id, ()),
        )
        for banner_id, pulls in parsed.items()
    ]
