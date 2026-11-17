import json
import os
from pathlib import Path

import pytest
from wasmtime import Config, Engine, Func, FuncType, Instance, Module, Store, ValType

from planner.catalogue_cache import forget_catalogue
from planner.middleware import PROFILE_COOKIE
from planner.models import Profile


@pytest.fixture(autouse=True)
def _fresh_catalogue():
    """Each test builds its own catalogue: none may read another's from the cache."""
    forget_catalogue()


@pytest.fixture
def profile(db, client):
    """A returning visitor: a saved guest profile that the test client's cookie names."""
    profile = Profile.objects.create()
    client.cookies[PROFILE_COOKIE] = profile.key

    return profile


# The page's wasm, as shipped; CI points NEKO_WASM at a fresh build of wasm/ too.
WASM = Path(os.environ.get("NEKO_WASM", Path(__file__).parent / "static/planner/neko.wasm"))


def _instance(store):
    """neko.wasm's exports in ``store``, its progress import a no-op."""
    noop = Func(store, FuncType([ValType.i32(), ValType.f64()], []), lambda run, done: None)
    return Instance(store, Module.from_file(store.engine, str(WASM)), [noop]).exports(store)


@pytest.fixture(scope="session")
def neko_wasm():
    """(store, exports) of one neko.wasm instance."""
    store = Store()
    return store, _instance(store)


def _caller(store, ex):
    def call(request):
        data = json.dumps(request).encode()
        ptr = ex["alloc"](store, len(data))
        ex["memory"].write(store, data, ptr)
        ex["engine"](store, ptr, len(data))
        ex["dealloc"](store, ptr, len(data))
        out, size = ex["engine_out"](store), ex["engine_out_len"](store)
        return bytes(ex["memory"].read(store, out, out + size)).decode()

    return call


@pytest.fixture(scope="session")
def engine(neko_wasm):
    """Call the page's engine the way the page does: a JSON request in, its response out."""
    return _caller(*neko_wasm)


@pytest.fixture
def engine_on_budget():
    """The engine in a fresh instance that may run only ``fuel`` wasm instructions per
    call (wasmtime fuel) and traps past it: work bounded the same on every machine."""
    config = Config()
    config.consume_fuel = True
    store = Store(Engine(config))
    store.set_fuel(10**9)  # instantiating runs the module's start code
    call = _caller(store, _instance(store))

    def run(request, fuel):
        store.set_fuel(fuel)
        return call(request)

    return run
