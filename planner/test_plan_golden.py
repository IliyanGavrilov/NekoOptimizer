import json
import time
from pathlib import Path

from neko.models import CATFOOD_PER_DRAW, BannerRolls, Rarity, TrackPull
from neko.search import Multi
from planner.services import equivalent_banners, subset_solutions

R = Rarity.RARE
S = Rarity.SUPER_RARE
U = Rarity.UBER_SUPER_RARE

GOLDEN_PATH = Path(__file__).parent / "fixtures" / "plan_golden.json"


def _fill(idx, rares, supers):
    if idx % 5 == 3:
        return supers[(idx // 5) % len(supers)], S
    return rares[idx % len(rares)], R


def _banner(overrides, rerolls, rares, supers, ubers, positions=12, seed_base=0):
    pulls, guaranteed, guaranteed_rerolls = [], [], []
    for idx in range(2 * positions):
        pos, track = idx // 2 + 1, "AB"[idx % 2]
        cat, rarity = overrides.get(idx) or _fill(idx, rares, supers)
        pulls.append(TrackPull(pos, track, cat, rarity, seed=seed_base + idx))
        guaranteed.append(TrackPull(pos, track, ubers[idx % len(ubers)], U, seed=seed_base + idx))
        guaranteed_rerolls.append(
            TrackPull(pos, track, ubers[(idx + 1) % len(ubers)], U, seed=seed_base + idx)
        )
    return BannerRolls(pulls, guaranteed, rerolls, guaranteed_rerolls)


def _rolls():
    x = _banner(
        overrides={
            2: ("Windy", U),
            9: ("Thundia", U),
            16: ("Kuu", U),
            12: ("Tin Cat", R),
            14: ("Tin Cat", R),
        },
        rerolls=[
            TrackPull(8, "A", "Sniper Cat", R, seed=814, steps=1, realized=True),
            TrackPull(3, "A", "Sniper Cat", R, seed=304, steps=1),
        ],
        rares=["Tin Cat", "Pogo Cat", "Cutter Cat", "Hunter Cat"],
        supers=["Salon Cat", "Weightlifter Cat"],
        ubers=["Windy", "Thundia", "Kuu"],
        seed_base=1000,
    )
    z = _banner(
        overrides={5: ("Kasa Jizo", U), 12: ("Momotaro", U)},
        rerolls=[],
        rares=["Onmyoji Cat", "Bath Cat", "Rocker Cat", "Sushi Cat"],
        supers=["Witch Cat", "Vaulter Cat"],
        ubers=["Kasa Jizo", "Momotaro"],
        seed_base=7000,
    )
    return {"X": x, "Y": x, "Z": z}


def _base():
    banners = _rolls()
    return {
        "pulls": {name: rolls.pulls for name, rolls in banners.items()},
        "rerolls": {name: rolls.rerolls for name, rolls in banners.items()},
        "guaranteed_pulls": {name: rolls.guaranteed for name, rolls in banners.items()},
        "guaranteed_rerolls": {name: rolls.guaranteed_rerolls for name, rolls in banners.items()},
        "equivalents": equivalent_banners(banners),
        "owned": {"Kuu", "Bath Cat"},
        "wanted": {"Windy", "Momotaro"},
        "titles": {"X": "Dynamites", "Y": "Dynamites"},
    }


_MULTIS = {"X": (Multi(11, 1500),), "Y": (Multi(11, 1500),)}


def golden_cases():
    base = _base()
    yield "singleton", dict(base, targets={"Windy"}, tickets=2, catfood=0)
    yield (
        "trio_across_banners",
        dict(
            base,
            targets={"Windy", "Thundia", "Kasa Jizo"},
            tickets=1,
            catfood=1200,
            multis=_MULTIS,
        ),
    )
    yield "unobtainable_mix", dict(base, targets={"Windy", "Ghost Cat"}, tickets=3, catfood=300)
    yield "unobtainable_only", dict(base, targets={"Ghost Cat"}, tickets=3, catfood=300)
    yield "unaffordable_pair", dict(base, targets={"Windy", "Thundia"}, tickets=1, catfood=0)
    yield (
        "capped_banner",
        dict(
            base,
            targets={"Windy", "Kasa Jizo"},
            tickets=4,
            catfood=600,
            banner_currency={"Z": "platinum"},
        ),
    )
    yield (
        "guaranteed_multi",
        dict(base, targets={"Kuu"}, tickets=0, catfood=1650, multis=_MULTIS),
    )


def solve(case):
    case = dict(case)
    result = subset_solutions(
        case.pop("pulls"),
        case.pop("rerolls"),
        case.pop("equivalents"),
        case.pop("targets"),
        tickets=case.pop("tickets"),
        catfood=case.pop("catfood"),
        guaranteed_pulls=case.pop("guaranteed_pulls"),
        multis=case.pop("multis", None),
        ticket_value=case.pop("ticket_value", CATFOOD_PER_DRAW),
        banner_currency=case.pop("banner_currency", None),
        platinum=case.pop("platinum", 0),
        legend=case.pop("legend", 0),
        owned=case.pop("owned"),
        wanted=case.pop("wanted"),
        titles=case.pop("titles"),
        guaranteed_rerolls=case.pop("guaranteed_rerolls"),
    )
    assert not case, f"unconsumed case keys: {sorted(case)}"
    return result


def _norm(value):
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm(v) for v in value]
    if isinstance(value, (set, frozenset)):
        return sorted(_norm(v) for v in value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def render(case) -> str:
    return json.dumps(_norm(solve(case)), sort_keys=True, separators=(",", ":"))


def test_small_inputs_are_byte_identical_to_golden():
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    current = {name: render(case) for name, case in golden_cases()}
    assert current == golden


TIME_BUDGET = 15.0


def _timed(case):
    begin = time.perf_counter()
    solutions = solve(case)
    return time.perf_counter() - begin, solutions


def test_wishlist_of_100_with_few_obtainable_completes_in_budget():
    targets = {"Windy", "Thundia", "Kasa Jizo"} | {f"Wish {i:03d}" for i in range(97)}
    case = dict(_base(), targets=targets, tickets=2, catfood=1200, multis=_MULTIS)
    elapsed, solutions = _timed(case)
    assert elapsed < TIME_BUDGET
    found = [s for s in solutions if s["found"]]
    assert found, "the obtainable trio must still get plans"
    assert all(set(s["targets"]) <= {"Windy", "Thundia", "Kasa Jizo"} for s in found)
    missing = {tuple(s["targets"]) for s in solutions if not s["found"]}
    assert ("Wish 000",) in missing, "each unobtainable cat is reported individually"
    assert len(solutions) < 200


def _wide_banner():
    ubers = [f"Big Uber {i:02d}" for i in range(16)]
    return _banner(
        overrides={2 * i: (ubers[i], U) for i in range(16)},
        rerolls=[],
        rares=["Tin Cat", "Pogo Cat", "Cutter Cat", "Hunter Cat"],
        supers=["Salon Cat", "Weightlifter Cat"],
        ubers=ubers[:3],
        positions=24,
        seed_base=3000,
    )


def test_wishlist_with_many_obtainable_completes_in_budget():
    rolls = _wide_banner()
    targets = {f"Big Uber {i:02d}" for i in range(16)} | {f"Wish {i:03d}" for i in range(84)}
    case = dict(
        _base(),
        pulls={"W": rolls.pulls},
        rerolls={"W": rolls.rerolls},
        guaranteed_pulls={"W": rolls.guaranteed},
        guaranteed_rerolls={"W": rolls.guaranteed_rerolls},
        equivalents=equivalent_banners({"W": rolls}),
        targets=targets,
        tickets=6,
        catfood=1500,
    )
    elapsed, solutions = _timed(case)
    assert elapsed < TIME_BUDGET
    found = [s for s in solutions if s["found"]]
    assert found, "per-cat plans for the obtainable ubers must be found"
    assert len(solutions) < 200
