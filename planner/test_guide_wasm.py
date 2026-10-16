import struct
from pathlib import Path

import pytest
from PIL import Image

SHOTS = Path(__file__).parent / "fixtures/guide"
EN_PAGES = 34  # the EN Cat Guide these shots come from

# Read by eye off each screenshot: O owned, ? locked, . no cell.
PAGES = [
    ("en-p00-normal.jpg", 0, "O" * 10 + "." * 14),
    ("en-p01-special.jpg", 1, "O" * 20 + "?" + "O" * 3),
    ("en-p08-rare.jpg", 8, "O" * 24),
    ("en-p13-rare.jpg", 13, "OO" + "?" * 12 + "OOO" + "." * 7),
    ("en-p25-uber.jpg", 25, "??OOOOOO?O??" + "?" * 12),
]


def pixels(neko_wasm, name):
    """The shot's RGBA bytes copied into the module, as the page does from a canvas."""
    store, ex = neko_wasm
    image = Image.open(SHOTS / name).convert("RGBA")
    data = image.tobytes()
    ptr = ex["alloc"](store, len(data))
    ex["memory"].write(store, data, ptr)
    return ptr, len(data), image.width, image.height


def measure(neko_wasm, name):
    store, ex = neko_wasm
    ptr, size, w, h = pixels(neko_wasm, name)
    found = ex["guide_measure"](store, ptr, w, h)
    out = ex["guide_page"](store)
    page = struct.unpack("<9d", ex["memory"].read(store, out, out + 72))
    ex["dealloc"](store, ptr, size)
    position = page[0] if found & 1 else None
    grid = tuple(int(v) for v in page[1:]) if found & 2 else None
    return position, grid


def read(neko_wasm, name, grid):
    store, ex = neko_wasm
    ptr, size, w, h = pixels(neko_wasm, name)
    out = ex["guide_read"](store, ptr, w, h, *grid[:6])
    marks = ex["memory"].read(store, out, out + 24)
    ex["dealloc"](store, ptr, size)
    return "".join(".?O"[m] for m in marks)


@pytest.fixture(scope="module")
def full_grid(neko_wasm):
    """The batch's grid, taken from a full page like the page does."""
    _, grid = measure(neko_wasm, "en-p08-rare.jpg")
    return grid


def test_a_full_page_shows_the_whole_six_by_four_grid(full_grid):
    assert full_grid[-2:] == (6, 4)


@pytest.mark.parametrize(("name", "page", "_"), PAGES)
def test_the_indicator_places_the_shot_on_its_page(neko_wasm, name, page, _):
    position, _grid = measure(neko_wasm, name)
    assert abs(position * (EN_PAGES - 1) - page) < 0.25


@pytest.mark.parametrize(("name", "_", "marks"), PAGES)
def test_each_cell_reads_as_owned_locked_or_empty(neko_wasm, full_grid, name, _, marks):
    assert read(neko_wasm, name, full_grid) == marks
