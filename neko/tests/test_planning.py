from neko.models import Rarity, TrackPull
from neko.planning import plan
from neko.search import Multi

U = Rarity.UBER_SUPER_RARE


def pulls(*rows):
    return [TrackPull(*row) for row in rows]


def banners():
    return {"x": pulls((1, "A", "Bahamut", U), (2, "A", "Kasli", U))}


def test_reachable_wishlist_returns_one_full_plan():
    result = plan(banners(), {"Bahamut", "Kasli"}, tickets=2, catfood=0)
    assert [sp.targets for sp in result] == [frozenset({"Bahamut", "Kasli"})]


def test_catfood_floor_divides_to_afford_both():
    result = plan(banners(), {"Bahamut", "Kasli"}, tickets=0, catfood=300)
    assert result[0].targets == frozenset({"Bahamut", "Kasli"})


def test_unaffordable_wishlist_falls_back_to_subsets():
    result = plan(banners(), {"Bahamut", "Kasli"}, tickets=0, catfood=299)
    assert [sp.targets for sp in result] == [frozenset({"Bahamut"})]


def test_guaranteed_multi_reaches_otherwise_unreachable_target():
    # The guaranteed column is keyed by the multi's first roll: a 2-roll guarantee begun
    # at 1A rolls Filler, then swaps its final roll for Target.
    result = plan(
        {"x": pulls((1, "A", "Filler", U))},
        {"Target"},
        tickets=0,
        catfood=300,
        guaranteed_pulls={"x": pulls((1, "A", "Target", U))},
        multis={"x": [Multi(rolls=2, cost=300)]},
    )
    assert result[0].targets == frozenset({"Target"})
