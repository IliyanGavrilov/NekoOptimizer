import json
import os
from pathlib import Path

import pytest
from wasmtime import Func, FuncType, Instance, Module, Store, ValType

from planner.middleware import PROFILE_COOKIE
from planner.models import Profile


@pytest.fixture
def profile(db, client):
    """A returning visitor: a saved guest profile that the test client's cookie names."""
    profile = Profile.objects.create()
    client.cookies[PROFILE_COOKIE] = profile.key

    return profile


# The page's wasm, as shipped; CI points NEKO_WASM at a fresh build of wasm/ too.
WASM = Path(os.environ.get("NEKO_WASM", Path(__file__).parent / "static/planner/neko.wasm"))


@pytest.fixture(scope="session")
def neko_wasm():
    """(store, exports) of one neko.wasm instance, its progress import a no-op."""
    store = Store()
    noop = Func(store, FuncType([ValType.i32(), ValType.f64()], []), lambda run, done: None)
    exports = Instance(store, Module.from_file(store.engine, str(WASM)), [noop]).exports(store)
    return store, exports


@pytest.fixture(scope="session")
def engine(neko_wasm):
    """Call the page's engine the way the page does: a JSON request in, its response out."""
    store, ex = neko_wasm

    def call(request):
        data = json.dumps(request).encode()
        ptr = ex["alloc"](store, len(data))
        ex["memory"].write(store, data, ptr)
        ex["engine"](store, ptr, len(data))
        ex["dealloc"](store, ptr, len(data))
        out, size = ex["engine_out"](store), ex["engine_out_len"](store)
        return bytes(ex["memory"].read(store, out, out + size)).decode()

    return call
