from neko.godfat import TrackPull
from neko.models import Rarity
from neko.planning import plan

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
