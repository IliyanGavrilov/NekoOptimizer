import json
from pathlib import Path

from neko.godfat import BannerRolls, TrackPull
from neko.graph import build_graphs, stream_index
from neko.models import CATFOOD_PER_DRAW, Rarity, State
from neko.search import Multi, astar

# A real bc.godfat capture: seed 1893568593, "Trixi joins the Capsules" (2026-06-26_1052),
# 1000 rolls. Trixi is a guaranteed-only uber here (first normal roll at position 193), so
# the whole guaranteed-multi + reroll pipeline runs against genuine data, not synthetic cells.
FIXTURE = Path(__file__).parent / "fixtures" / "godfat_seed_1893568593_trixi.json"
BANNER = "trixi"
TRIXI = "Trixi the Merc"
GUARANTEED_MULTI = Multi(11, 1500, guaranteed=True)


def load_rolls() -> BannerRolls:
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))

    def pulls(key):
        return [
            TrackPull(r["position"], r["track"], r["cat"], Rarity(r["rarity"])) for r in data[key]
        ]

    return BannerRolls(pulls("pulls"), pulls("guaranteed"), pulls("rerolls"))


def graph():
    rolls = load_rolls()
    graphs = build_graphs(
        {BANNER: rolls.pulls}, {BANNER: rolls.guaranteed}, {BANNER: rolls.rerolls}
    )
    return graphs[0]


def test_real_capture_has_the_expected_shape():
    rolls = load_rolls()
    counts = (len(rolls.pulls), len(rolls.guaranteed), len(rolls.rerolls))
    assert counts == (1000, 999, 18)


def test_real_capture_first_roll():
    rolls = load_rolls()
    assert (rolls.pulls[0].cat, rolls.pulls[0].rarity) == ("Stilts Cat", Rarity.RARE)


def test_real_rare_dupe_rerolls_to_a_clean_name_and_switches_track():
    # 60B nominally repeats 59B (Welterweight Cat), so godfat rerolls it to Onmyoji Cat and
    # jumps a track. Guards both the stray-"R" parse bug and the pre-reroll dupe display.
    outcome = graph().outcome(stream_index(60, "B"))
    assert outcome.cat == "Onmyoji Cat"
    assert outcome.switched is True
    assert outcome.next_position == stream_index(60, "B") + 3


def test_trixi_only_rolls_normally_deep_into_the_stream():
    normal = [p.position for p in load_rolls().pulls if p.cat == TRIXI]
    assert min(normal) == 193


def test_guaranteed_multi_lands_trixi_far_earlier_than_the_normal_roll():
    # The plan repositions with single pulls, then one guaranteed 11-roll obtains Trixi -
    # well before its position-193 normal roll, which is the whole point of the guaranteed.
    start = State(0, 40, 1500 // CATFOOD_PER_DRAW, frozenset())
    result = astar([graph()], {TRIXI}, start, multis={BANNER: [GUARANTEED_MULTI]})
    trixi_pull = result.pulls[-1]
    assert trixi_pull.cat == TRIXI
    assert trixi_pull.position < 193


def test_trixi_comes_from_the_guaranteed_leg_not_a_single_pull():
    start = State(0, 40, 1500 // CATFOOD_PER_DRAW, frozenset())
    result = astar([graph()], {TRIXI}, start, multis={BANNER: [GUARANTEED_MULTI]})
    trixi_leg = next(leg for leg in result.legs if any(p.cat == TRIXI for p in leg.pulls))
    assert "guaranteed" in trixi_leg.kind


def test_without_a_multi_config_a_cheap_budget_cannot_reach_trixi():
    # Trixi's first normal roll is 193 pulls in; a small budget only reaches it via the
    # guaranteed. Drop the multi and a modest budget can no longer collect it.
    start = State(0, 40, 1500 // CATFOOD_PER_DRAW, frozenset())
    assert astar([graph()], {TRIXI}, start) is None
