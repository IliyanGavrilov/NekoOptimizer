# Pools come from the game's GatyaDataSetR1.csv (the BCData tarball we already fetch);
# rates and the schedule from godfat's curated event TSVs (Apache-2.0).

import csv
import io
import json
import tarfile
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from functools import cache
from pathlib import Path

from neko.bcdata import METADATA_URL, _get, latest_version, release_url
from neko.models import GACHA_RARITIES, Banner, Rarity

# godfat's event schedule lives in its Apache-2.0 gitlab repo, one dated TSV per snapshot.
_PROJECT = "9827349"  # gitlab project id for godfat/battle-cats-rolls
_EVENTS_TREE = (
    f"https://gitlab.com/api/v4/projects/{_PROJECT}/repository/tree"
    "?path=data/{lang}/events&per_page=100&page={page}&ref=master"
)
_EVENTS_RAW = "https://gitlab.com/godfat/battle-cats-rolls/-/raw/master/data/{lang}/events/{name}"

EVENTS_PATH = Path(__file__).parent / "data" / "gacha_events.json"
POOLS_PATH = Path(__file__).parent / "data" / "gacha_pools.json"
SERIES_PATH = Path(__file__).parent / "data" / "gacha_series.json"

_POOL_OFFSET = 9  # godfat tsv_reader PoolOffset: event fields end, pool blocks follow
_POOL_FIELDS = 15  # godfat tsv_reader PoolFields: each pool block is 15 columns
_RARE_GACHA = 1  # event type for the rare (main) gacha

_RARITY_ORDER = GACHA_RARITIES


@dataclass(frozen=True, slots=True)
class GachaEventRow:
    """One scheduled gacha: its godfat event id, name, run dates, pool id, and rates."""

    event_id: str
    name: str
    start: date
    end: date
    pool_id: int
    rare: int
    supa: int
    uber: int
    legend: int
    guaranteed: bool
    step_up: bool


def _parse_date(text: str) -> date | None:
    """godfat's Date.parse over the TSV's YYYYMMDD field."""
    text = text.strip()
    if len(text) != 8 or not text.isdigit():
        return None

    return date(int(text[:4]), int(text[4:6]), int(text[6:8]))


def parse_gacha_pools(r1_text: str) -> dict[int, list[int]]:
    """Map each GatyaDataSetR1 row number to its ordered unit ids (up to the ``-1``)."""
    pools: dict[int, list[int]] = {}
    for index, line in enumerate(r1_text.splitlines()):
        if not line[:1].isdigit():  # godfat: line =~ /\A\d+/
            continue

        ids: list[int] = []
        for cell in line.split(","):
            cell = cell.strip()
            try:
                value = int(cell)
            except ValueError:
                break

            if value == -1:
                break

            ids.append(value)

        pools[index] = ids

    return pools


def parse_series(option_text: str) -> dict[int, list[int]]:
    """Map each pool id (GatyaSetID) to its [seriesID, ItemID_Ticket] from
    GatyaData_Option_SetR.tsv. The series id is the stable id of a recurring gacha set -
    it stays the same across reruns even when the pool and the marketing subtitle both
    change; the ticket item tells the special capsules (Platinum/Legend) apart from
    rare-ticket ones.
    """
    series: dict[int, list[int]] = {}
    rows = csv.reader(option_text.splitlines(), delimiter="\t")
    header = next(rows, None)
    if header is None:
        return series

    columns = [header.index(name) for name in ("GatyaSetID", "seriesID", "ItemID_Ticket")]
    for row in rows:
        try:
            set_id, series_id, ticket = (int(row[column]) for column in columns)
        except IndexError, ValueError:
            continue

        series[set_id] = [series_id, ticket]

    return series


def parse_events(tsv_text: str) -> list[GachaEventRow]:
    """Parse one godfat event TSV into its rare-gacha rows (ported from tsv_reader.rb)."""
    events: list[GachaEventRow] = []
    for line in tsv_text.splitlines():
        if line.startswith("[") or not line.strip():  # [start]/[end] markers
            continue

        row = line.split("\t")
        if len(row) <= _POOL_OFFSET:
            continue

        try:
            if int(row[8]) != _RARE_GACHA:  # 'type' field
                continue

            offset = int(row[_POOL_OFFSET])
        except ValueError:
            continue

        start, end = _parse_date(row[0]), _parse_date(row[2])
        if start is None or end is None:
            continue

        blocks = row[_POOL_OFFSET + 1 :]
        pools = [blocks[i : i + _POOL_FIELDS] for i in range(0, len(blocks), _POOL_FIELDS)]
        if not 1 <= offset <= len(pools):
            continue

        pool = pools[offset - 1]
        if len(pool) < _POOL_FIELDS:
            continue

        try:
            pool_id = int(pool[0])
            rare, supa, uber = int(pool[6]), int(pool[8]), int(pool[10])
            legend = int(pool[12] or 0)
            guaranteed = int(pool[11]) > 0
            step_up = int(pool[3]) & 4 == 4
        except ValueError:
            continue

        if pool_id <= 0:
            continue

        events.append(
            GachaEventRow(
                f"{start.isoformat()}_{pool_id}",
                pool[14].strip(),
                start,
                end,
                pool_id,
                rare,
                supa,
                uber,
                legend,
                guaranteed,
                step_up,
            )
        )

    return events


def merge_events(event_lists: list[list[GachaEventRow]]) -> list[GachaEventRow]:
    """Combine the dated TSV snapshots into one list, keeping one row per event id
    (godfat's EventsReader)."""
    merged: dict[str, GachaEventRow] = {}
    for events in event_lists:
        for event in events:
            merged[event.event_id] = event

    return sorted(merged.values(), key=lambda e: (e.start, e.pool_id))


def build_banner(
    event: GachaEventRow,
    pools: Mapping[int, list[int]],
    units: Mapping[int, tuple[str, str]],
) -> Banner:
    """Build a rollable Banner: rates from the event, pools from its GatyaDataSet row
    grouped by rarity in row order, unit ids turned into names via ``units`` (id -> name,
    rarity). godfat's legend rate is whatever's left over after the other three."""
    rates = {
        Rarity.RARE: event.rare,
        Rarity.SUPER_RARE: event.supa,
        Rarity.UBER_SUPER_RARE: event.uber,
        Rarity.LEGEND_RARE: event.legend,
    }

    grouped: dict[Rarity, list[str]] = {rarity: [] for rarity in _RARITY_ORDER}
    for unit_id in pools.get(event.pool_id, ()):
        entry = units.get(unit_id)
        if entry is None:
            continue

        name, rarity = entry
        grouped.setdefault(Rarity(rarity), []).append(name)

    return Banner(
        event.event_id, event.name, "", rates, {r: tuple(names) for r, names in grouped.items()}
    )


def _event_files(lang: str) -> list[str]:
    """List every event-TSV filename in godfat's repo (paginated gitlab tree)."""
    names: list[str] = []
    page = 1

    while True:
        batch = json.loads(_get(_EVENTS_TREE.format(lang=lang, page=page)))
        names += [entry["name"] for entry in batch if entry["name"].endswith(".tsv")]
        if len(batch) < 100:
            return names

        page += 1


def download_events(lang: str = "en") -> list[GachaEventRow]:
    """Fetch and merge every event TSV into the full schedule (network)."""
    lists = [
        parse_events(_get(_EVENTS_RAW.format(lang=lang, name=name)).decode("utf-8", "replace"))
        for name in _event_files(lang)
    ]

    return merge_events(lists)


def download_gatya(
    country: str = "en", tarball: bytes | None = None
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Fetch the newest BCData tarball; parse GatyaDataSetR1 into pools and the option
    file into the pool->series map (network). Pass pre-downloaded bytes via *tarball* to
    skip the network fetch (workaround for the expired BCData TLS cert)."""
    if tarball is None:
        metadata = json.loads(_get(METADATA_URL))
        tarball = _get(release_url(metadata, latest_version(metadata, country), country))

    with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:xz") as tar:
        r1 = tar.extractfile("./DataLocal/GatyaDataSetR1.csv").read().decode("utf-8", "replace")
        opt = tar.extractfile("./DataLocal/GatyaData_Option_SetR.tsv").read()

    return parse_gacha_pools(r1), parse_series(opt.decode("utf-8", "replace"))


def event_records(events: Iterable[GachaEventRow]) -> list[dict]:
    """Events as JSON records for gacha_events.json."""
    return [
        {
            "event_id": e.event_id,
            "name": e.name,
            "start": e.start.isoformat(),
            "end": e.end.isoformat(),
            "pool_id": e.pool_id,
            "rare": e.rare,
            "supa": e.supa,
            "uber": e.uber,
            "legend": e.legend,
            "guaranteed": e.guaranteed,
            "step_up": e.step_up,
        }
        for e in events
    ]


def pool_records(pools: Mapping[int, list[int]], event_rows: Iterable[GachaEventRow]) -> dict:
    """Only the pools referenced by an event, as {str(pool_id): [ids]} for gacha_pools.json."""
    referenced = {e.pool_id for e in event_rows}

    return {str(pid): pools[pid] for pid in sorted(referenced) if pid in pools}


def series_records(series: Mapping[int, list[int]], event_rows: Iterable[GachaEventRow]) -> dict:
    """Only the referenced pools' entries, as {str(pool_id): [series_id, ticket_id]}."""
    referenced = {e.pool_id for e in event_rows}

    return {str(pid): series[pid] for pid in sorted(referenced) if pid in series}


@cache
def load_events(path: Path = EVENTS_PATH) -> list[GachaEventRow]:
    """Read the committed event schedule back into typed rows. Memoized: the file only
    changes on a re-import (a fresh process), and the rows are frozen and read-only."""
    return [
        GachaEventRow(
            r["event_id"],
            r["name"],
            date.fromisoformat(r["start"]),
            date.fromisoformat(r["end"]),
            r["pool_id"],
            r["rare"],
            r["supa"],
            r["uber"],
            r["legend"],
            r["guaranteed"],
            r["step_up"],
        )
        for r in json.loads(path.read_text(encoding="utf-8"))
    ]


@cache
def load_pools(path: Path = POOLS_PATH) -> dict[int, list[int]]:
    """Read the committed pools back as {pool_id: [ids]}. Memoized alongside load_events -
    same committed-until-reimport lifetime, consumed read-only (the roller types it Mapping)."""
    return {int(k): v for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def load_series(path: Path = SERIES_PATH) -> dict[int, int]:
    """Read the committed series map back as {pool_id: series_id}."""
    return {int(k): v[0] for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def load_tickets(path: Path = SERIES_PATH) -> dict[int, int]:
    """Read the committed series map back as {pool_id: ticket item id}."""
    return {int(k): v[1] for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def refresh(lang: str = "en", tarball: bytes | None = None) -> tuple[int, int]:
    """Fetch the live schedule + pools + series and rewrite the committed data files
    (network). Pass pre-downloaded BCData bytes via *tarball* to skip that TLS fetch."""
    events = download_events(lang)
    pools, series = download_gatya(lang, tarball=tarball)
    kept = pool_records(pools, events)

    EVENTS_PATH.write_text(json.dumps(event_records(events), ensure_ascii=False), encoding="utf-8")
    POOLS_PATH.write_text(json.dumps(kept), encoding="utf-8")
    SERIES_PATH.write_text(json.dumps(series_records(series, events)), encoding="utf-8")

    return len(events), len(kept)
