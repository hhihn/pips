"""Care-child selection, exact time allocation and safe curated CSV refresh."""

import csv
from decimal import Decimal
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest


SRC_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC_DIR))

from create_row_view import (
    DEFAULT_INPUT, EVENT_COLUMNS, PHASE_DURATION_COLUMNS, SEQUENCE_COLUMNS,
    SPEECH_COLUMN, TIMING_COLUMNS, WITHIN_COLUMNS, add_event_timing,
    add_sequences_to_events, calculate_event_timing, find_pflegekind_with_same_time,
    get_events, refresh_overview, sum_531_for_matching_pflegekind,
    sum_531_within_main_window, time_milliseconds,
)
from consolidate_csv import (
    EXPORT_COLUMNS, OVERVIEW_RETAIN_COLUMNS, PROPORTION_COLUMNS, add_proportions,
    merge_overview, write_csv_atomic,
)


def sequence(code, start, end):
    return {
        "Sequence_Code": code, "Sequence_Start": str(start), "Sequence_End": str(end),
        "Sequence Duration": str(time_milliseconds(end) - time_milliseconds(start)),
    }


def event(*sequences, child="5.5.1 K1", start=0, end=10):
    return {
        "Filename": "example.xlsx", "Child_Start": str(start), "Child_End": str(end),
        "Sequences": [sequence("6.1.1 Pflegesituation", start, end),
                      sequence(child, start, end), *sequences],
    }


def speech(start, end, child="5.5.1 K1"):
    return [sequence("5.3.1 FK spricht", start, end), sequence(child, start, end)]


@pytest.mark.parametrize("value,expected", [
    ("0:01:02,500", 62500), ("1:02.5", 62500), ("62.5", 62500),
    ("01:02:03.004", 3723004), (0, 0),
])
def test_timestamp_formats_have_exact_millisecond_values(value, expected):
    assert time_milliseconds(value) == expected


@pytest.mark.parametrize("value", ["", "bad", "NaN", "Infinity", "-1", "1:60", "0:60:00", "0.0001", "1.5:00"])
def test_invalid_timestamps_fail_instead_of_becoming_zero(value):
    with pytest.raises(ValueError, match="Invalid timestamp"):
        time_milliseconds(value)


def test_only_exactly_child_matched_speech_counts_with_multiple_recipients():
    row = event(
        sequence("6.1.2 Vorphase", 0, 10),
        *speech(1, 3), sequence("5.5.2 K2", 1, 3), sequence("5.5.11 Gruppe", 1, 3),
        *speech(4, 5, "5.5.2 K2"), sequence("5.3.1 FK spricht", 6, 7),
        sequence("5.3.1 FK spricht", 8, 9), sequence("5.5.1 K1", 8, "9.001"),
    )
    values, _ = calculate_event_timing(row)
    assert values[SPEECH_COLUMN] == 2000
    assert values[WITHIN_COLUMNS["6.1.1"]] == 2000
    assert values[WITHIN_COLUMNS["6.1.2"]] == 2000


def test_child_ten_is_distinct_from_child_one_and_labels_do_not_affect_matching():
    row = event(*speech(1, 3, "5.5.10 other label"), *speech(4, 6), child="5.5.10 K10")
    assert calculate_event_timing(row)[0][SPEECH_COLUMN] == 2000


def test_equivalent_timestamp_spellings_match_exactly():
    row = event(sequence("5.3.1", "0:00:01,000", "0:00:02,5"),
                sequence("5.5.1 K1", "00:01.0", "2.500"))
    assert calculate_event_timing(row)[0][SPEECH_COLUMN] == 1500


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_ambiguous_care_child_fails_with_event_context(missing):
    row = event()
    if missing:
        row["Sequences"].pop()
    else:
        row["Sequences"].append(sequence("5.5.2 K2", 0, 10))
    with pytest.raises(ValueError, match=r"example.xlsx.*0.*10.*Missing or ambiguous Pflegekind"):
        calculate_event_timing(row)


def test_boundary_crossing_speech_is_split_across_phases():
    row = event(sequence("6.1.2", 0, 4), sequence("6.1.3", 4, 7),
                sequence("6.1.4", 7, 10), *speech(2, 9))
    values, diagnostics = calculate_event_timing(row)
    assert [values[WITHIN_COLUMNS[f"6.1.{p}"]] for p in range(1, 5)] == [7000, 2000, 3000, 2000]
    assert diagnostics == []


def test_all_repeated_phase_windows_and_union_of_duplicate_speech_are_used():
    row = event(sequence("6.1.2", 0, 3), sequence("6.1.2", 2, 4),
                sequence("6.1.2", 6, 10), sequence("6.1.2", 6, 10),
                *speech(1, 3), *speech(1, 3), *speech(2, 8))
    values, _ = calculate_event_timing(row)
    assert values[PHASE_DURATION_COLUMNS["6.1.2"]] == 8000
    assert values[SPEECH_COLUMN] == 7000
    assert values[WITHIN_COLUMNS["6.1.2"]] == 5000


def test_phase_overlaps_count_independently_and_total_is_not_the_phase_sum():
    row = event(sequence("6.1.2", 0, 6), sequence("6.1.3", 4, 10), *speech(3, 7))
    values, diagnostics = calculate_event_timing(row)
    assert [values[WITHIN_COLUMNS[f"6.1.{p}"]] for p in range(1, 5)] == [4000, 3000, 3000, 0]
    assert diagnostics == ["overlap 6.1.2/6.1.3: 2000 ms"]


def test_gaps_leave_speech_unassigned_to_phases_but_included_in_total():
    row = event(sequence("6.1.2", 0, 3), sequence("6.1.3", 7, 10), *speech(2, 8))
    values, diagnostics = calculate_event_timing(row)
    assert [values[WITHIN_COLUMNS[f"6.1.{p}"]] for p in range(1, 5)] == [6000, 1000, 1000, 0]
    assert diagnostics == ["phase gaps: 4000 ms"]


def test_speech_outside_care_and_touching_boundaries_has_no_overlap():
    row = event(sequence("6.1.2", 1, 4), *speech(0, 1), *speech(10, 12),
                *speech(4, 5), start=1, end=10)
    values, _ = calculate_event_timing(row)
    assert values[WITHIN_COLUMNS["6.1.1"]] == 1000
    assert values[WITHIN_COLUMNS["6.1.2"]] == 0


def test_missing_phases_and_missing_speech_have_zero_durations():
    values, _ = calculate_event_timing(event())
    assert all(value == 0 for value in values.values())


@pytest.mark.parametrize("bad", [sequence("5.3.1", 5, 4),
                                     sequence("6.1.3", 5, 4),
                                     sequence("5.5.1 K1", 5, 4),
                                     {"Sequence_Code": "5.3.1", "Sequence_Start": "bad", "Sequence_End": "2"}])
def test_invalid_relevant_intervals_raise_contextual_errors(bad):
    with pytest.raises(ValueError, match="example.xlsx"):
        calculate_event_timing(event(bad))


def test_reversed_unrelated_recipient_is_reported_without_changing_valid_speech():
    values, diagnostics = calculate_event_timing(event(*speech(1, 3), sequence("5.5.4 K4", 12, 0)))
    assert values[SPEECH_COLUMN] == 2000
    assert "ignored non-matching recipient 5.5.4: end before start" in diagnostics


def test_phase_outside_care_is_an_error():
    with pytest.raises(ValueError, match="extends outside"):
        calculate_event_timing(event(sequence("6.1.2", 0, 11)))


def test_existing_dataframe_helpers_use_the_same_filter_and_time_allocation():
    row = event(sequence("6.1.2", 0, 4), *speech(2, 6), *speech(7, 9, "5.5.2 K2"))
    df = find_pflegekind_with_same_time(pd.DataFrame([row]), output_column="Pflegekind")
    df = sum_531_for_matching_pflegekind(df, output_col="speech")
    df = sum_531_within_main_window(df, "6.1.2", "pre")
    assert df.loc[0, "speech"] == 4000
    assert df.loc[0, "pre"] == 2000
    df = add_event_timing(df)
    assert df.loc[0, SPEECH_COLUMN] == df.loc[0, "speech"]
    assert df.loc[0, WITHIN_COLUMNS["6.1.2"]] == df.loc[0, "pre"]


def raw_rows(row):
    first = {column: "" for column in EVENT_COLUMNS}
    first.update({key: value for key, value in row.items() if key != "Sequences"})
    first.update({
        "Parent_Code": "5.4.1", "Parent_Start": "0", "Parent_End": "100",
        "Child_Code": "6.1.1", "Child Duration": str(time_milliseconds(row["Child_End"]) - time_milliseconds(row["Child_Start"])),
        "Matched_Code": "6.2.1 Nase putzen", "Matched_Start": row["Child_Start"],
        "Matched_End": row["Child_End"],
        "Matched Duration": str(time_milliseconds(row["Child_End"]) - time_milliseconds(row["Child_Start"])),
    })
    return [{**first, **seq, "Sequence_Order": str(i)} for i, seq in enumerate(row["Sequences"], 1)]


def write_csv(path, fields, rows, encoding="utf-8"):
    with path.open("w", encoding=encoding, newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def overview_row(filename="example.xlsx", duration="10000"):
    return {"Filename": filename, "Situation": "6.2.1 Nase putzen", "Situation_Duration": duration,
            "curated_note": "leave unchanged", **dict.fromkeys(TIMING_COLUMNS, "0.0")}


def refresh_fixture(tmp_path, events=None, overview=None, encoding="utf-8"):
    events = events if events is not None else [event(sequence("6.1.2", 0, 4), *speech(2, 6))]
    rows = [row for item in events for row in raw_rows(item)]
    source = tmp_path / "sequences.csv"
    write_csv(source, [*EVENT_COLUMNS, *SEQUENCE_COLUMNS], rows)
    curated = tmp_path / "overview.csv"
    overview = overview if overview is not None else [overview_row()]
    write_csv(curated, list(overview[0]), overview, encoding)
    return source, curated


def test_missing_parent_metadata_still_attaches_sequences():
    rows = raw_rows(event(*speech(1, 3)))
    for row in rows:
        row["Parent_Code"] = float("nan")
    source = pd.DataFrame(rows)
    events = add_sequences_to_events(get_events(source), source)
    assert len(events.loc[0, "Sequences"]) == 4
    assert add_event_timing(events).loc[0, SPEECH_COLUMN] == 2000


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig"])
def test_refresh_retains_selection_order_other_cells_and_is_byte_idempotent(tmp_path, encoding):
    first = event(sequence("6.1.2", 0, 4), *speech(2, 6))
    second = {**event(*speech(1, 3)), "Filename": "second.xlsx"}
    excluded = {**event(*speech(1, 5)), "Filename": "excluded.xlsx"}
    overview = [overview_row("second.xlsx"), overview_row(), overview_row()]
    source, curated = refresh_fixture(tmp_path, [first, second, excluded], overview, encoding)
    original = curated.read_bytes()
    preview = refresh_overview(source, curated, dry_run=True)
    assert curated.read_bytes() == original
    report = refresh_overview(source, curated)
    assert report == preview
    assert report["changed_rows"] == 3
    with curated.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        refreshed = list(reader)
        assert reader.fieldnames == list(overview[0])
    assert [row["Filename"] for row in refreshed] == ["second.xlsx", "example.xlsx", "example.xlsx"]
    assert all(row["curated_note"] == "leave unchanged" for row in refreshed)
    assert refreshed[1][WITHIN_COLUMNS["6.1.2"]] == "2000"
    assert refreshed[1][WITHIN_COLUMNS["6.1.1"]] == "4000"
    assert curated.read_bytes().startswith(b"\xef\xbb\xbf") == (encoding == "utf-8-sig")
    corrected_bytes = curated.read_bytes()
    assert refresh_overview(source, curated)["changed_rows"] == 0
    assert curated.read_bytes() == corrected_bytes


def test_identical_values_from_different_raw_candidates_are_accepted(tmp_path):
    source, curated = refresh_fixture(tmp_path, [event(*speech(1, 3)), event(*speech(21, 23), start=20, end=30)])
    assert refresh_overview(source, curated)["changed_rows"] == 1


@pytest.mark.parametrize("failure", ["unmatched", "ambiguous", "invalid"])
def test_refresh_validation_failure_preserves_entire_existing_output(tmp_path, failure):
    if failure == "unmatched":
        source, curated = refresh_fixture(tmp_path, overview=[overview_row(), overview_row("missing.xlsx")])
    elif failure == "ambiguous":
        source, curated = refresh_fixture(tmp_path, [event(*speech(1, 3)), event(*speech(21, 24), start=20, end=30)])
    else:
        source, curated = refresh_fixture(tmp_path, [event(sequence("5.3.1", 5, 4))])
    original = curated.read_bytes()
    with pytest.raises(ValueError):
        refresh_overview(source, curated)
    assert curated.read_bytes() == original


def test_refresh_refuses_to_overwrite_raw_input(tmp_path):
    source, _ = refresh_fixture(tmp_path)
    original = source.read_bytes()
    with pytest.raises(ValueError, match="overwrite"):
        refresh_overview(source, source)
    assert source.read_bytes() == original


def test_cli_dry_run_reports_corrections_without_writing(tmp_path):
    source, curated = refresh_fixture(tmp_path)
    original = curated.read_bytes()
    result = subprocess.run([sys.executable, "-B", str(SRC_DIR / "create_row_view.py"),
                             "--input", str(source), "--refresh-overview", str(curated), "--dry-run"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "Dry run: 1/1 rows changed" in result.stdout
    assert "2000 ms" in result.stdout
    assert curated.read_bytes() == original


def test_zero_duration_ratios_are_blank_and_invalid_ratios_fail():
    row = {"id": "test", "Situation_Duration": "10", SPEECH_COLUMN: "4",
           **dict.fromkeys(TIMING_COLUMNS, "0")}
    row[WITHIN_COLUMNS["6.1.1"]] = "4"
    row[PHASE_DURATION_COLUMNS["6.1.2"]] = "4"
    row[WITHIN_COLUMNS["6.1.2"]] = "2"
    add_proportions([row], list(row))
    assert Decimal(row["5_3_1_Proportion_Talking_PK_within_6_1_1"]) == Decimal("0.4")
    assert Decimal(row["5_3_1_Proportion_Talking_PK_within_6_1_2"]) == Decimal("0.5")
    assert row["5_3_1_Proportion_Talking_PK_within_6_1_3"] == ""
    assert row["5_3_1_Proportion_Talking_PK_within_6_1_4"] == ""
    for talking, window, total in [(5, 4, 6), (1, 0, 6), (5, 6, 4)]:
        invalid = {key: value for key, value in row.items() if key not in PROPORTION_COLUMNS}
        invalid[WITHIN_COLUMNS["6.1.2"]] = str(talking)
        invalid[PHASE_DURATION_COLUMNS["6.1.2"]] = str(window)
        invalid[WITHIN_COLUMNS["6.1.1"]] = str(total)
        with pytest.raises(ValueError, match="exceeds"):
            add_proportions([invalid], list(invalid))


def test_refresh_and_merge_end_to_end_convert_once_and_preserve_export(tmp_path):
    source, curated = refresh_fixture(tmp_path)
    refresh_overview(source, curated)
    fields = [column for column in EXPORT_COLUMNS if column not in OVERVIEW_RETAIN_COLUMNS and column not in PROPORTION_COLUMNS]
    merged_row = dict.fromkeys(fields, "0")
    merged_row.update({"id": "original-id", "Filename": "example.xlsx", "Situation_Code": "6.2.1",
                       "Situation_Duration": "10", "cluster": "1"})
    merged = tmp_path / "first.csv"
    output = tmp_path / "final.csv"
    write_csv(merged, fields, [merged_row])
    assert merge_overview(merged, curated, output, OVERVIEW_RETAIN_COLUMNS) == 1
    with output.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
    assert reader.fieldnames == list(EXPORT_COLUMNS.values())
    assert rows[0]["ID"] == "original-id"
    assert Decimal(rows[0]["Total_Educator-Speech-Duration"]) == 4
    assert Decimal(rows[0]["Pre-Action_Educator-Speech_Duration"]) == 2
    assert Decimal(rows[0]["Total_Educator-Speech_Proportion"]) == Decimal("0.4")
    assert Decimal(rows[0]["Pre-Action_Educator-Speech_Proportion"]) == Decimal("0.5")
    assert rows[0]["Action_Educator-Speech_Proportion"] == ""


def test_invalid_merge_leaves_previous_export_untouched(tmp_path):
    source, curated = refresh_fixture(tmp_path)
    refresh_overview(source, curated)
    fields = [column for column in EXPORT_COLUMNS if column not in OVERVIEW_RETAIN_COLUMNS and column not in PROPORTION_COLUMNS]
    merged_row = dict.fromkeys(fields, "0")
    merged_row.update({"id": "test", "Filename": "example.xlsx", "Situation_Code": "6.2.1",
                       "Situation_Duration": "10", "cluster": "1"})
    merged = tmp_path / "first.csv"
    write_csv(merged, fields, [merged_row])
    with curated.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        overview_fields = reader.fieldnames
        rows = list(reader)
    rows[0][WITHIN_COLUMNS["6.1.2"]] = "5000"
    write_csv(curated, overview_fields, rows)
    output = tmp_path / "final.csv"
    output.write_bytes(b"existing export\n")
    with pytest.raises(ValueError, match="exceeds"):
        merge_overview(merged, curated, output, OVERVIEW_RETAIN_COLUMNS)
    assert output.read_bytes() == b"existing export\n"


@pytest.mark.parametrize("invalid_value", ["bad", "NaN", "Infinity", "-1"])
def test_invalid_export_duration_fails_with_id(invalid_value):
    row = {"id": "invalid-id", "Situation_Duration": "10", **dict.fromkeys(TIMING_COLUMNS, "0")}
    row[WITHIN_COLUMNS["6.1.1"]] = invalid_value
    with pytest.raises(ValueError, match="invalid-id"):
        add_proportions([row], list(row))


@pytest.mark.parametrize("operation", ["refresh", "export"])
def test_write_failure_keeps_existing_csv_and_cleans_up_temporary_file(tmp_path, monkeypatch, operation):
    source, curated = refresh_fixture(tmp_path)
    original = curated.read_bytes()
    filenames = set(tmp_path.iterdir())

    def fail(*args, **kwargs):
        raise OSError("simulated write failure")

    monkeypatch.setattr(csv.DictWriter, "writerows", fail)
    with pytest.raises(OSError, match="simulated write failure"):
        if operation == "refresh":
            refresh_overview(source, curated)
        else:
            write_csv_atomic(curated, ["column"], [{"column": "new"}])
    assert curated.read_bytes() == original
    assert set(tmp_path.iterdir()) == filenames


def test_curated_repository_overview_matches_the_shared_raw_calculation():
    overview = SRC_DIR.parent / "data/sauber_übersicht_situationen_länge_pro_datei.csv"
    report = refresh_overview(DEFAULT_INPUT, overview, dry_run=True)
    assert report["rows"] == 86
    assert report["changed_rows"] == 0
    assert sum(any(message.startswith("overlap ") for message in detail["diagnostics"])
               for detail in report["details"]) == 3
    assert sum(any(message.startswith("phase gaps:") for message in detail["diagnostics"])
               for detail in report["details"]) == 15
