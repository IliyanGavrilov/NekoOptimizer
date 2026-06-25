from datetime import date

from neko.gacha import GachaRule, load_rules, match_rule, multi_configs
from neko.godfat import GachaEvent
from neko.search import Multi

ELEVEN = (Multi(11, 1500),)
STEP_UP = (Multi(3, 300, guaranteed=False), Multi(8, 1050, guaranteed=False), Multi(15, 2100))


def rules():
    return [GachaRule(("step up",), STEP_UP), GachaRule((), ELEVEN)]


def event(event_id, name):
    return GachaEvent(event_id, name, date(2026, 6, 1), date(2026, 6, 30))


def test_keyword_rule_matches_name():
    assert match_rule("Step Up Festival", rules()) == STEP_UP


def test_match_is_case_insensitive():
    assert match_rule("STEP UP", rules()) == STEP_UP


def test_falls_through_to_catch_all():
    assert match_rule("Platinum Banner", rules()) == ELEVEN


def test_no_match_returns_none():
    assert match_rule("Platinum Banner", [GachaRule(("epic",), ELEVEN)]) is None


def test_configs_keyed_by_event_id():
    configs = multi_configs([event("ev1", "Step Up")], rules())
    assert configs == {"ev1": STEP_UP}


def test_configs_skip_unmatched_events():
    no_default = [GachaRule(("step up",), STEP_UP)]
    assert multi_configs([event("ev1", "Platinum")], no_default) == {}


def test_load_rules_reads_default_eleven_roll():
    assert match_rule("anything", load_rules()) == ELEVEN
