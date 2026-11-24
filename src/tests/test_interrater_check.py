"""Agreement tests use hand-computable cases, including extraction losses."""

import csv
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest


SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from care_overlap import extract_care_patterns, export_care_sequences
from interrater_check import (
    DEFAULT_CONFIG, Event, Video, align_situations, bootstrap_intervals,
    compare_timing, ordered_match, pair_files, presence_counts, presence_metrics,
    read_sequences, run_check, score_rows, timing_metrics, validate_config, video_id,
    export_report_tables,
    code_duration_counts, code_duration_metrics, summarize_code_durations,
)
from pattern_analyzer import PatternAnalyzer
from pattern_detector import PatternDetector


def frame(*rows):
    return pd.DataFrame(rows, columns=["Code", "Anfang", "Ende"])


def video(windows=((0, 10000),), events=()):
    result = Video("example_transformed.xlsx")
    result.situations = {f"s{i:03d}": window for i, window in enumerate(windows, 1)}
    for code, start, end, memberships in events:
        result.events[Event(code, start, end)] = set(memberships)
    return result


def test_overlap_extraction_recovers_situation_and_keeps_unclipped_boundaries(tmp_path):
    data = frame(
        ("6 Pflege > 6.1 Pflegekontext > 6.1.1 Pflegesituation", "0:02:30,8", "0:02:39,0"),
        ("6.2.2 Gesicht abwischen", "0:02:30,7", "0:02:37,0"),
        ("5.3.1 speech", "0:02:38,0", "0:02:41,0"),
        ("5.3.1 label changed", "0:02:38.000", "0:02:41.000"),
        ("5.3.2 touches start", "0:02:29,0", "0:02:30,8"),
        ("5.3.3 touches end", "0:02:39,0", "0:02:40,0"),
        ("5.2.1 zero duration", "0:02:31,0", "0:02:31,0"),
    )
    results = PatternDetector(sequence_scope="care-overlap").detect_patterns(data, "5-P-3_transformed_IR.xlsx")
    path = tmp_path / "sequences.csv"
    export_care_sequences(results, path)
    loaded = read_sequences(path)["5-P-3"]
    assert len(loaded.situations) == 1
    assert set(loaded.events) == {
        Event("6.1.1", 150800, 159000), Event("6.2.2", 150700, 157000),
        Event("5.3.1", 158000, 161000),
    }
    assert results[0].child_codes[0]["matching_6_2_codes"][0]["code"].startswith("6.2.2")


def test_no_setting_or_care_type_does_not_drop_situation(tmp_path):
    path = tmp_path / "sequences.csv"
    export_care_sequences(extract_care_patterns(frame(("6.1.1", "0", "10")), "v_transformed.xlsx"), path)
    loaded = read_sequences(path)["v"]
    assert set(loaded.events) == {Event("6.1.1", 0, 10000)}


def test_multiple_care_types_and_overlapping_windows_do_not_duplicate_event_counts(tmp_path):
    data = frame(("6.1.1", "0", "10"), ("6.1.1", "8", "20"),
                 ("6.2.1", "0", "10"), ("6.2.2", "0", "10"), ("5.3.1", "9", "11"))
    path = tmp_path / "sequences.csv"
    export_care_sequences(extract_care_patterns(data, "v.xlsx"), path)
    loaded = read_sequences(path)["v"]
    event = Event("5.3.1", 9000, 11000)
    assert loaded.events[event] == {"s001", "s002"}
    assert loaded.duplicate_rows > 0
    counts, details = compare_timing(loaded, loaded, align_situations(loaded, loaded), ["5.3.1"], 0, "v")
    assert list(counts[0]) == [1, 1, 1, 0, 0, 0, 0]
    assert len(details) == 1


@pytest.mark.parametrize("code,start,end", [("5.3.1", "bad", "10"), ("5.3.1", "10", "1"),
                                              ("6.1.1", "5", "5"), ("no code", "0", "1")])
def test_malformed_annotations_fail_with_context(code, start, end):
    with pytest.raises(ValueError, match="example.xlsx, Excel row"):
        extract_care_patterns(frame((code, start, end), ("6.1.1", "0", "20")), "example.xlsx")


def test_unselected_invalid_rows_require_audit_and_selected_errors_still_fail():
    data = frame(("6.1.1", "0", "10"), ("5.5.4", "9", "0"))
    exclusions = []
    extract_care_patterns(data, "v.xlsx", {"5.3.1"}, exclusions)
    assert exclusions[0]["Code"] == "5.5.4"
    assert exclusions[0]["Excel_Row"] == 3
    with pytest.raises(ValueError, match="Invalid interval"):
        extract_care_patterns(data, "v.xlsx", {"5.5.4"}, [])
    with pytest.raises(ValueError, match="audit is required"):
        extract_care_patterns(data, "v.xlsx", {"5.3.1"})


def test_file_pairing_subset_identifiers_and_lock_files(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    for name in ("44-P-1_K1_transformed.xlsx", "44-P-1_K2_transformed.xlsx", "unused_transformed.xlsx"):
        (old / name).touch()
    (new / "44-P-1_K1_transformed_IR.xlsx").touch()
    (new / "~$44-P-1_K1_transformed_IR.xlsx").touch()
    pairs, excluded = pair_files(old, new)
    assert [p[0] for p in pairs] == ["44-P-1_K1"]
    assert excluded == ["44-P-1_K2", "unused"]
    assert video_id("44-P-1_K1_transformed_IR.xlsx") == "44-P-1_K1"
    (new / "missing_transformed_IR.xlsx").touch()
    with pytest.raises(ValueError, match="Missing old annotations"):
        pair_files(old, new)
    (old / "44-P-1_K1.xlsx").touch()
    with pytest.raises(ValueError, match="Ambiguous video"):
        pair_files(old, new)


def test_situation_alignment_keeps_later_pairs_after_missing_middle():
    old = video(((0, 10), (20, 30), (40, 50)))
    new = video(((1, 11), (41, 51)))
    assert align_situations(old, new) == [("s001", "s001"), ("s002", None), ("s003", "s002")]


def test_situation_alignment_prefers_count_before_overlap_and_excludes_touching():
    old = video(((0, 100), (100, 110)))
    new = video(((0, 1), (1, 110)))
    assert align_situations(old, new) == [("s001", "s001"), ("s002", "s002")]
    assert align_situations(video(((0, 10),)), video(((10, 20),))) == [("s001", None), (None, "s001")]
    # If cardinality ties, use the stronger overlap rather than positional pairing.
    assert align_situations(video(((0, 5), (5, 20))), video(((4, 20),))) == [("s001", None), ("s002", "s001")]


def test_presence_per_video_and_situation_exact_ids_and_missing_side():
    old = video(((0, 10), (20, 30)), [("5.5.1", 1, 9, ["s001"]), ("5.5.10", 21, 29, ["s002"])])
    new = video(((0, 10),), [("5.5.1", 2, 8, ["s001"])])
    counts, details = presence_counts(old, new, align_situations(old, new), ["5.5.1", "5.5.10"], "v")
    assert counts["video"].tolist() == [[1, 0, 0, 0], [0, 1, 0, 0]]
    assert counts["situation"].tolist() == [[1, 0, 0, 1], [0, 1, 0, 1]]
    assert len(details) == 6


def test_presence_and_timing_statistics_hand_calculated():
    presence = presence_metrics([3, 1, 1, 5])
    assert presence["agreement"] == pytest.approx(.8)
    assert presence["positive_f1"] == pytest.approx(.75)
    assert presence["kappa"] == pytest.approx((.8 - .52) / (1 - .52))
    assert presence_metrics([10, 0, 0, 0])["kappa"] is None
    assert presence_metrics([0, 0, 0, 10])["positive_f1"] is None
    assert presence_metrics([0, 0, 0, 0])["agreement"] is None
    timing = timing_metrics([3, 2, 2, 400, 600, 100000, 200000])
    assert timing["f1"] == pytest.approx(.8)
    assert timing["mean_abs_start_error_ms"] == 200
    assert timing["sd_abs_start_error_ms"] == pytest.approx(200 / np.sqrt(2))
    assert timing["sd_abs_end_error_ms"] == pytest.approx(200 / np.sqrt(2))
    assert timing_metrics([0, 0, 0, 0, 0, 0, 0])["f1"] is None
    assert timing_metrics([2, 0, 0, 0, 0, 0, 0])["f1"] == 0
    assert timing_metrics([1, 1, 1, 50, 50, 2500, 2500])["sd_abs_start_error_ms"] is None


def test_specific_agreement_distinguishes_rare_positive_events():
    row = presence_metrics([2, 3, 5, 90])
    assert row["agreement"] == pytest.approx(.92)
    assert row["positive_specific_agreement"] == pytest.approx(1 / 3)
    assert row["positive_specific_agreement"] == row["positive_f1"]
    assert row["negative_specific_agreement"] == pytest.approx(180 / 188)
    assert presence_metrics([0, 0, 0, 10])["positive_specific_agreement"] is None
    assert presence_metrics([10, 0, 0, 0])["negative_specific_agreement"] is None
    assert presence_metrics([0, 0, 0, 0])["negative_specific_agreement_status"] == "undefined_no_negative_ratings"
    assert presence_metrics([0, 1, 0, 0])["negative_specific_agreement"] == 0


@pytest.mark.parametrize("counts,expected", [
    ([3, 1, 1, 5], 29 / 48),
    ([3, 2, 0, 5], 29 / 48),  # Same pooled category frequencies and disagreement.
    ([1, 1, 3, 5], 2 / 21),  # Krippendorff (2013), binary example, pp. 2–3.
    ([2, 0, 0, 3], 1),
    ([0, 1, 0, 0], 0),
    ([0, 2, 0, 0], -.5),
])
def test_nominal_alpha_uses_pooled_frequencies_and_finite_sample_correction(counts, expected):
    metrics = presence_metrics(counts)
    assert metrics["krippendorff_alpha"] == pytest.approx(expected)
    assert metrics["krippendorff_alpha_status"] == "defined"
    both, old_only, new_only, neither = counts
    assert presence_metrics([both, new_only, old_only, neither])["krippendorff_alpha"] == pytest.approx(expected)


@pytest.mark.parametrize("counts", [[0, 0, 0, 0], [10, 0, 0, 0], [0, 0, 0, 10]])
def test_nominal_alpha_is_undefined_without_category_variation(counts):
    metrics = presence_metrics(counts)
    assert metrics["krippendorff_alpha"] is None
    assert metrics["krippendorff_alpha_status"] == "undefined_constant_ratings_or_no_units"


def test_presence_chance_corrected_statistics_are_not_pooled_across_codes():
    rows = score_rows(np.array([[2, 0, 0, 3], [3, 1, 1, 5]]), ["1.1", "1.2"], "presence")
    assert rows[0]["krippendorff_alpha"] == 1
    assert rows[1]["krippendorff_alpha"] == pytest.approx(29 / 48)
    for metric in ("kappa", "krippendorff_alpha"):
        assert rows[-1][metric] is None
        assert rows[-1][f"{metric}_status"] == "not_pooled_across_codes"


def test_situation_presence_pools_counts_before_chance_correction():
    counts = np.array([[1, 0, 0, 1], [0, 1, 0, 0]])
    overall = score_rows(counts, ["1.1", "1.2"], "presence", pool_presence=True)[-1]
    assert overall["units"] == 3
    assert overall["agreement"] == pytest.approx(2 / 3)
    assert overall["kappa"] == pytest.approx(.4)
    assert overall["krippendorff_alpha"] == pytest.approx(4 / 9)
    assert overall["krippendorff_alpha_status"] == "defined"
    weights = np.array([[1, 1], [2, 0], [0, 2]])
    blocks = np.array([[[1, 0, 0, 1], [0, 0, 0, 0]],
                       [[0, 0, 0, 0], [0, 1, 0, 0]]])
    interval = bootstrap_intervals(blocks, ["1.1", "1.2"], "presence", weights, pool_presence=True)["__overall__"]
    assert interval["krippendorff_alpha_bootstrap_valid"] == 3
    assert interval["krippendorff_alpha_ci_low"] == pytest.approx(-.4527777777777778)
    assert interval["krippendorff_alpha_ci_high"] == pytest.approx(.9722222222222222)
    assert overall["positive_specific_agreement"] == pytest.approx(2 / 3)
    assert overall["negative_specific_agreement"] == pytest.approx(2 / 3)
    assert interval["positive_specific_agreement_bootstrap_valid"] == 3
    assert interval["positive_specific_agreement_ci_low"] == pytest.approx(1 / 30)
    assert interval["positive_specific_agreement_ci_high"] == pytest.approx(59 / 60)


@pytest.mark.parametrize("start_delta,end_delta,expected", [(500, 500, 1), (-500, -500, 1),
    (501, 0, 0), (0, 501, 0), (0, -501, 0), (0, 0, 1)])
def test_timing_requires_both_inclusive_boundaries(start_delta, end_delta, expected):
    old = video(events=[("5.3.1", 2000, 4000, ["s001"])])
    new = video(events=[("5.3.1", 2000 + start_delta, 4000 + end_delta, ["s001"])])
    counts, _ = compare_timing(old, new, [("s001", "s001")], ["5.3.1"], 500, "v")
    assert counts[0, 2] == expected


def test_timing_matches_most_occurrences_then_smallest_error():
    old = video(events=[("5.3.1", 1000, 2000, ["s001"]), ("5.3.1", 1500, 2500, ["s001"])])
    new = video(events=[("5.3.1", 500, 1500, ["s001"]), ("5.3.1", 1100, 2100, ["s001"])])
    counts, _ = compare_timing(old, new, [("s001", "s001")], ["5.3.1"], 500, "v")
    assert counts[0, 2] == 2  # A greedy nearest match for old[0] would lose one.
    new.events.pop(Event("5.3.1", 500, 1500))
    counts, details = compare_timing(old, new, [("s001", "s001")], ["5.3.1"], 500, "v")
    matched = next(row for row in details if row["status"] == "matched")
    assert counts[0, 2] == 1
    assert matched["old_start_ms"] == 1000


def test_events_cannot_match_across_codes_or_unmatched_situations():
    old = video(events=[("5.5.1", 1000, 2000, ["s001"])])
    new = video(events=[("5.5.10", 1000, 2000, ["s001"])])
    counts, _ = compare_timing(old, new, [("s001", "s001")], ["5.5.1", "5.5.10"], 500, "v")
    assert counts[:, 2].sum() == 0
    counts, details = compare_timing(old, old, [("s001", None), (None, "s001")], ["5.5.1"], 500, "v")
    assert counts[0, 2] == 0
    assert {row["reason"] for row in details} == {"unmatched_situation"}


def test_micro_macro_and_undefined_code_exclusion():
    rows = score_rows(np.array([[10, 10, 10, 0, 0, 0, 0], [1, 1, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0]]),
                      ["1.1", "1.2", "1.3"], "timing")
    assert rows[-1]["f1"] == pytest.approx(20 / 22)
    assert rows[-1]["macro_f1"] == .5
    assert rows[-1]["macro_f1_codes"] == 2


def test_bootstrap_resamples_video_counts_with_defined_replicate_counts():
    per_video = np.array([[[1, 0, 0, 0]], [[0, 1, 0, 0]]])
    weights = np.array([[2, 0], [1, 1], [0, 2]])
    result = bootstrap_intervals(per_video, ["5.3.1"], "presence", weights)
    assert result["5.3.1"]["kappa_bootstrap_valid"] == 2
    assert result["__overall__"]["kappa_bootstrap_valid"] == 0
    assert result["5.3.1"]["krippendorff_alpha_bootstrap_valid"] == 2
    assert result["5.3.1"]["krippendorff_alpha_ci_low"] == pytest.approx(-.4875)
    assert result["5.3.1"]["krippendorff_alpha_ci_high"] == pytest.approx(-.0125)
    assert result["__overall__"]["krippendorff_alpha_bootstrap_valid"] == 0
    assert result["__overall__"]["krippendorff_alpha_ci_low"] is None
    assert result["__overall__"]["krippendorff_alpha_ci_high"] is None
    assert result["5.3.1"]["agreement_ci_low"] == pytest.approx(.025)
    assert result["5.3.1"]["agreement_ci_high"] == pytest.approx(.975)


def test_legacy_scope_is_default_and_retains_its_old_gate():
    data = frame(("5.4.1 setting", "0:00:00,0", "0:00:10,0"),
                 ("6.1.1 care", "0:00:01,0", "0:00:09,0"),
                 ("6.2.1 type", "0:00:00,9", "0:00:08,0"))
    legacy = PatternDetector().detect_patterns(data, "v.xlsx")
    explicit = PatternDetector(sequence_scope="legacy").detect_patterns(data, "v.xlsx")
    assert legacy == explicit
    child = next(c for result in legacy for c in result.child_codes if c["code"] == "6.1.1 care")
    assert child["matching_6_2_codes"] == []
    corrected = PatternDetector(sequence_scope="care-overlap").detect_patterns(data, "v.xlsx")
    assert len(corrected[0].child_codes[0]["matching_6_2_codes"]) == 1


@pytest.mark.parametrize("key,value", [("presence_codes", []), ("timing_codes", ["5.5.1", "5.5.1"]),
    ("presence_codes", ["5.5.*"]), ("duration_codes", []), ("duration_codes", ["5.5.*"]),
    ("duration_codes", ["5.5.1", "5.5.1"]), ("tolerance_ms", -1), ("tolerance_ms", True), ("bootstrap_replicates", 0)])
def test_invalid_config_rejected(key, value):
    config = json.loads(DEFAULT_CONFIG.read_text())
    config[key] = value
    with pytest.raises(ValueError, match=key):
        validate_config(config)


def test_analyzer_care_overlap_mode_exports_and_propagates_errors(tmp_path):
    source, output = tmp_path / "inputs", tmp_path / "results"
    source.mkdir()
    path = source / "v.xlsx"
    frame(("6.1.1", "0", "10")).to_excel(path, index=False)
    analyzer = PatternAnalyzer(source, output, sequence_scope="care-overlap")
    analyzer.run_analysis()
    assert len(read_sequences(output / "sequence_analysis.csv")["v"].situations) == 1
    frame(("6.1.1", "bad", "10")).to_excel(path, index=False)
    with pytest.raises(ValueError, match="Invalid timestamp"):
        analyzer.analyze_file(path)


def test_end_to_end_independent_code_lists_and_repeatable_bootstrap(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    common = [("6.1.1", "0", "10"), ("5.3.1", "1", "2")]
    frame(*common, ("2.2.3.4", "2", "3")).to_excel(old / "v_transformed.xlsx", index=False)
    frame(*common).to_excel(new / "v_transformed_IR.xlsx", index=False)
    config = {**json.loads(DEFAULT_CONFIG.read_text()), "old_input_dir": str(old), "new_input_dir": str(new),
              "output_dir": str(tmp_path / "results"), "presence_codes": ["2.2.3.4"],
              "timing_codes": ["5.3.1"], "bootstrap_replicates": 20}
    result = run_check(config)
    assert result["presence_scores"][0]["positive_f1"] == 0
    assert result["presence_scores"][0]["krippendorff_alpha"] == 0
    with (tmp_path / "results/presence_scores.csv").open(newline="") as handle:
        row = next(csv.DictReader(handle))
    assert float(row["krippendorff_alpha"]) == 0
    assert row["krippendorff_alpha_status"] == "defined"
    assert int(row["krippendorff_alpha_bootstrap_valid"]) == 20
    with result["report_tables"][0].open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows[0]["Krippendorffs Alpha"] == "0.000"
    assert rows[1]["Krippendorffs Alpha"] == "nicht definiert"
    assert rows[3]["Krippendorffs Alpha"] == "0.000"
    assert result["timing_scores"][0]["f1"] == 1
    durations = {row["code"]: row for row in result["duration_scores"]}
    assert set(durations) == {"2.2.3.4", "5.3.1"}
    assert durations["2.2.3.4"]["old_duration_ms"] == 1000
    assert durations["2.2.3.4"]["new_duration_ms"] == 0
    first = (tmp_path / "results/timing_scores.csv").read_bytes()
    first_presence = (tmp_path / "results/presence_scores.csv").read_bytes()
    run_check(config)
    assert (tmp_path / "results/timing_scores.csv").read_bytes() == first
    assert (tmp_path / "results/presence_scores.csv").read_bytes() == first_presence
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    config_before = config_file.read_bytes()
    command = subprocess.run([sys.executable, "-B", str(SRC / "interrater_check.py"), "--config", str(config_file),
                              "--tolerance-ms", "0", "--output-dir", str(tmp_path / "cli")],
                             cwd=tmp_path, capture_output=True, text=True)
    assert command.returncode == 0, command.stderr
    assert "1 video pairs" in command.stdout
    assert f"Config: {config_file}" in command.stdout
    assert "Tolerance: 0 ms (command-line override)" in command.stdout
    assert config_file.read_bytes() == config_before
    assert json.loads((tmp_path / "cli/settings.json").read_text())["tolerance_ms"] == 0
    config["tolerance_ms"] = 1379
    config_file.write_text(json.dumps(config))
    config_before = config_file.read_bytes()
    command = subprocess.run([sys.executable, "-B", str(SRC / "interrater_check.py"), "--config", str(config_file)],
                             cwd=tmp_path, capture_output=True, text=True)
    assert command.returncode == 0, command.stderr
    assert "Tolerance: 1379 ms (config file)" in command.stdout
    assert config_file.read_bytes() == config_before
    assert json.loads((tmp_path / "results/settings.json").read_text())["tolerance_ms"] == 1379
    custom = {**config, "duration_codes": ["6.1.1"]}
    result = run_check(custom)
    assert [row["code"] for row in result["duration_scores"]] == ["6.1.1"]
    assert result["duration_scores"][0]["old_duration_ms"] == 10000
    assert json.loads((tmp_path / "results/settings.json").read_text())["duration_codes"] == ["6.1.1"]


def test_jointly_absent_timing_codes_write_valid_empty_match_table(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    frame(("6.1.1", "0", "10")).to_excel(old / "v_transformed.xlsx", index=False)
    frame(("6.1.1", "0", "10")).to_excel(new / "v_transformed_IR.xlsx", index=False)
    config = {**json.loads(DEFAULT_CONFIG.read_text()), "old_input_dir": str(old), "new_input_dir": str(new),
              "output_dir": str(tmp_path / "out"), "timing_codes": ["9.9.9"], "bootstrap_replicates": 5}
    result = run_check(config)
    assert result["timing_scores"][0]["f1"] is None
    with (tmp_path / "out/event_matches.csv").open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert "old_start_ms" in reader.fieldnames
        assert list(reader) == []


def test_current_ten_videos_retain_all_thirteen_situations_per_rater(tmp_path):
    config = {**json.loads(DEFAULT_CONFIG.read_text()), "output_dir": str(tmp_path), "bootstrap_replicates": 5}
    result = run_check(config)
    assert len(result["file_pairs"]) == 10
    assert sum(r["old_situations"] for r in result["file_pairs"]) == 13
    assert sum(r["new_situations"] for r in result["file_pairs"]) == 13
    assert sum(r["matched_situations"] for r in result["file_pairs"]) == 13
    new = read_sequences(tmp_path / "sequences/new/sequence_analysis.csv")["5-P-3"]
    assert new.situations["s002"] == (150800, 159000)
    with (tmp_path / "excluded_annotations.csv").open(newline="") as handle:
        excluded = list(csv.DictReader(handle))
    assert len(excluded) == 4
    assert {row["Code"] for row in excluded}.isdisjoint(config["presence_codes"] + config["timing_codes"])


def test_report_tables_export_headings_order_rounding_and_csv_quoting(tmp_path):
    report = """# Report

## Presence

| Code | Agreement | Note |
|---|---:|---|
| 5.3.1 | 0.875 | both, present |
| 5.3.2 | undefined | no events |

## Event timing

| Code | F1 |
|:---|---:|
| 5.3.1 | 0.500 |
"""
    paths = export_report_tables(report, tmp_path)
    assert [p.name for p in paths] == ["01_presence.csv", "02_event_timing.csv"]
    with paths[0].open(newline="") as handle:
        assert list(csv.reader(handle)) == [
            ["Code", "Agreement", "Note"], ["5.3.1", "0.875", "both, present"],
            ["5.3.2", "undefined", "no events"],
        ]
    with paths[1].open(newline="") as handle:
        assert list(csv.reader(handle)) == [["Code", "F1"], ["5.3.1", "0.500"]]
    before = paths[0].read_bytes()
    assert export_report_tables(report, tmp_path) == paths
    assert paths[0].read_bytes() == before


def test_report_table_export_rejects_inconsistent_column_counts(tmp_path):
    with pytest.raises(ValueError, match="inconsistent row width"):
        export_report_tables("## Example\n| A | B |\n|---|---|\n| only one |\n", tmp_path)


def test_code_duration_retains_full_intervals_but_compares_shared_time():
    old = video(((1000, 10000),), [("2.2.3.4", 0, 5000, ["s001"]),
                                 ("2.2.3.4", 4000, 12000, ["s001"])])
    new = video(((2000, 8000),), [("2.2.3.4", 3000, 9000, ["s001"])])
    counts = code_duration_counts(old, new, [("s001", "s001")], ["2.2.3.4"])
    assert counts.tolist() == [[12000, 6000, 6000, 6000, 5000, 5000, 6000]]
    metrics = code_duration_metrics(counts[0], 1)
    assert metrics["duration_difference_ms"] == -6000
    assert metrics["absolute_duration_difference_ms"] == 6000
    assert metrics["duration_change_percent"] == -50
    assert metrics["mean_abs_video_difference_ms"] == 6000
    assert metrics["duration_dice"] == pytest.approx(10 / 11)


def test_unmatched_situation_duration_is_retained_without_shared_coverage():
    old = video(events=[("6.4.3", 1000, 2000, ["s001"])])
    new = video()
    counts = code_duration_counts(old, new, [("s001", None), (None, "s001")], ["6.4.3"])
    assert counts.tolist() == [[1000, 0, 0, 0, 0, 0, 1000]]
    metrics = code_duration_metrics(counts[0], 1)
    assert metrics["duration_change_percent"] == -100
    assert metrics["duration_dice"] is None
    assert metrics["shared_duration_status"] == "no_shared_observation"


def test_duration_sum_does_not_merge_different_videos_or_cancel_absolute_errors():
    old = video(events=[("5.3.1", 1000, 2000, ["s001"])])
    new = video(events=[("5.3.1", 1000, 3000, ["s001"])])
    counts = np.array([code_duration_counts(old, new, [("s001", "s001")], ["5.3.1"]),
                       code_duration_counts(new, old, [("s001", "s001")], ["5.3.1"])])
    rows = summarize_code_durations(counts, ["5.3.1"], np.array([[1, 1], [2, 0], [0, 2]]))
    row = rows[0]
    assert row["old_duration_ms"] == row["new_duration_ms"] == 3000
    assert row["duration_difference_ms"] == row["absolute_duration_difference_ms"] == 0
    assert row["mean_abs_video_difference_ms"] == 1000
    assert row["sum_abs_video_difference_ms"] == 2000
    assert row["duration_difference_ms_ci_low"] == pytest.approx(-1900)
    assert row["duration_difference_ms_ci_high"] == pytest.approx(1900)
    assert row["mean_abs_video_difference_ms_ci_low"] == 1000


def test_duration_zero_baseline_and_joint_absence_have_explicit_status():
    counts = code_duration_counts(video(), video(), [("s001", "s001")], ["9.9"])
    metrics = code_duration_metrics(counts[0], 1)
    assert metrics["old_duration_ms"] == metrics["new_duration_ms"] == 0
    assert metrics["duration_change_percent"] is None
    assert metrics["change_status"] == "undefined_zero_old_duration"
    assert metrics["duration_dice"] is None
    assert metrics["shared_duration_status"] == "no_code_duration"
    metrics = code_duration_metrics([0, 1000, 10000, 0, 1000, 0, 1000], 1)
    assert metrics["duration_difference_ms"] == 1000
    assert metrics["duration_change_percent"] is None
    assert metrics["duration_dice"] == 0


def test_kappa_standard_test_matches_reference_and_degenerate_cases():
    from interrater_check import kappa_significance, report_pvalue
    # Hand-calculated null z² = 35/6 for these marginal counts.
    from scipy.stats import norm
    row = presence_metrics([2, 1, 0, 7])
    result = kappa_significance(row)
    assert result['kappa_z_statistic'] == pytest.approx(np.sqrt(35 / 6))
    assert result['kappa_pvalue_two_sided'] == pytest.approx(2 * norm.sf(np.sqrt(35 / 6)))
    assert kappa_significance(presence_metrics([10, 0, 0, 0]))['kappa_pvalue_two_sided'] is None
    constant = kappa_significance(presence_metrics([8, 0, 2, 0]))
    assert constant['kappa_pvalue_two_sided'] is None
    assert constant['kappa_test_status'] == 'undefined_zero_or_nonfinite_null_variance'
    assert report_pvalue(0.00001) == '<0.001'
    assert report_pvalue(None) == 'nicht definiert'


def test_duration_permutation_hand_calculated_and_degenerate_cases():
    from interrater_check import duration_difference_test
    # Four positive equal differences: only all + and all - are as extreme.
    result = duration_difference_test([1000, 1000, 1000, 1000])
    assert result['duration_pvalue_two_sided'] == .125
    assert result['duration_test_permutations'] == 16
    assert result['mean_signed_duration_difference_ms'] == 1000
    assert duration_difference_test([-1000] * 4)['duration_pvalue_two_sided'] == .125
    assert duration_difference_test([0, 0, 0])['duration_pvalue_two_sided'] == 1
    assert duration_difference_test([1000, -1000])['duration_pvalue_two_sided'] == 1
    assert duration_difference_test([1000])['duration_pvalue_two_sided'] == 1
    assert duration_difference_test([])['duration_pvalue_two_sided'] is None
    with pytest.raises(ValueError):
        duration_difference_test([float('nan')])


def test_duration_holm_adjusts_across_all_reported_codes():
    blocks = np.zeros((4, 2, 7), dtype=np.int64)
    blocks[:, 0, 1] = 1000
    rows = summarize_code_durations(blocks, ['positive', 'absent'], np.ones((1, 4), dtype=int))
    assert rows[0]['duration_pvalue_two_sided'] == .125
    assert rows[0]['duration_pvalue_holm'] == .25
    assert rows[0]['duration_significant_holm'] is False
    assert rows[1]['duration_pvalue_holm'] == 1
