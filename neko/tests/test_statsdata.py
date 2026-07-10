from neko.statsdata import (
    form_record,
    growth_pct,
    parse_curves,
    parse_frequencies,
    parse_stat_rows,
)

# The Cat's real level curve: +20% per level through 60, +10% after.
CAT_CURVE = [20] * 6 + [10] * 14


def _row(**overrides):
    """A stat row with the Cat's real numbers; keyword indices override columns."""
    cells = [0] * 117
    cells[0], cells[1], cells[2], cells[3] = 100, 3, 10, 8
    cells[4], cells[5], cells[6], cells[7], cells[13] = 15, 140, 50, 75, 8
    for index, value in overrides.items():
        cells[int(index.lstrip("c"))] = value
    return cells


def test_parse_pads_short_rows_to_the_full_column_set():
    assert len(parse_stat_rows("100,3,10,8")[0]) == 117


def test_parse_reads_one_row_per_form():
    assert len(parse_stat_rows("100,3,10,8\n200,3,10,16")) == 2


def test_parse_drops_blank_lines():
    assert parse_stat_rows("100,3\n\n0,0,0") == [[100, 3] + [0] * 115]


def test_parse_treats_junk_cells_as_zero():
    assert parse_stat_rows("100,x,10")[0][1] == 0


def test_curves_read_one_curve_per_unit():
    assert parse_curves("20,20\n10,10") == [[20, 20], [10, 10]]


def test_growth_reaches_the_cats_known_level_30_multiplier():
    assert growth_pct(CAT_CURVE, level=30) == 680


def test_growth_at_level_one_is_the_base():
    assert growth_pct(CAT_CURVE, level=1) == 100


def test_hp_matches_the_wikis_level_30_quote():
    assert form_record(_row(), CAT_CURVE, 37)["hp"] == 1700


def test_attack_matches_the_wikis_level_30_quote():
    assert form_record(_row(), CAT_CURVE, 37)["atk"] == 136


def test_dps_is_attack_over_the_frequency():
    assert form_record(_row(), CAT_CURVE, 37)["dps"] == 110


def test_multi_hit_attacks_sum_into_the_total():
    assert form_record(_row(c59=8, c60=8), CAT_CURVE, 37)["atk"] == 408


def test_no_frequency_leaves_dps_unknown():
    assert form_record(_row(), CAT_CURVE, None)["dps"] is None


def test_frequency_displays_in_seconds():
    assert form_record(_row(), CAT_CURVE, 37)["freq"] == 1.23


def test_recharge_displays_the_initial_seconds():
    assert form_record(_row(), CAT_CURVE, 37)["recharge"] == 5.07


def test_cost_is_the_chapter_two_figure():
    assert form_record(_row(), CAT_CURVE, 37)["cost"] == 75


def test_targets_name_the_flagged_traits():
    record = form_record(_row(c17=1, c20=1), CAT_CURVE, 37)
    assert record["targets"] == ["Black", "Angel"]


def test_immunities_name_the_flagged_effects():
    record = form_record(_row(c46=1, c50=1), CAT_CURVE, 37)
    assert record["immune"] == ["Waves", "Slow"]


def test_area_attack_flag_carries_over():
    assert form_record(_row(c12=1), CAT_CURVE, 37)["area"] is True


def test_effect_flags_become_plain_chips():
    record = form_record(_row(c30=1, c52=1), CAT_CURVE, 37)
    assert record["effects"] == ["Massive damage", "Zombie Killer"]


def test_freeze_reports_chance_and_seconds():
    record = form_record(_row(c25=20, c26=60), CAT_CURVE, 37)
    assert record["effects"] == ["Freeze 20% for 2.0s"]


def test_weaken_reports_the_reduced_attack_level():
    record = form_record(_row(c37=100, c38=90, c39=50), CAT_CURVE, 37)
    assert record["effects"] == ["Weaken 100% to 50% for 3.0s"]


def test_wave_reports_its_level():
    record = form_record(_row(c35=30, c36=3), CAT_CURVE, 37)
    assert record["effects"] == ["Wave 30% (Lv 3)"]


def test_mini_wave_is_named_as_such():
    record = form_record(_row(c35=100, c36=1, c94=1), CAT_CURVE, 37)
    assert record["effects"] == ["Mini-wave 100% (Lv 1)"]


def test_surge_unscales_its_stored_coordinates():
    record = form_record(_row(c86=30, c87=1200, c88=1200, c89=2), CAT_CURVE, 37)
    assert record["effects"] == ["Surge 30% (Lv 2, 300~600)"]


def test_multi_hit_chip_lists_each_hit():
    record = form_record(_row(c3=600, c59=600, c60=3600), CAT_CURVE, 37)
    assert record["effects"] == ["3 hits (600 + 600 + 3,600)"]


def test_long_distance_reports_its_band():
    record = form_record(_row(c44=350, c45=250), CAT_CURVE, 37)
    assert record["effects"] == ["Long distance 350~600"]


def test_omni_strike_flips_the_negative_band():
    record = form_record(_row(c44=350, c45=-900), CAT_CURVE, 37)
    assert record["effects"] == ["Omni strike -550~350"]


def test_strengthen_reports_threshold_and_boost():
    record = form_record(_row(c40=50, c41=100), CAT_CURVE, 37)
    assert record["effects"] == ["Attack +100% at 50% HP"]


def test_frequencies_key_forms_in_row_order():
    tsv = "id\tattack_frequency\n0\t37\n0\t40\n5\t600"
    assert parse_frequencies(tsv) == {(0, 0): 37, (0, 1): 40, (5, 0): 600}


def test_frequencies_skip_blank_cells_but_keep_counting_forms():
    tsv = "id\tattack_frequency\n0\t\n0\t40"
    assert parse_frequencies(tsv) == {(0, 1): 40}
