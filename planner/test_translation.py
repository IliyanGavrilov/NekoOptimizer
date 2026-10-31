import json
import re
from gettext import GNUTranslations, NullTranslations
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation

from neko.region import using
from neko.tests.test_seek import GOLDEN_SEED
from neko.tierdata import load_tiers
from planner.engine_text import ENGINE_PLURALS, ENGINE_TEXT, SHORT_RARITIES, engine_text
from planner.services import fest_label, normal_names, tier_set_label
from planner.test_normal_engine import DARK_SEED, _plan, _tracks
from planner.test_normal_engine import _compare as _compare_normal
from planner.test_plans_engine import _compare as _compare_plan
from planner.test_plans_engine import _form as _plan_form
from planner.test_plans_engine import _targets
from planner.test_tracks_engine import _compare, _form, _runs, catalogue  # noqa: F401

# The reference views the engine is held to are routed only for tests.
pytestmark = [pytest.mark.django_db, pytest.mark.urls("planner.reference_urls")]

LANGUAGES = [code for code, _ in settings.LANGUAGES if code != "en"]
ROOT = Path(__file__).resolve().parent
STR = r'"((?:[^"\\]|\\.)*)"'


def _literal(text: str) -> str:
    return json.loads(f'"{text}"')


def _rust_text() -> set[str]:
    """Every English string the engine looks up in a request's ``text``."""
    found = set()
    for path in (ROOT.parent / "wasm" / "src").glob("*.rs"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"\btrn\(\s*" + STR + r",\s*" + STR, source):
            found.update(map(_literal, match.groups()))
        for match in re.finditer(r"\btr?\(\s*" + STR, source):
            found.add(_literal(match.group(1)))
    return found


def test_every_string_the_engine_asks_for_is_sent():
    declared = set(ENGINE_TEXT) | {form for pair in ENGINE_PLURALS for form in pair}
    assert _rust_text() - declared == set()


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_engine_string_is_translated(language):
    with translation.override(language):
        text = engine_text()
    plurals = {form for pair in ENGINE_PLURALS for form in pair}
    shorts = {f"short rarity:{short}" for short in SHORT_RARITIES}
    assert (set(ENGINE_TEXT) | plurals | shorts) - set(text) == set()


class _Missing(NullTranslations):
    def gettext(self, message):
        return None

    def ngettext(self, singular, plural, n):
        return None


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_script_string_is_translated(language):
    # xgettext before 0.21 skips strings past a template literal, so check the catalogue
    # holds every gettext call the page scripts make.
    locale = translation.to_locale(language)
    with open(ROOT / "locale" / locale / "LC_MESSAGES" / "djangojs.mo", "rb") as compiled:
        catalogue = GNUTranslations(compiled)
    catalogue.add_fallback(_Missing())
    call = re.compile(
        r"\b(n?gettext)\(\s*" + STR + r"(?:\s*\+\s*" + STR + r")?(?:,\s*" + STR + r")?"
    )
    missing = []
    for path in (ROOT / "static" / "planner").glob("*.js"):
        for match in call.finditer(path.read_text(encoding="utf-8")):
            kind, first, rest, plural = match.groups()
            message = _literal(first) + (_literal(rest) if rest else "")
            if kind == "ngettext":
                got = catalogue.ngettext(message, _literal(plural), 1)
            else:
                got = catalogue.gettext(message)
            if got is None:
                missing.append(message)
    assert missing == []


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_rolls_table_renders_alike_in_every_language(client, engine, catalogue, language):  # noqa: F811
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    html = _compare(client, engine, _form(GOLDEN_SEED, _runs(2), simulate_guaranteed="11"))
    assert "Track A" not in html


@pytest.mark.parametrize("language", LANGUAGES)
def test_a_plan_renders_alike_in_every_language(client, engine, catalogue, language):  # noqa: F811
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    seed, runs = GOLDEN_SEED, _runs(3)
    targets = _targets(seed, runs, 3, rows=10, track="A")
    html = _compare_plan(client, engine, _plan_form(seed, runs, targets))
    assert "Apply this plan" not in html


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_normal_capsules_render_alike_in_every_language(client, engine, catalogue, language):  # noqa: F811
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = language
    _compare_normal(client, engine, "tracks", _tracks(DARK_SEED, ["n", "ce", "lt"]))
    plan = _plan(DARK_SEED, ["ce", "n", "lt", "ltg"], "dark", {"normal": 20, "lucky": 3})
    html = _compare_normal(client, engine, "plan", plan)
    assert "Apply this plan" not in html


def test_normal_items_take_each_versions_own_names():
    with using("jp"):
        names = normal_names()
    assert (names["Dark Catseye"], names["Superfeline"]) == ("キャッツアイ【闇】", "ネコ超人")


def test_english_keeps_the_normal_items_as_they_are():
    assert normal_names() == {}


def test_a_fest_the_cat_guide_names_takes_that_sets_own_name():
    # The JP Cat Guide calls EPICFEST's set 極ネコ祭, so its section must too, or the fest's
    # extras would land in a second section beside it.
    with using("jp"):
        assert fest_label(27) == "極ネコ祭"


def test_a_tier_list_takes_the_versions_own_set_name():
    dynamites = next(e for e in load_tiers()["lists"] if e["label"] == "Dynamites")
    with using("jp"):
        assert tier_set_label(dynamites) == "超激ダイナマイツ"
    assert tier_set_label(dynamites) == "Dynamites"
