from datetime import date

from neko.gacha import GachaRule, guaranteed_configs, load_rules, match_rule
from neko.godfat import GachaEvent
from neko.search import Guaranteed

ELEVEN = Guaranteed(11, 1500)
FIFTEEN = Guaranteed(15, 2100)


def rules():
    return [GachaRule(("step up",), FIFTEEN), GachaRule((), ELEVEN)]


def event(event_id, name):
    return GachaEvent(event_id, name, date(2026, 6, 1), date(2026, 6, 30))


def test_keyword_rule_matches_name():
    assert match_rule("Step Up Festival", rules()) == FIFTEEN


def test_match_is_case_insensitive():
    assert match_rule("STEP UP", rules()) == FIFTEEN


def test_falls_through_to_catch_all():
    assert match_rule("Platinum Banner", rules()) == ELEVEN


def test_no_match_returns_none():
    assert match_rule("Platinum Banner", [GachaRule(("epic",), ELEVEN)]) is None


def test_configs_keyed_by_event_id():
    configs = guaranteed_configs([event("ev1", "Step Up")], rules())
    assert configs == {"ev1": FIFTEEN}


def test_configs_skip_unmatched_events():
    no_default = [GachaRule(("step up",), FIFTEEN)]
    assert guaranteed_configs([event("ev1", "Platinum")], no_default) == {}


def test_load_rules_reads_default_eleven_roll():
    assert match_rule("anything", load_rules()) == ELEVEN
