"""What reaches the /fixed dashboard is checked against the document, in code.

The checks are pure functions fed with whatever the extractor wrote: every wrong
shape drops the item it sits in and never raises.
"""

import pytest

from src.dashboard_checks import (
    checked_kpis,
    checked_rows,
    checked_scope,
    checked_share,
    checked_trend,
    first_number,
    numbers_in,
    text_or_empty,
)

# Real rows of the Insee document.
INSEE = (
    "[Document: insee.pdf]\n"
    "2025T3 | 2025T4 | 2026T1 | 2026T2 | 2025 | 2026 (acquis)\n"
    "PIB | 0,4 | 0,3 | -0,2 | 0,0 | 0,9 | 0,3\n"
    "Dép. conso. ménages | 0,1 | 0,2 | -0,3 | 0,3 | 0,5 | 0,1\n"
    "Taux de marge | 32,4 | 32,5 | 31,5 | 31,5 | 32,4\n"
    "Production | 94 930 M€ | 1,5\n"
    "Parts | 30 | 40 | 60 | 10 | 20\n"
)

TRUE_TREND = [
    {"label": "2025T3", "value": 0.4},
    {"label": "2025T4", "value": 0.3},
    {"label": "2026T1", "value": -0.2},
    {"label": "2026T2", "value": 0.0},
]


def _points(labels, values):
    return [{"label": label, "value": value} for label, value in zip(labels, values)]


# --- numbers ------------------------------------------------------------------


def test_numbers_in_reads_decimal_commas_and_thousands_groups():
    found = numbers_in("PIB | 0,4 | -0,2 | 94 930 M€ | 1,5")
    assert found == {0.4, 0.2, 94930.0, 1.5}


@pytest.mark.parametrize("space", ["\u00a0", "\u202f"])
def test_numbers_in_accepts_narrow_and_no_break_spaces(space):
    assert 94930.0 in numbers_in(f"94{space}930 M€")


def test_numbers_in_reads_a_decimal_dot():
    assert numbers_in("rate 2.8 %") == {2.8}


def test_numbers_in_does_not_glue_a_period_to_the_next_value():
    # "2026 0,4": the second group is not a 3-digit thousands group.
    assert numbers_in("2026 0,4") == {2026.0, 0.4}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("+0,3 %", 0.3),
        ("-0,2", -0.2),
        ("−0,2", -0.2),
        ("94 930 M€", 94930.0),
        ("0,0", 0.0),
        ("n/a", None),
        ("", None),
    ],
)
def test_first_number_is_signed(text, expected):
    assert first_number(text) == expected


def test_text_or_empty_keeps_strings_only():
    assert text_or_empty("T") == "T"
    assert text_or_empty(None) == ""
    assert text_or_empty(12) == ""
    assert text_or_empty(["a"]) == ""


# --- KPIs ---------------------------------------------------------------------


def _kpi(**changes):
    return {
        "label": "PIB",
        "value": "0,4 %",
        "delta": "+0,3 %",
        "caption": "T3",
        **changes,
    }


def test_a_kpi_with_a_number_absent_from_the_document_is_dropped():
    kpis = [_kpi(), _kpi(label="x", value="7,77 %")]
    assert checked_kpis(kpis, INSEE) == [_kpi()]


def test_a_kpi_value_without_a_number_is_kept():
    kpis = [_kpi(value="n/a", delta="")]
    assert checked_kpis(kpis, INSEE) == kpis


def test_a_kpi_delta_not_written_in_the_document_is_blanked():
    assert checked_kpis([_kpi(delta="+0,6 %")], INSEE)[0]["delta"] == ""


def test_a_kpi_delta_with_no_number_is_blanked():
    assert checked_kpis([_kpi(delta="en hausse")], INSEE)[0]["delta"] == ""


def test_a_kpi_delta_longer_than_twelve_characters_is_blanked():
    kpi = _kpi(delta="+0,3 % vs 0,4")
    assert len(kpi["delta"]) == 13
    assert checked_kpis([kpi], INSEE)[0]["delta"] == ""


def test_kpis_are_cut_to_the_first_four():
    kpis = [_kpi(label=f"k{i}") for i in range(6)]
    assert [k["label"] for k in checked_kpis(kpis, INSEE)] == ["k0", "k1", "k2", "k3"]


def test_the_observed_spill_in_a_delta_is_blanked():
    spill = "+1,7 %}]}}\n\nVoici le tableau de bord demandé, avec les chiffres clés."
    assert checked_kpis([_kpi(delta=spill)], INSEE)[0]["delta"] == ""


def test_kpi_strings_that_are_not_strings_are_coerced_or_the_kpi_dropped():
    assert checked_kpis([_kpi(caption=3)], INSEE)[0]["caption"] == ""
    assert checked_kpis([_kpi(delta=None)], INSEE)[0]["delta"] == ""
    assert checked_kpis([_kpi(value=0.4)], INSEE) == []
    assert checked_kpis([_kpi(label=None)], INSEE) == []


# --- trend --------------------------------------------------------------------


def test_the_true_trend_is_kept():
    assert checked_trend(TRUE_TREND, INSEE) == TRUE_TREND


def test_a_trend_on_a_subset_of_the_header_columns_is_kept():
    # Positions in the header (not in the trend) say which cell to read.
    trend = _points(["2025T3", "2026T1", "2025"], [0.4, -0.2, 0.9])
    assert checked_trend(trend, INSEE) == trend


def test_the_observed_series_is_dropped():
    observed = _points(
        ["T2 2025", "T3 2025", "T4 2025", "T1 2026", "T2 2026"],
        [0.5, 0.3, -0.2, -0.2, 0],
    )
    assert checked_trend(observed, INSEE) == []


def test_true_labels_with_shifted_values_are_dropped():
    shifted = _points(["2025T3", "2025T4", "2026T1", "2026T2"], [0.3, -0.2, 0.0, 0.9])
    assert checked_trend(shifted, INSEE) == []


def test_true_values_under_shifted_labels_are_dropped():
    shifted = _points(["2025T4", "2026T1", "2026T2", "2025"], [0.4, 0.3, -0.2, 0.0])
    assert checked_trend(shifted, INSEE) == []


def test_a_flipped_sign_is_dropped():
    flipped = _points(["2025T3", "2025T4", "2026T1", "2026T2"], [0.4, 0.3, 0.2, 0.0])
    assert checked_trend(flipped, INSEE) == []


def test_values_of_two_different_rows_are_dropped():
    mixed = _points(["2025T3", "2025T4"], [0.4, 0.2])  # PIB, then conso
    assert checked_trend(mixed, INSEE) == []


def test_a_vertical_table_is_kept():
    document = "T1 | 41,2\nT2 | 43,0\n"
    trend = _points(["T1", "T2"], [41.2, 43.0])
    assert checked_trend(trend, document) == trend


def test_a_sentence_holding_the_label_and_the_value_supports_a_point():
    document = "Le PIB a reculé de -0,2 % au 2026T1 puis progressé de 0,3 % au 2026T2."
    trend = _points(["2026T1", "2026T2"], [-0.2, 0.3])
    assert checked_trend(trend, document) == trend


def test_a_vertical_point_needs_the_same_sign():
    document = "T1 | -41,2\nT2 | 43,0\n"
    assert checked_trend(_points(["T1", "T2"], [41.2, 43.0]), document) == []


def test_the_digits_of_a_label_do_not_support_its_own_value():
    # The header line holds "2025T3" and the number 3, but only through the label.
    digits = _points(["2025T3", "2025T4"], [3, 4])
    assert checked_trend(digits, INSEE) == []


def test_a_huge_integer_value_is_dropped_without_error_in_a_share_too():
    assert checked_share(_points(["a", "b"], [10**400, 30]), INSEE) == []


def test_a_trend_under_two_points_is_dropped():
    assert checked_trend(TRUE_TREND[:1], INSEE) == []


def test_zero_matches_a_written_zero_only():
    assert numbers_in("0,0") == {0.0}
    trend = _points(["2026T2", "2025T3"], [0.0, 0.4])
    assert checked_trend(trend, INSEE) == trend


def test_a_negative_value_does_not_match_the_same_digits_unsigned():
    document = "T1 | 0,2\nT2 | 0,3\n"
    assert checked_trend(_points(["T1", "T2"], [-0.2, 0.3]), document) == []


def test_labels_are_compared_with_normalized_whitespace():
    document = "2025T3  |  2025T4\nPIB | 0,4 | 0,3\n"
    trend = _points(["2025T3", "2025T4"], [0.4, 0.3])
    assert checked_trend(trend, document) == trend


@pytest.mark.parametrize(
    "raw",
    [
        "texte",
        None,
        ["a", "b"],
        [{"label": "2025T3"}, {"label": "2025T4", "value": 0.3}],
        [{"label": "2025T3", "value": "0,4"}, {"label": "2025T4", "value": 0.3}],
        [{"label": None, "value": 0.4}, {"label": "2025T4", "value": 0.3}],
        [{"label": "2025T3", "value": True}, {"label": "2025T4", "value": 0.3}],
        [{"label": "2025T3", "value": float("nan")}, {"label": "a", "value": 0.3}],
        [{"label": "2025T3", "value": 10**400}, {"label": "a", "value": 0.3}],
        [{"label": "2025T3", "value": float("inf")}, {"label": "a", "value": 0.3}],
    ],
)
def test_a_trend_of_the_wrong_shape_is_dropped_without_error(raw):
    assert checked_trend(raw, INSEE) == []


# --- share --------------------------------------------------------------------


def test_a_share_written_in_the_document_is_kept():
    share = _points(["a", "b", "c"], [30, 40, 60])
    assert checked_share(share, INSEE) == share


def test_a_share_with_a_value_absent_from_the_document_is_dropped():
    assert checked_share(_points(["a", "b"], [30, 55]), INSEE) == []


def test_a_share_with_a_non_positive_part_or_a_single_part_is_dropped():
    assert checked_share(_points(["a", "b"], [30, 0]), INSEE) == []
    assert checked_share(_points(["a", "b", "c"], [30, -30, 40]), INSEE) == []
    assert checked_share(_points(["a"], [30]), INSEE) == []


@pytest.mark.parametrize("raw", ["texte", None, [3, 4], [{"label": "a"}] * 2])
def test_a_share_of_the_wrong_shape_is_dropped_without_error(raw):
    assert checked_share(raw, INSEE) == []


# --- rows ---------------------------------------------------------------------


def _row(**changes):
    return {
        "name": "Dép. conso. ménages",
        "category": "Demande",
        "value": "+0,3 %",
        "delta": "+0,5 %",
        **changes,
    }


def test_a_row_delta_written_on_the_line_of_its_value_is_kept():
    assert checked_rows([_row()], INSEE) == [_row()]


def test_a_computed_row_delta_is_blanked():
    assert checked_rows([_row(delta="+0,6 %")], INSEE)[0]["delta"] == ""


def test_a_row_value_absent_from_the_document_drops_the_row():
    assert checked_rows([_row(value="+7,7 %")], INSEE) == []


def test_a_row_delta_on_another_line_than_its_value_is_blanked():
    # 0,4 is on the PIB line, 0,3 on both: only the shared line counts.
    assert (
        checked_rows([_row(value="+0,1 %", delta="+32,4 %")], INSEE)[0]["delta"] == ""
    )


def test_a_row_delta_longer_than_twelve_characters_is_blanked():
    row = _row(delta="+0,5 % sur un an")
    assert checked_rows([row], INSEE)[0]["delta"] == ""


def test_a_row_name_is_not_checked_against_the_document():
    assert checked_rows([_row(name="Consommation")], INSEE)[0]["name"] == "Consommation"


def test_rows_are_cut_to_the_first_eight():
    rows = [_row(name=f"r{i}") for i in range(10)]
    assert len(checked_rows(rows, INSEE)) == 8


def test_a_row_with_the_wrong_shape_is_dropped_or_coerced_without_error():
    assert checked_rows("texte", INSEE) == []
    assert checked_rows([None, 3, "x"], INSEE) == []
    assert checked_rows([_row(name=None)], INSEE) == []
    assert checked_rows([_row(value=None)], INSEE) == []
    assert checked_rows([_row(category=3)], INSEE)[0]["category"] == ""
    assert checked_rows([_row(delta=None)], INSEE)[0]["delta"] == ""


# --- scope --------------------------------------------------------------------

OPTIONS = [{"label": "Tout", "value": "all"}, {"label": "Ménages", "value": "hh"}]


def test_the_selected_scope_is_kept_when_it_is_an_option():
    assert checked_scope(OPTIONS, "hh") == {"options": OPTIONS, "selected": "hh"}


def test_the_selected_scope_falls_back_to_the_first_option():
    expected = {"options": OPTIONS, "selected": "all"}
    assert checked_scope(OPTIONS, "zz") == expected
    assert checked_scope(OPTIONS, None) == expected


def test_scope_options_of_the_wrong_shape_are_skipped():
    raw = [OPTIONS[0], {"label": "x"}, {"label": 1, "value": "y"}, "z", None]
    assert checked_scope(raw, "all") == {"options": [OPTIONS[0]], "selected": "all"}


@pytest.mark.parametrize("raw", [[], "texte", None, [{"label": "x"}]])
def test_no_valid_scope_option_means_no_scope(raw):
    assert checked_scope(raw, "all") is None
