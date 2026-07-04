import json
from pathlib import Path

from neko.graph import build_graphs, stream_index
from neko.models import CATFOOD_PER_DRAW, BannerRolls, Rarity, State, TrackPull
from neko.search import Multi, astar

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


def local_banner():
    from neko.bcdata import load_records
    from neko.gachadata import build_banner, load_events, load_pools

    units = {r["id"]: (r["name"], r["rarity"]) for r in load_records()}
    trixi = next(e for e in load_events() if e.event_id == "2026-06-26_1052")
    return build_banner(trixi, load_pools(), units)


def graph():
    from neko.roll import roll_banner

    rolls = roll_banner(1893568593, local_banner(), 1000, guaranteed_rolls=11)
    graphs = build_graphs(
        {BANNER: rolls.pulls},
        {BANNER: rolls.guaranteed},
        {BANNER: rolls.rerolls},
        {BANNER: rolls.guaranteed_rerolls},
    )
    return graphs[0]


def test_local_roll_reproduces_the_capture_byte_for_byte():
    from neko.roll import roll_banner

    fixture = load_rolls()
    count = max(p.position for p in fixture.pulls)
    mine = roll_banner(1893568593, local_banner(), count, guaranteed_rolls=1)

    def cells(pulls):
        return sorted((p.position, p.track, p.cat) for p in pulls)

    assert cells(mine.pulls) == cells(fixture.pulls)
    assert cells(p for p in mine.rerolls if p.realized) == cells(fixture.rerolls)
    got = {(p.position, p.track): p.cat for p in mine.guaranteed}
    assert all(got[(p.position, p.track)] == p.cat for p in fixture.guaranteed)


def test_trixi_banner_rolls_without_a_guarantee():
    from neko.gachadata import load_events
    from neko.roller import roll_selected

    trixi = next(e for e in load_events() if e.event_id == "2026-06-26_1052")
    assert (trixi.guaranteed, trixi.step_up) == (False, False)
    res = roll_selected(1893568593, [trixi.name], count=30)
    assert res.banners[trixi.name].guaranteed == []
    assert all(not m.guaranteed for m in res.multis.get(trixi.name, ()))


def test_real_capture_has_the_expected_shape():
    rolls = load_rolls()
    counts = (len(rolls.pulls), len(rolls.guaranteed), len(rolls.rerolls))
    assert counts == (1000, 999, 18)


def test_real_capture_first_roll():
    rolls = load_rolls()
    assert (rolls.pulls[0].cat, rolls.pulls[0].rarity) == ("Stilts Cat", Rarity.RARE)


def test_real_rare_dupe_rerolls_to_a_clean_name_and_switches_track():
    outcome = graph().outcome(stream_index(60, "B"))
    assert outcome.cat == "Onmyoji Cat"
    assert outcome.switched is True
    assert outcome.next_position == stream_index(60, "B") + 3


def test_bounce_path_rerolls_62a_again_but_only_on_that_path():
    g = graph()
    sixty_b = g.outcome(stream_index(60, "B"))
    assert (sixty_b.cat, sixty_b.next_position) == ("Onmyoji Cat", stream_index(62, "A"))
    bounced = g.resolve(sixty_b.next_position, sixty_b.cat)
    assert (bounced.cat, bounced.switched) == ("Pirate Cat", True)
    assert bounced.next_position == stream_index(63, "B")
    straight = g.outcome(stream_index(62, "A"))
    assert (straight.cat, straight.switched) == ("Onmyoji Cat", False)
    assert g.realized(stream_index(62, "A")) is True


def test_trixi_only_rolls_normally_deep_into_the_stream():
    normal = [p.position for p in load_rolls().pulls if p.cat == TRIXI]
    assert min(normal) == 193


def test_guaranteed_multi_lands_trixi_far_earlier_than_the_normal_roll():
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
    start = State(0, 40, 1500 // CATFOOD_PER_DRAW, frozenset())
    assert astar([graph()], {TRIXI}, start) is None
