from datetime import date

from neko.gachadata import (
    GachaEventRow,
    build_banner,
    event_records,
    load_events,
    merge_events,
    parse_events,
    parse_gacha_pools,
    parse_series,
)
from neko.models import Rarity


def tsv_row(start="20250101", end="20250108", type_="1", offset="1", pools=()):
    event = [start, "", end, "", "0", "", "", "", type_, offset]  # fields 0..9
    blocks = []
    for p in pools:
        block = ["0"] * 15
        block[0] = str(p["id"])
        block[3] = str(p.get("step_up", 0))
        block[6], block[8], block[10] = str(p["rare"]), str(p["supa"]), str(p["uber"])
        block[11] = str(p.get("guaranteed", 0))
        block[12] = str(p.get("legend", 0))
        block[14] = p["name"]
        blocks += block
    return "\t".join(event + blocks)


POOL = {"id": 42, "rare": 7000, "supa": 2500, "uber": 500, "name": "Test Banner"}


def test_parse_events_reads_rates_dates_and_id():
    (event,) = parse_events(tsv_row(pools=[POOL]))
    assert event.event_id == "2025-01-01_42"
    assert event.name == "Test Banner"
    assert (event.start, event.end) == (date(2025, 1, 1), date(2025, 1, 8))
    assert (event.rare, event.supa, event.uber) == (7000, 2500, 500)


def test_parse_events_skips_non_rare_gacha_and_markers():
    tsv = "[start]\n" + tsv_row(type_="0", pools=[POOL]) + "\n"
    assert parse_events(tsv) == []


def test_parse_events_uses_the_active_pool_by_offset():
    other = {"id": 99, "rare": 6000, "supa": 3000, "uber": 1000, "name": "Other"}
    (event,) = parse_events(tsv_row(offset="2", pools=[POOL, other]))
    assert event.pool_id == 99 and event.uber == 1000


def test_parse_events_flags_guaranteed_and_step_up():
    (guaranteed,) = parse_events(tsv_row(pools=[{**POOL, "guaranteed": 1}]))
    (step,) = parse_events(tsv_row(pools=[{**POOL, "step_up": 4}]))
    assert guaranteed.guaranteed is True and guaranteed.step_up is False
    assert step.step_up is True


def test_parse_gacha_pools_stops_at_terminator_and_keeps_row_index():
    pools = parse_gacha_pools("header,line\n10,20,30,-1,//comment\n40,50,-1\n")
    assert pools == {1: [10, 20, 30], 2: [40, 50]}


def test_parse_series_maps_pool_to_series_and_ticket_by_header_column():
    option = (
        "GatyaSetID\tBannerON_OFF\tItemID_Ticket\tseriesID\n"
        "953\t0\t29\t21\n966\t1\t29\t21\nbad\trow\there\ttoo\n"
    )
    assert parse_series(option) == {953: [21, 29], 966: [21, 29]}


def test_build_banner_groups_pool_by_rarity_in_row_order():
    event = GachaEventRow(
        "e", "B", date(2025, 1, 1), date(2025, 1, 8), 42, 7000, 2500, 500, 0, True, False
    )
    pools = {42: [100, 200, 300]}
    units = {100: ("Aa", "Rare"), 200: ("Bb", "Super Rare"), 300: ("Cc", "Rare")}
    banner = build_banner(event, pools, units)
    assert banner.pool(Rarity.RARE) == ("Aa", "Cc")
    assert banner.pool(Rarity.SUPER_RARE) == ("Bb",)
    assert banner.rates[Rarity.UBER_SUPER_RARE] == 500


def test_merge_events_dedupes_by_event_id():
    a = parse_events(tsv_row(pools=[POOL]))
    b = parse_events(tsv_row(pools=[{**POOL, "name": "Renamed"}]))  # same id, newer snapshot
    merged = merge_events([a, b])
    assert len(merged) == 1 and merged[0].name == "Renamed"


def test_event_records_roundtrip(tmp_path):
    (event,) = parse_events(tsv_row(pools=[POOL]))
    import json

    path = tmp_path / "events.json"
    path.write_text(json.dumps(event_records([event])), encoding="utf-8")
    assert load_events(path) == [event]
