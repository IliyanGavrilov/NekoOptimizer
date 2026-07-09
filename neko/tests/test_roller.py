from datetime import date

from neko.gacha import GachaRule
from neko.gachadata import GachaEventRow
from neko.models import Rarity, future_uber_names
from neko.roller import RollResult, active_events, catalogue_banners, roll_active, roll_selected
from neko.search import Multi


def event(event_id, name, start, end, pool_id, guaranteed=True, step_up=False):
    return GachaEventRow(
        event_id, name, start, end, pool_id, 7000, 2500, 500, 0, guaranteed, step_up
    )


EVENTS = [
    event("2025-01-01_42", "Alpha Banner", date(2025, 1, 1), date(2025, 1, 10), 42),
    event("2025-02-01_43", "Beta Banner", date(2025, 2, 1), date(2025, 2, 10), 43),
]
POOLS = {42: [100, 200, 300, 400], 43: [100, 300]}
UNITS = {
    100: ("R1", "Rare"),
    200: ("R2", "Rare"),
    300: ("S1", "Super Rare"),
    400: ("U1", "Uber Super Rare"),
}


def roll(fn, *args, **kw):
    return fn(*args, events=EVENTS, pools=POOLS, units=UNITS, rules=[], **kw)


def test_roll_selected_returns_a_roll_result_for_named_banners():
    res = roll(roll_selected, 123, ["Alpha Banner"])
    assert isinstance(res, RollResult)
    assert set(res.banners) == {"Alpha Banner"}
    assert all(p.cat in {"R1", "R2", "S1", "U1"} for p in res.banners["Alpha Banner"].pulls)
    assert res.dates["Alpha Banner"] == (date(2025, 1, 1), date(2025, 1, 10))


def test_active_events_includes_the_start_and_end_dates():
    assert active_events(EVENTS, date(2025, 1, 1)) == [EVENTS[0]]
    assert active_events(EVENTS, date(2025, 1, 10)) == [EVENTS[0]]
    assert active_events(EVENTS, date(2025, 1, 20)) == []


def test_roll_active_filters_by_date():
    assert set(roll(roll_active, 123, today=date(2025, 1, 5)).banners) == {"Alpha Banner"}
    assert set(roll(roll_active, 123, today=date(2025, 2, 5)).banners) == {"Beta Banner"}


def test_catalogue_banners_lists_every_pool_cat_without_rolling():
    res = catalogue_banners(events=EVENTS, pools=POOLS, units=UNITS)
    assert set(res.banners) == {"Alpha Banner", "Beta Banner"}
    assert {p.cat for p in res.banners["Alpha Banner"].pulls} == {"R1", "R2", "S1", "U1"}
    assert {p.cat for p in res.banners["Beta Banner"].pulls} == {"R1", "S1"}
    assert res.dates["Beta Banner"] == (date(2025, 2, 1), date(2025, 2, 10))


def test_multis_are_matched_by_rule():
    rule = GachaRule((), (Multi(11, 1500, True),))
    res = roll_selected(
        123, ["Alpha Banner"], events=EVENTS, pools=POOLS, units=UNITS, rules=[rule]
    )
    assert res.multis["Alpha Banner"] == (Multi(11, 1500, True),)


def test_guaranteed_banner_gets_the_guaranteed_column():
    res = roll(roll_selected, 123, ["Alpha Banner"])
    assert res.banners["Alpha Banner"].guaranteed


def test_plain_banner_gets_no_guaranteed_column_and_its_multi_is_demoted():
    plain = [
        event(
            "2025-03-01_44",
            "Plain Banner",
            date(2025, 3, 1),
            date(2025, 3, 10),
            42,
            guaranteed=False,
        )
    ]
    rule = GachaRule((), (Multi(11, 1500, True),))
    res = roll_selected(123, ["Plain Banner"], events=plain, pools=POOLS, units=UNITS, rules=[rule])
    assert res.banners["Plain Banner"].guaranteed == []
    assert res.multis["Plain Banner"] == (Multi(11, 1500, False),)


def test_simulate_guaranteed_forces_the_column_on_a_plain_banner():
    plain = [
        event(
            "2025-03-01_44",
            "Plain Banner",
            date(2025, 3, 1),
            date(2025, 3, 10),
            42,
            guaranteed=False,
        )
    ]
    kw = dict(events=plain, pools=POOLS, units=UNITS, rules=[])
    assert roll_selected(123, ["Plain Banner"], **kw).banners["Plain Banner"].guaranteed == []
    forced = roll_selected(123, ["Plain Banner"], simulate_guaranteed=11, **kw)
    assert len(forced.banners["Plain Banner"].guaranteed) > 1


def test_future_ubers_pad_the_pool_but_shift_only_uber_names():
    kw = dict(events=EVENTS, pools=POOLS, units=UNITS, rules=[])
    plain = roll_selected(123, ["Alpha Banner"], **kw).banners["Alpha Banner"]
    padded = roll_selected(123, ["Alpha Banner"], future_ubers={"Alpha Banner": 3}, **kw).banners[
        "Alpha Banner"
    ]
    placeholders = set(future_uber_names(3))

    for before, after in zip(plain.pulls, padded.pulls, strict=True):
        assert (after.position, after.track, after.rarity, after.seed) == (
            before.position,
            before.track,
            before.rarity,
            before.seed,
        )
        if before.rarity is Rarity.UBER_SUPER_RARE:
            assert after.cat in placeholders | {"U1"}
        else:
            assert after.cat == before.cat

    # The padding must actually shift something, or the control would be a no-op.
    assert any(a.cat != b.cat for a, b in zip(plain.pulls, padded.pulls, strict=True))


def test_future_ubers_pad_only_the_named_banner():
    kw = dict(events=EVENTS, pools=POOLS, units=UNITS, rules=[])
    names = ["Alpha Banner", "Beta Banner"]
    plain = roll_selected(123, names, **kw).banners
    padded = roll_selected(123, names, future_ubers={"Alpha Banner": 3}, **kw).banners
    assert padded["Beta Banner"].pulls == plain["Beta Banner"].pulls


def test_simulate_guaranteed_leaves_a_real_guarantee_unchanged():
    kw = dict(events=EVENTS, pools=POOLS, units=UNITS, rules=[])
    real = roll_selected(123, ["Alpha Banner"], **kw).banners["Alpha Banner"].guaranteed
    forced = roll_selected(123, ["Alpha Banner"], simulate_guaranteed=7, **kw)
    assert forced.banners["Alpha Banner"].guaranteed == real


def test_step_up_guarantee_lands_only_on_the_15_roll_multi():
    step = [
        event(
            "2025-04-01_45",
            "Step Up Banner",
            date(2025, 4, 1),
            date(2025, 4, 10),
            42,
            guaranteed=False,
            step_up=True,
        )
    ]
    rule = GachaRule((), (Multi(3, 300, True), Multi(15, 2100, True)), step_up=True)
    res = roll_selected(
        123, ["Step Up Banner"], events=step, pools=POOLS, units=UNITS, rules=[rule]
    )
    assert res.banners["Step Up Banner"].guaranteed
    assert res.multis["Step Up Banner"] == (Multi(3, 300, False), Multi(15, 2100, True))


def test_bare_name_resolves_to_the_run_live_today_not_a_future_rerun():
    reruns = [
        event("2025-04-24_42", "Platinum", date(2025, 4, 24), date(2030, 1, 1), 42),
        event("2025-07-11_43", "Platinum", date(2025, 7, 11), date(2030, 1, 1), 43),
    ]
    res = roll_selected(
        123, ["Platinum"], today=date(2025, 7, 1), events=reruns, pools=POOLS, units=UNITS, rules=[]
    )
    assert res.dates["Platinum"] == (date(2025, 4, 24), date(2030, 1, 1))


def test_dated_selection_pins_that_exact_run():
    reruns = [
        event("2025-04-24_42", "Platinum", date(2025, 4, 24), date(2030, 1, 1), 42),
        event("2025-07-11_43", "Platinum", date(2025, 7, 11), date(2030, 1, 1), 43),
    ]
    res = roll_selected(
        123,
        ["2025-07-11|Platinum"],
        today=date(2025, 7, 1),
        events=reruns,
        pools=POOLS,
        units=UNITS,
        rules=[],
    )
    assert res.dates["Platinum"] == (date(2025, 7, 11), date(2030, 1, 1))


def test_rolls_are_deterministic_for_a_seed():
    a = roll(roll_selected, 777, ["Beta Banner"])
    b = roll(roll_selected, 777, ["Beta Banner"])
    assert a.banners["Beta Banner"].pulls == b.banners["Beta Banner"].pulls
