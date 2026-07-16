from neko.models import (
    CATFOOD_PER_DRAW,
    Banner,
    Path,
    Rarity,
    State,
    future_uber_banner,
    future_uber_label,
    future_uber_names,
    is_future_uber,
)


def test_equal_states_collapse_when_hashed():
    fields = dict(position=10, tickets_left=5, catfood_draws=8, found=frozenset({"Bahamut"}))
    assert len({State(**fields), State(**fields)}) == 1


def test_state_found_set_affects_identity():
    base = dict(position=0, tickets_left=0, catfood_draws=0)
    assert State(found=frozenset({"A"}), **base) != State(found=frozenset({"A", "B"}), **base)


def test_path_cost_counts_catfood_not_tickets():
    path = Path(pulls=(), tickets_used=5, catfood_draws_used=2)
    assert path.cost == 2 * CATFOOD_PER_DRAW


def test_future_uber_names_run_up_to_the_pool_front():
    assert future_uber_names(3) == ("Future Uber 3", "Future Uber 2", "Future Uber 1")
    assert future_uber_names(0) == ()


def test_future_uber_names_qualify_by_banner():
    assert future_uber_names(2, "Epicfest") == (
        "Future Uber 2 @ Epicfest",
        "Future Uber 1 @ Epicfest",
    )


def test_is_future_uber_matches_bare_and_qualified_placeholders():
    assert is_future_uber("Future Uber 1")
    assert is_future_uber("Future Uber 12")
    assert is_future_uber("Future Uber 1 @ Epicfest")
    assert not is_future_uber("Baby Gao")
    assert not is_future_uber("Future Uber 1 Cat")


def test_future_uber_label_and_banner_split_the_qualifier():
    assert future_uber_label("Future Uber 1 @ Epicfest") == "Future Uber 1"
    assert future_uber_banner("Future Uber 1 @ Epicfest") == "Epicfest"
    # A bare placeholder reads as itself, with no banner.
    assert future_uber_label("Future Uber 1") == "Future Uber 1"
    assert future_uber_banner("Future Uber 1") == ""


def test_with_future_ubers_prepends_banner_qualified_placeholders_and_leaves_the_rest():
    banner = Banner(
        "id",
        "Epicfest",
        "",
        {Rarity.UBER_SUPER_RARE: 500},
        {Rarity.UBER_SUPER_RARE: ("U1", "U2"), Rarity.RARE: ("R1",)},
    )
    padded = banner.with_future_ubers(2)
    assert padded.pool(Rarity.UBER_SUPER_RARE) == (
        "Future Uber 2 @ Epicfest",
        "Future Uber 1 @ Epicfest",
        "U1",
        "U2",
    )
    assert padded.pool(Rarity.RARE) == ("R1",)
    assert padded.rates == banner.rates
    assert banner.with_future_ubers(0) is banner
