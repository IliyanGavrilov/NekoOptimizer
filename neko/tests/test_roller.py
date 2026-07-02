from datetime import date

from neko.gacha import GachaRule
from neko.gachadata import GachaEventRow
from neko.roller import roll_active, roll_catalogue, roll_selected
from neko.scraper import ScrapeResult
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


def test_roll_selected_returns_a_scrape_result_for_named_banners():
    res = roll(roll_selected, 123, ["Alpha Banner"])
    assert isinstance(res, ScrapeResult)
    assert set(res.banners) == {"Alpha Banner"}
    assert all(p.cat in {"R1", "R2", "S1", "U1"} for p in res.banners["Alpha Banner"].pulls)
    assert res.dates["Alpha Banner"] == (date(2025, 1, 1), date(2025, 1, 10))


def test_roll_active_filters_by_date():
    assert set(roll(roll_active, 123, today=date(2025, 1, 5)).banners) == {"Alpha Banner"}
    assert set(roll(roll_active, 123, today=date(2025, 2, 5)).banners) == {"Beta Banner"}


def test_roll_catalogue_rolls_every_banner():
    assert set(roll(roll_catalogue, 123).banners) == {"Alpha Banner", "Beta Banner"}


def test_multis_are_matched_by_rule():
    rule = GachaRule((), (Multi(11, 1500, True),))
    res = roll_selected(
        123, ["Alpha Banner"], events=EVENTS, pools=POOLS, units=UNITS, rules=[rule]
    )
    assert res.multis["Alpha Banner"] == (Multi(11, 1500, True),)


def test_guaranteed_banner_gets_the_guaranteed_column():
    res = roll(roll_selected, 123, ["Alpha Banner"])  # Alpha runs a guaranteed event
    assert res.banners["Alpha Banner"].guaranteed


def test_plain_banner_gets_no_guaranteed_column_and_its_multi_is_demoted():
    # A banner that is neither guaranteed nor step-up must not offer a guaranteed uber:
    # no guaranteed column, and the config's 11-roll multi becomes a plain 11-roll.
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
    rule = GachaRule((), (Multi(11, 1500, True), Multi(15, 2100, True)))
    res = roll_selected(
        123, ["Step Up Banner"], events=step, pools=POOLS, units=UNITS, rules=[rule]
    )
    assert res.banners["Step Up Banner"].guaranteed
    assert res.multis["Step Up Banner"] == (Multi(11, 1500, False), Multi(15, 2100, True))


def test_bare_name_resolves_to_the_run_live_today_not_a_future_rerun():
    # A recurring banner name reruns with a DIFFERENT pool; asking for the name must
    # give the run that's on now, not the future rerun (whose start date is later).
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
