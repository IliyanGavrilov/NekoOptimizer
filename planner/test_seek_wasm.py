import os
import struct
from math import ceil
from pathlib import Path

import pytest
from wasmtime import Func, FuncType, Instance, Module, Store, ValType

from neko.models import Rarity
from neko.rng import xorshift
from neko.seek import play, seek_spec
from neko.seekspec import seed_spec
from neko.tests.test_seek import ALL_RARE, GOLDEN_SEED, LEGEND_HEAVY, window_with_repick

# The page's sieve, as shipped; CI points SEEK_WASM at a fresh build of seekwasm/ too.
WASM = Path(os.environ.get("SEEK_WASM", Path(__file__).parent / "static/planner/seek.wasm"))
SLICES = 3  # seekrun.js splits each pass across workers; slicing here checks that merge


@pytest.fixture(scope="module")
def sieve():
    store = Store()
    noop = Func(store, FuncType([ValType.i32(), ValType.f64()], []), lambda run, done: None)
    exports = Instance(store, Module.from_file(store.engine, str(WASM)), [noop]).exports(store)
    return store, exports


def local_seek(sieve, spec, limit=20):
    """What seekrun.js does with the module: each pass in slices, concatenated in order."""
    store, ex = sieve
    words = [
        len(spec.sizes),
        *spec.sizes,
        *spec.bands,
        sum(1 << pool for pool in spec.rerollable),
        len(spec.cats),
        *(n for pair in spec.cats for n in pair),
    ]
    ex["memory"].write(store, struct.pack(f"<{len(words)}I", *words), ex["input"](store))

    def run_pass(run, cap):
        total = int(ex["pass_size"](store, run))
        step = ceil(total / SLICES) if total else 0
        found = []
        for i in range(SLICES if total else 0):
            frm = min(total, i * step)
            n = ex["search"](store, run, float(frm), float(min(total, frm + step)), cap)
            out = ex["output"](store)
            raw = struct.unpack(f"<{3 * n}I", ex["memory"].read(store, out, out + 12 * n))
            found += [tuple(raw[j : j + 3]) for j in range(0, len(raw), 3)]
        return found[:cap]

    matches = run_pass(0, limit + 1)
    if not matches:
        for run in (1, 2):
            matches += run_pass(run, max(limit + 1 - len(matches), 1))

    return matches, len(matches) > limit


def python_seek(spec, limit=20):
    result = seek_spec(spec, limit=limit)
    return [(m.seed_before, m.seed_after, m.run) for m in result.matches], result.truncated


def test_wasm_matches_python_on_a_window_with_a_repick(sieve):
    _, observed, _ = window_with_repick(ALL_RARE, GOLDEN_SEED, 6)
    spec = seed_spec(ALL_RARE, observed)
    assert local_seek(sieve, spec) == python_seek(spec)


def test_wasm_matches_python_on_a_first_pull_that_was_a_repick(sieve):
    start, _, _ = window_with_repick(ALL_RARE, GOLDEN_SEED, 2)
    full, _ = play(start, ALL_RARE, 6)
    spec = seed_spec(ALL_RARE, full[1:])
    assert local_seek(sieve, spec) == python_seek(spec)


def test_wasm_matches_python_on_the_rarity_method(sieve):
    state = GOLDEN_SEED
    while play(state, LEGEND_HEAVY, 1)[0][0][0] is not Rarity.LEGEND_RARE:
        state = xorshift(state)
    spec = seed_spec(LEGEND_HEAVY, play(state, LEGEND_HEAVY, 6)[0])
    assert local_seek(sieve, spec) == python_seek(spec)


def test_wasm_truncates_like_python(sieve):
    spec = seed_spec(ALL_RARE, [(Rarity.RARE, 7)])
    assert local_seek(sieve, spec, limit=5) == python_seek(spec, limit=5)
