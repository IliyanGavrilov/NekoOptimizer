from neko.models import CATFOOD_PER_DRAW, Path, State


def test_equal_states_collapse_when_hashed():
    fields = dict(position=10, tickets_left=5, catfood_draws=8, found=frozenset({"Bahamut"}))
    assert len({State(**fields), State(**fields)}) == 1


def test_state_found_set_affects_identity():
    base = dict(position=0, tickets_left=0, catfood_draws=0)
    assert State(found=frozenset({"A"}), **base) != State(found=frozenset({"A", "B"}), **base)


def test_path_cost_counts_catfood_not_tickets():
    path = Path(pulls=(), tickets_used=5, catfood_draws_used=2)
    assert path.cost == 2 * CATFOOD_PER_DRAW
