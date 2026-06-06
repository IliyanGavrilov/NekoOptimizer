from neko.models import CATFOOD_PER_DRAW, Banner, Path, Pull, Rarity, State


def make_banner():
    return Banner(
        banner_id="uber_fest",
        name="Uberfest",
        url="https://bc.godfat.org/?seed=1",
        rates={Rarity.RARE: 7000, Rarity.SUPER_RARE: 2500, Rarity.UBER_SUPER_RARE: 500},
        pools={Rarity.RARE: ("Cat", "Tank Cat"), Rarity.UBER_SUPER_RARE: ("Bahamut",)},
    )


def test_total_rate_sums_rates():
    assert make_banner().total_rate() == 10000


def test_pool_returns_cats_for_rarity():
    assert make_banner().pool(Rarity.UBER_SUPER_RARE) == ("Bahamut",)


def test_pool_returns_empty_for_absent_rarity():
    assert make_banner().pool(Rarity.LEGEND_RARE) == ()


def test_equal_states_collapse_when_hashed():
    fields = dict(position=10, tickets_left=5, catfood_draws=8, found=frozenset({"Bahamut"}))
    assert len({State(**fields), State(**fields)}) == 1


def test_state_found_set_affects_identity():
    base = dict(position=0, tickets_left=0, catfood_draws=0)
    assert State(found=frozenset({"A"}), **base) != State(found=frozenset({"A", "B"}), **base)


def test_path_length_counts_pulls():
    path = Path(pulls=(Pull(0, "b", "Cat", Rarity.RARE),), tickets_used=1, catfood_draws_used=0)
    assert len(path) == 1


def test_path_lists_cats_in_order():
    pulls = (Pull(0, "b", "Cat", Rarity.RARE), Pull(1, "b", "Bahamut", Rarity.UBER_SUPER_RARE))
    assert Path(pulls=pulls, tickets_used=2, catfood_draws_used=0).cats == ("Cat", "Bahamut")


def test_path_cost_charges_per_catfood_draw():
    assert Path(pulls=(), tickets_used=0, catfood_draws_used=3).cost == 3 * CATFOOD_PER_DRAW


def test_path_cost_is_zero_without_catfood():
    assert Path(pulls=(), tickets_used=5, catfood_draws_used=0).cost == 0
