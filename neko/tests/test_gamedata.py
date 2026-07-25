from neko.gamedata import parse_cannons, parse_combos, parse_evolve, parse_items, parse_talents

# The real Cat Army row: units 0-4 first forms, effect 5 (Starting Money Up), size Sm.
_CAT_ARMY = "0,-1,-1,0,0,1,0,2,0,3,0,4,0,5,0,-1"
# Behind Closed Doors: two units, the empty pair slots are -1.
_CLOSED_DOORS = "2,-1,-1,13,0,12,0,-1,-1,-1,-1,-1,-1,6,0,-1"

_EFFECTS = "Unit Attack Up|\n" * 7
_PARAMS = "10\t15\t20\t30\t-20\n" * 7
# A show-everything first line, then the game's effect groups.
_FILTERS = "0\t1\t2\t3\n0\t1\n2\t3"


def _combos(data, names="Cat Army\nx\nBehind Closed Doors"):
    return parse_combos(data, names, _EFFECTS, _PARAMS, _FILTERS)


def _acquisition(*slots, unit=9, limits=()):
    """A SkillAcquisition file with one unit whose slot abilities are given; params are
    (1, 50) for the first pair, limit flags per slot from ``limits``."""
    cells = [unit, 0]
    for index in range(8):
        ability = slots[index] if index < len(slots) else 0
        limit = limits[index] if index < len(limits) else 0
        cells += [ability, 10, 1, 50, 0, 0, 0, 0, 0, 0, 7, 4, -1, limit]
    return "ID,typeID\n" + ",".join(str(cell) for cell in cells)


def _unitbuy(tf_level=30, uf_level=-1, tf_xp=500000, uf_xp=0, tf_items=(), uf_items=()):
    """One unitbuy row with the evolution block filled in."""
    cells = [0] * 63
    cells[25], cells[26], cells[27], cells[38] = tf_level, uf_level, tf_xp, uf_xp
    for offset, (item, count) in enumerate(tf_items):
        cells[28 + offset * 2], cells[29 + offset * 2] = item, count
    for offset, (item, count) in enumerate(uf_items):
        cells[39 + offset * 2], cells[40 + offset * 2] = item, count
    return ",".join(str(cell) for cell in cells)


def test_combo_reads_units_effect_and_size():
    combo = _combos(_CAT_ARMY)["combos"][0]
    assert combo == {
        "id": 0,
        "name": "Cat Army",
        "effect": 5,
        "size": 0,
        "units": [[0, 0], [1, 0], [2, 0], [3, 0], [4, 0]],
    }


def test_combo_drops_empty_unit_slots():
    assert _combos(_CLOSED_DOORS)["combos"][0]["units"] == [[13, 0], [12, 0]]


def test_combo_without_a_name_is_dropped():
    assert (
        _combos("1,-1,-1,0,0,-1,-1,-1,-1,-1,-1,-1,-1,0,0,-1", names="Cat Army\n＠")["combos"] == []
    )


def test_combo_values_keep_one_magnitude_per_size():
    assert _combos(_CAT_ARMY)["values"][0] == [10, 15, 20, 30]


def test_combo_categories_skip_the_show_all_line():
    assert _combos(_CAT_ARMY)["categories"] == [[0, 1], [2, 3]]


def test_talent_slots_read_ability_and_cost_curve():
    slot = parse_talents(_acquisition(10), "", "")["units"][9][0]
    assert slot == {
        "ability": 10,
        "max": 10,
        "params": [[1, 50]],
        "text": 7,
        "curve": 4,
        "ultra": False,
    }


def test_talent_empty_slots_are_dropped():
    assert len(parse_talents(_acquisition(10, 0, 20), "", "")["units"][9]) == 2


def test_talent_limit_flag_marks_ultra():
    slots = parse_talents(_acquisition(10, 20, limits=(0, 1)), "", "")["units"][9]
    assert [slot["ultra"] for slot in slots] == [False, True]


def test_talent_curves_read_np_costs_per_level():
    curves = parse_talents(_acquisition(10), "lvID,lv1,lv2\n1,25,5\n2,5,5", "")["curves"]
    assert curves == {1: [25, 5], 2: [5, 5]}


def test_talent_texts_key_descriptions_by_id():
    texts = parse_talents(_acquisition(10), "", "textID|x\n1|Gain the ability.")["texts"]
    assert texts == {1: "Gain the ability."}


def test_evolve_reads_true_form_costs():
    evolve = parse_evolve(_unitbuy(tf_items=((31, 3), (40, 1))))[0]
    assert evolve["tf"] == {"level": 30, "xp": 500000, "items": [[31, 3], [40, 1]]}


def test_evolve_without_ultra_form_reports_none():
    assert parse_evolve(_unitbuy())[0]["uf"] is None


def test_evolve_reads_ultra_form_costs():
    row = _unitbuy(uf_level=60, uf_xp=2000000, uf_items=((181, 1), (38, 10)))
    assert parse_evolve(row)[0]["uf"] == {"level": 60, "xp": 2000000, "items": [[181, 1], [38, 10]]}


def test_evolve_costless_units_are_dropped():
    assert parse_evolve(_unitbuy(tf_xp=0)) == {}


def test_items_key_names_by_row_and_drop_fillers():
    text = "Speed Up|desc|\nTreasure Radar|x|\ndummy|＠|\n|\n＠|"
    assert parse_items(text) == {0: "Speed Up", 1: "Treasure Radar"}


# The real Slow Beam data: two construction stages, then Lv1+ upgrade rows.
_CANNON_ROWS = "12,1,5,3,4,0,0,0,0,0\n12,1,7,4,5,2,0,0,0,0\n24,2,9,5,7,3,0,0,0,0"
# Foundation/style rows carry their counts in the Z-material columns c10-17.
_BASE_ROWS = "24,2,0,0,0,0,0,0,0,0,3,2,2,1,0,0,0,0"
_DESCRIPTIONS = "0|Enhance Base|x|\n1|Slow Beam|y|"


def _cannons(base=None, deco=None):
    return parse_cannons(_DESCRIPTIONS, {1: {"cannon": _CANNON_ROWS, "base": base, "deco": deco}})


def test_cannon_splits_construction_stages_from_level_rows():
    parts = _cannons()[0]["parts"]["cannon"]
    assert parts["construction"] == [
        [12, 1, 5, 3, 4, 0, 0, 0, 0, 0],
        [12, 1, 7, 4, 5, 2, 0, 0, 0, 0],
    ]
    assert parts["levels"] == [[24, 2, 9, 5, 7, 3, 0, 0, 0, 0]]


def test_cannon_foundation_reads_the_z_material_columns():
    parts = _cannons(base=_BASE_ROWS)[0]["parts"]
    assert parts["base"] == {"construction": [], "levels": [[24, 2, 3, 2, 2, 1, 0, 0, 0, 0]]}


def test_cannon_without_foundation_or_style_keeps_only_the_cannon_part():
    assert sorted(_cannons()[0]["parts"]) == ["cannon"]


def test_cannon_names_come_from_the_descriptions_file():
    assert _cannons()[0]["name"] == "Slow Beam"
