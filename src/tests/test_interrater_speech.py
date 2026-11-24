"""Recipient selection and duration coverage are distinct from utterance matching."""

import csv
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest


SRC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SRC))

from interrater_check import (
    DEFAULT_CONFIG, Event, Video, align_situations, compare_timing, pflegekind_speech,
    presence_counts, run_check, speech_coverage_counts, speech_coverage_metrics,
    validate_config,
)


def make_video(windows=((0, 10000),), events=()):
    result = Video("example.xlsx", {f"s{i:03d}": w for i, w in enumerate(windows, 1)})
    for code, start, end, memberships in events:
        result.events[Event(code, start, end)] = set(memberships)
    return result


def test_exact_focus_link_extra_recipients_and_child_ten_are_distinct():
    source = make_video(events=[
        ("5.5.10", 0, 10000, ["s001"]),
        ("5.3.1", 1000, 2000, ["s001"]), ("5.5.10", 1000, 2000, ["s001"]),
        ("5.5.1", 1000, 2000, ["s001"]), ("5.5.11", 1000, 2000, ["s001"]),
        ("5.3.1", 3000, 4000, ["s001"]), ("5.5.1", 3000, 4000, ["s001"]),
        ("5.3.1", 5000, 6000, ["s001"]), ("5.5.11", 5000, 6000, ["s001"]),
        ("5.3.1", 7000, 8000, ["s001"]), ("5.5.10", 7000, 8001, ["s001"]),
        ("6.4.3", 1000, 2000, ["s001"]),
    ])
    filtered, children, audit = pflegekind_speech(source, "example", "old")
    assert children[0]["pflegekind"] == "5.5.10"
    assert [row["category"] for row in audit] == [
        "pflegekind_and_others", "other_child_without_explicit_pflegekind",
        "group_without_explicit_pflegekind", "unlinked_speech",
    ]
    assert {e for e in filtered.events if e.code == "5.3.1"} == {Event("5.3.1", 1000, 2000)}
    assert Event("6.4.3", 1000, 2000) in filtered.events
    assert Event("5.3.1", 7000, 8000) in source.events  # Filtering must not mutate the input.


@pytest.mark.parametrize("children,status", [([], "missing"), (["5.5.1", "5.5.2"], "ambiguous")])
def test_unidentified_care_child_is_audited_as_unknown_not_other_speech(children, status):
    source = make_video(events=[("5.3.1", 1000, 2000, ["s001"])] + [
        (child, 0, 10000, ["s001"]) for child in children])
    filtered, care, speech = pflegekind_speech(source, "example", "new")
    assert care[0]["status"] == status
    assert speech[0]["category"] == "unknown_pflegekind"
    assert not speech[0]["included_pflegekind_speech"]


def test_care_children_are_independent_between_raters():
    old = make_video(events=[("5.5.2", 0, 10000, ["s001"]),
                            ("5.3.1", 1000, 2000, ["s001"]), ("5.5.2", 1000, 2000, ["s001"])])
    new = make_video(events=[("5.5.1", 0, 10000, ["s001"]),
                            ("5.3.1", 1000, 2000, ["s001"]), ("5.5.1", 1000, 2000, ["s001"])])
    old, _, _ = pflegekind_speech(old, "example", "old")
    new, _, _ = pflegekind_speech(new, "example", "new")
    counts, _ = compare_timing(old, new, [("s001", "s001")], ["5.3.1"], 0, "example")
    assert counts.tolist() == [[1, 1, 1, 0, 0, 0, 0]]


def test_event_spanning_different_care_children_keeps_only_matching_membership():
    source = make_video(windows=((0, 6000), (4000, 10000)), events=[
        ("5.5.1", 0, 6000, ["s001", "s002"]), ("5.5.2", 4000, 10000, ["s001", "s002"]),
        ("5.3.1", 1000, 9000, ["s001", "s002"]), ("5.5.1", 1000, 9000, ["s001", "s002"]),
    ])
    filtered, _, _ = pflegekind_speech(source, "example", "old")
    assert filtered.events[Event("5.3.1", 1000, 9000)] == {"s001"}
    counts, _ = presence_counts(filtered, filtered, [("s001", "s001"), ("s002", "s002")], ["5.3.1"], "v")
    assert counts["situation"].tolist() == [[1, 0, 0, 1]]
    coverage = speech_coverage_counts(filtered, filtered, [("s001", "s001"), ("s002", "s002")])
    assert coverage.tolist() == [10000, 5000, 5000, 5000]
    # Both memberships qualify if both children are explicitly addressed.
    source.events[Event("5.5.2", 1000, 9000)] = {"s001", "s002"}
    filtered, _, _ = pflegekind_speech(source, "example", "old")
    assert filtered.events[Event("5.3.1", 1000, 9000)] == {"s001", "s002"}
    assert speech_coverage_counts(filtered, filtered, [("s001", "s001"), ("s002", "s002")]).tolist() == [10000, 8000, 8000, 8000]


def test_duration_unions_shared_windows_and_one_to_many_segmentation():
    old = make_video(events=[("5.3.1", 1000, 2000, ["s001"]),
                            ("5.3.1", 3000, 4000, ["s001"])])
    new = make_video(windows=((500, 9500),), events=[("5.3.1", 1000, 4000, ["s001"])])
    pairs = [("s001", "s001")]
    counts = speech_coverage_counts(old, new, pairs)
    assert counts.tolist() == [9000, 2000, 3000, 2000]
    metrics = speech_coverage_metrics(counts)
    assert metrics["duration_dice"] == .8
    assert metrics["old_covered_by_new"] == 1
    assert metrics["new_covered_by_old"] == pytest.approx(2 / 3)
    assert metrics["duration_jaccard"] == pytest.approx(2 / 3)
    timing, _ = compare_timing(old, new, pairs, ["5.3.1"], 10000, "example")
    assert timing[0, 2] == 1  # Temporal coverage must not masquerade as two matched events.
    assert speech_coverage_counts(old, new, [("s001", None), (None, "s001")]).tolist() == [0, 0, 0, 0]


def test_shared_coverage_clips_original_event_boundaries_and_merges_overlaps():
    old = make_video(events=[("5.3.1", -1000, 5000, ["s001"]),
                            ("5.3.1", 4000, 12000, ["s001"])])
    new = make_video(windows=((2000, 8000),), events=[("5.3.1", 1000, 9000, ["s001"])])
    counts = speech_coverage_counts(old, new, [("s001", "s001")])
    assert counts.tolist() == [6000, 6000, 6000, 6000]
    assert speech_coverage_metrics(counts)["duration_dice"] == 1
    assert speech_coverage_metrics([10000, 0, 0, 0])["duration_dice"] is None
    assert speech_coverage_metrics([0, 0, 0, 0])["coverage_status"] == "no_shared_observation"
    assert speech_coverage_metrics([10000, 1000, 0, 0])["duration_dice"] == 0


def make_config(tmp_path, old_rows, new_rows):
    old, new = tmp_path / "old", tmp_path / "new"
    old.mkdir()
    new.mkdir()
    for folder, name, rows in ((old, "v_transformed.xlsx", old_rows), (new, "v_transformed_IR.xlsx", new_rows)):
        pd.DataFrame(rows, columns=["Code", "Anfang", "Ende"]).to_excel(folder / name, index=False)
    return {**json.loads(DEFAULT_CONFIG.read_text()), "old_input_dir": str(old), "new_input_dir": str(new),
            "output_dir": str(tmp_path / "out"), "presence_codes": ["5.3.1"], "timing_codes": ["5.3.1"],
            "bootstrap_replicates": 10, "tolerance_ms": 500}


def test_primary_scope_filters_speech_only_and_preserves_both_comparisons(tmp_path):
    care = [("6.1.1", "0", "10"), ("5.5.1", "0", "10")]
    old = care + [("5.3.1", "1", "2"), ("5.5.2", "1", "2")]
    new = care + [("5.3.1", "1", "2"), ("5.5.1", "1", "2")]
    config = make_config(tmp_path, old, new)
    original = json.dumps(config, sort_keys=True)
    result = run_check(config)
    assert result["timing_scores"][0]["f1"] == 1
    assert json.dumps(config, sort_keys=True) == original
    variants = {row["scope"]: row for row in result["speech"]["timing"]}
    assert variants["all"]["old_events"] == 1
    assert variants["pflegekind"]["old_events"] == 0
    assert variants["pflegekind"]["new_events"] == 1
    assert variants["pflegekind"]["f1"] == 0
    config["speech_scope"] = "pflegekind"
    result = run_check(config)
    assert result["timing_scores"][0]["f1"] == 0
    assert result["duration_scores"][0]["old_duration_ms"] == 0
    assert result["duration_scores"][0]["new_duration_ms"] == 1000
    assert result["presence_scores"][0]["old_only"] == 0
    assert result["presence_scores"][0]["new_only"] == 1
    focus_presence = [row for row in result["speech"]["presence"] if row["scope"] == "pflegekind"]
    assert all(row["krippendorff_alpha"] == 0 for row in focus_presence)
    with (tmp_path / "out/speech_presence_scores.csv").open(newline="") as handle:
        focus_rows = [row for row in csv.DictReader(handle) if row["scope"] == "pflegekind"]
    assert all(float(row["krippendorff_alpha"]) == 0 for row in focus_rows)
    assert all(int(row["krippendorff_alpha_bootstrap_valid"]) == 10 for row in focus_rows)
    assert json.loads((tmp_path / "out/settings.json").read_text())["speech_scope"] == "pflegekind"
    with (tmp_path / "out/speech_recipients.csv").open(newline="") as handle:
        assert {row["category"] for row in csv.DictReader(handle)} == {
            "other_child_without_explicit_pflegekind", "pflegekind_only"}
    config["speech_scope"] = "all"
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps(config))
    before = config_file.read_bytes()
    command = subprocess.run([
        sys.executable, "-B", str(SRC / "interrater_check.py"), "--config", str(config_file),
        "--speech-scope", "pflegekind", "--output-dir", str(tmp_path / "cli"),
    ], cwd=tmp_path, capture_output=True, text=True)
    assert command.returncode == 0, command.stderr
    assert "Main speech scope: pflegekind" in command.stdout
    assert json.loads((tmp_path / "cli/settings.json").read_text())["speech_scope"] == "pflegekind"
    assert config_file.read_bytes() == before


def test_missing_focus_excludes_secondary_video_and_primary_focus_fails(tmp_path):
    rows = [("6.1.1", "0", "10"), ("5.3.1", "1", "2")]
    config = make_config(tmp_path, rows, rows)
    result = run_check(config)
    assert result["timing_scores"][0]["f1"] == 1
    focus = next(row for row in result["speech"]["timing"] if row["scope"] == "pflegekind")
    assert focus["availability"] == "no_eligible_videos"
    assert focus["videos_excluded"] == 1
    assert focus["f1"] is None
    for row in result["speech"]["presence"]:
        if row["scope"] == "pflegekind":
            assert row["krippendorff_alpha"] is None
            assert row["krippendorff_alpha_status"] == "undefined_constant_ratings_or_no_units"
            assert row["krippendorff_alpha_ci_low"] is None
            assert row["krippendorff_alpha_bootstrap_valid"] == 0
    with (tmp_path / "out/speech_timing_by_video.csv").open(newline="") as handle:
        focus = next(row for row in csv.DictReader(handle) if row["scope"] == "pflegekind")
        assert focus["availability"] == "unavailable_pflegekind"
        assert focus["old_events"] == ""
    config["speech_scope"] = "pflegekind"
    with pytest.raises(ValueError, match="Missing or ambiguous Pflegekind"):
        run_check(config)


def test_zero_speech_still_writes_recipient_and_matching_headers(tmp_path):
    rows = [("6.1.1", "0", "10"), ("5.5.1", "0", "10")]
    result = run_check(make_config(tmp_path, rows, rows))
    for row in result["speech"]["timing"]:
        assert row["videos_included"] == 1
        assert row["f1"] is None
    for name in ("speech_recipients.csv", "speech_event_matches.csv"):
        with (tmp_path / "out" / name).open(newline="") as handle:
            reader = csv.DictReader(handle)
            assert "code" in reader.fieldnames
            assert list(reader) == []


@pytest.mark.parametrize("scope", ["other", [], None, 42])
def test_invalid_speech_scope_is_rejected(scope):
    config = {**json.loads(DEFAULT_CONFIG.read_text()), "speech_scope": scope}
    with pytest.raises(ValueError, match="speech_scope"):
        validate_config(config)


def test_real_data_recipient_counts_and_durations_match_audit(tmp_path):
    config = {**json.loads(DEFAULT_CONFIG.read_text()), "output_dir": str(tmp_path), "bootstrap_replicates": 5}
    config_bytes = DEFAULT_CONFIG.read_bytes()
    result = run_check(config)
    assert DEFAULT_CONFIG.read_bytes() == config_bytes
    scopes = {row["scope"]: row for row in result["speech"]["timing"]}
    assert (scopes["all"]["old_events"], scopes["all"]["new_events"]) == (64, 28)
    assert (scopes["pflegekind"]["old_events"], scopes["pflegekind"]["new_events"]) == (50, 27)
    assert all(row["videos_included"] == 10 for row in scopes.values())
    coverage = {row["scope"]: row for row in result["speech"]["coverage"]}
    assert coverage["all"]["shared_observation_ms"] == 200900
    assert (coverage["all"]["old_speech_ms"], coverage["all"]["new_speech_ms"]) == (76300, 92100)
    assert (coverage["pflegekind"]["old_speech_ms"], coverage["pflegekind"]["new_speech_ms"]) == (65200, 84000)
    assert coverage["pflegekind"]["overlap_ms"] == 56400
    assert [p.name for p in result["report_tables"]] == [
        "01_code_presence.csv", "02_event_timing.csv", "03_speech_event_matching.csv",
        "04_shared_speech_time_coverage.csv",
        "05_code_durations.csv",
    ]
    with result["report_tables"][2].open(newline="") as handle:
        speech_table = list(csv.DictReader(handle))
    assert [r["Sprachvariante"] for r in speech_table] == ["Alle Kindansprachen", "Pflegekind-Sprache"]
    assert (speech_table[1]["Intervalle alt"], speech_table[1]["Intervalle neu"]) == ("50", "27")
    with result["report_tables"][3].open(newline="") as handle:
        duration_table = list(csv.DictReader(handle))
    assert duration_table[1]["Sprechzeit alt (s)"] == "65.200"
    assert duration_table[1]["Sprechzeit neu (s)"] == "84.000"
    assert duration_table[1]["Dauer-Dice"] == "0.756"
    durations = {row["code"]: row for row in result["duration_scores"]}
    # Different source boundaries must not disappear under shared-window clipping.
    assert durations["6.1.1"]["old_duration_ms"] != durations["6.1.1"]["new_duration_ms"]
    assert durations["6.1.1"]["old_shared_duration_ms"] == durations["6.1.1"]["new_shared_duration_ms"] == 200900
    with result["report_tables"][4].open(newline="") as handle:
        table = {row["Code"]: row for row in csv.DictReader(handle)}
    assert float(table["6.1.1"]["Dauer alt (s)"]) == pytest.approx(durations["6.1.1"]["old_duration_ms"] / 1000)
    report = (tmp_path / "report.md").read_text()
    assert report.startswith("# Interrater-Analyse\n")
    assert "nicht definiert" in report
    assert "undefined" not in report
