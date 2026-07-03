from datetime import date

from neko.gacha import GachaRule, load_rules, match_rule, multi_configs
from neko.gachadata import GachaEventRow
from neko.search import Multi

ELEVEN = (Multi(11, 1500),)
STEP_UP = (Multi(3, 300, guaranteed=False), Multi(8, 1050, guaranteed=False), Multi(15, 2100))


def rules():
    return [GachaRule(("step up",), STEP_UP, step_up=True), GachaRule((), ELEVEN)]


def scheduled(event_id, name, guaranteed=False, step_up=False):
    return GachaEventRow(
        event_id,
        name,
        date(2026, 6, 1),
        date(2026, 6, 30),
        42,
        7000,
        2500,
        500,
        0,
        guaranteed,
        step_up,
    )


def test_keyword_rule_matches_name():
    assert match_rule("Platinum Capsules", [GachaRule(("platinum",), ELEVEN)]) == ELEVEN


def test_match_is_case_insensitive():
    assert match_rule("PLATINUM", [GachaRule(("platinum",), ELEVEN)]) == ELEVEN


def test_step_up_name_without_the_flag_is_ordinary():
    # The schedule flag is authoritative: a marketing name saying "Step Up" alone
    # doesn't trigger the ladder rule.
    assert match_rule("Step Up Festival", rules()) == ELEVEN


def test_falls_through_to_catch_all():
    assert match_rule("Platinum Banner", rules()) == ELEVEN


def test_no_match_returns_none():
    assert match_rule("Platinum Banner", [GachaRule(("epic",), ELEVEN)]) is None


def test_configs_keyed_by_event_id():
    configs = multi_configs([scheduled("ev1", "Step Up Festival", step_up=True)], rules())
    assert configs == {"ev1": STEP_UP}


def test_configs_skip_unmatched_events():
    no_default = [GachaRule(("step up",), STEP_UP, step_up=True)]
    assert multi_configs([scheduled("ev1", "Platinum")], no_default) == {}


def test_step_up_flag_picks_the_step_rule_regardless_of_name():
    # In game a step-up event has NO ordinary 11-roll - the forced 3/5/7 ladder replaces
    # it - and its marketing name rarely says "step up", so the schedule flag decides.
    row = scheduled("ev2", "Mighty Morta-Loncha, with Explosive attacks!", step_up=True)
    assert multi_configs([row], rules()) == {"ev2": STEP_UP}


def test_step_up_event_never_takes_the_ordinary_multis():
    row = scheduled("ev2", "Anything", step_up=True)
    assert multi_configs([row], [GachaRule((), ELEVEN)]) == {}


def test_guaranteed_takes_precedence_over_step_up():
    # godfat's pool.guaranteed_rolls checks guaranteed first, so a both-flagged event is
    # an 11-roll guarantee, not a step-up ladder.
    row = scheduled("ev3", "Anything", guaranteed=True, step_up=True)
    assert multi_configs([row], rules()) == {"ev3": ELEVEN}


def test_load_rules_reads_default_eleven_roll():
    assert match_rule("anything", load_rules()) == ELEVEN


def test_load_rules_matches_step_up_event():
    assert match_rule("anything", load_rules(), step_up=True) == STEP_UP
