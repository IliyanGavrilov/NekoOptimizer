# The normal-side gacha engine, checked byte-for-byte against ampuri's tracker
# (github.com/ampuri/bc-normal-seed-tracking) - the community reference for the
# normal seed. The fixtures are scraped straight off its rendered tables.

import json
from pathlib import Path

import pytest

from neko.normal import BANNERS_BY_KEY, NORMAL_BANNERS, play, roll_normal

FIXTURES = Path(__file__).parent / "fixtures"

TRACKS = ("A", "B")


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def track_maps(rolls):
    pulls = {(p.position, p.track): p for p in rolls.pulls}
    rerolls = {(p.position, p.track): p for p in rolls.rerolls}

    return pulls, rerolls


def landing(position: int, track: str, steps: int) -> tuple[int, str]:
    """Where a reroll's extra steps land the chain (the engine's _landing, restated
    from the dupe cell's 1-based coordinates)."""
    seq, tindex = position - 1, TRACKS.index(track)
    seq_landing = seq + (tindex + steps) // 2 + 1

    return seq_landing + 1, TRACKS[((tindex + steps - 1) ^ 1) & 1]


@pytest.mark.parametrize("fixture", ["normal_golden_1515525936.json", "normal_golden_lastcat.json"])
def test_tracks_match_ampuris_tables(fixture):
    """Every cell of every banner: the item, the seed a click jumps to, which cells
    show a dupe branch, the branch's item/seed, and where it lands."""
    golden = load_fixture(fixture)
    last = golden.get("lastCat", "")

    for column, key in enumerate(golden["banners"]):
        banner = BANNERS_BY_KEY[key]
        rolls = roll_normal(golden["seed"], banner, golden["rolls"], last_item=last)
        pulls, rerolls = track_maps(rolls)

        for track in TRACKS:
            for row, cells in enumerate(golden[f"track{track}"], start=1):
                cell = cells[column]
                pull = pulls[(row, track)]
                assert pull.item == cell["name"], (key, row, track)
                assert pull.seed == cell["seed"], (key, row, track)

                branch = cell.get("dupe")
                reroll = rerolls.get((row, track))
                shown = reroll is not None and reroll.realized
                assert shown == (branch is not None), (key, row, track)
                if branch is None:
                    continue

                assert reroll.item == branch["name"], (key, row, track)
                if reroll.steps > 1:
                    # A cascade (a repick that re-dupes) only happens in pools that
                    # repeat a name (the lucky tickets). There ampuri's shrunk-pool
                    # remap diverges from godfat's in-game-validated pool deletion
                    # after the first removal, so its step count - and with it the
                    # end seed and landing - can differ. The item above still has
                    # to match; the mechanics we trust are godfat's.
                    continue

                assert reroll.seed == branch["seed"], (key, row, track)
                assert landing(row, track, reroll.steps) == (branch["pos"], branch["track"])
                target = pulls.get((branch["pos"], branch["track"]))
                if target is not None:
                    assert (target.item == reroll.item) == branch["bounce"], (key, row, track)


@pytest.mark.parametrize("banner", NORMAL_BANNERS, ids=lambda b: b.key)
def test_play_walks_the_grids_play_chain(banner):
    """play must consume the stream exactly like the grid: walk the rolled grid's
    straight chain (nominal cell, or its reroll when the previous pull dupes it)
    and the linear names must match, cascades and track jumps included."""
    seed, count = 1515525936, 60
    rolls = roll_normal(seed, banner, count + 10)
    pulls, rerolls = track_maps(rolls)

    names = []
    position, track, prev = 1, "A", ""
    for _ in range(count):
        pull = pulls[(position, track)]
        reroll = rerolls.get((position, track))
        if reroll is not None and pull.item == prev:
            names.append(reroll.item)
            position, track = landing(position, track, reroll.steps)
        else:
            names.append(pull.item)
            position += 1

        prev = names[-1]

    assert play(seed, banner, count)[0] == names


def test_play_seed_after_continues_the_chain():
    """Feeding a pull's end state back in must make the next pull its 1A - the
    page's click-to-jump depends on it."""
    banner = BANNERS_BY_KEY["np"]
    items, end = play(1515525936, banner, 10)
    tail, _ = play(1515525936, banner, 15)

    resumed, _ = play(end, banner, 5, last_item=items[-1])
    assert resumed == tail[10:]
