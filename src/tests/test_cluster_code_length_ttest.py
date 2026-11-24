from pathlib import Path
import sys

import pandas as pd


OMA_DIR = Path(__file__).resolve().parents[1] / "oma"
sys.path.insert(0, str(OMA_DIR))

from cluster_code_length_ttest import (
    aggregate_code_durations,
    attach_blocks_to_sequence_ids,
    build_analysis,
    code_matches,
    merge_intervals,
    parse_analysis_summary,
    parse_timestamp,
    save_violin_plots,
    statistical_result,
)


def test_parse_timestamp_accepts_comma_and_dot_decimals():
    assert parse_timestamp("0:01:02,5") == 62.5
    assert parse_timestamp("0:01:02.5") == 62.5


def test_parse_analysis_summary_reads_only_sequence_events(tmp_path):
    summary_path = tmp_path / "analysis_summary.txt"
    summary_path.write_text(
        """File: file.xlsx
  Parent: 5.4.1 Freispielsituation (0:00:00,0 - 0:00:10,0)
    Child: 6.1.1 Pflegesituation (0:00:01,0 - 0:00:05,0)
      ↳ Sequence (2 events):
          1. 5.3.1 FK spricht mit Kind(ern) (0:00:01,0 - 0:00:02,0)
          2. 5.3.1 FK spricht (0:00:01,5 - 0:00:03,0)
      ↔ 5.5.* Matches (1):
          5.3.1 FK spricht (0:00:04,0 - 0:00:05,0)
""",
        encoding="utf-8",
    )

    blocks = parse_analysis_summary(summary_path)

    assert len(blocks) == 1
    assert len(blocks[0].events) == 2
    assert blocks[0].events[0].code == "5.3.1"


def test_parse_analysis_summary_ignores_care_children_without_sequences(tmp_path):
    summary_path = tmp_path / "analysis_summary.txt"
    summary_path.write_text(
        """File: file.xlsx
  Parent: 5.4.1 Freispielsituation (0:00:00,0 - 0:00:10,0)
    Child: 6.1.1 Pflegesituation (0:00:01,0 - 0:00:05,0)
      ↔ No matching 6.2.* code found
      ↔ 5.5.* Matches (1):
          5.5.1 K1 (0:00:01,0 - 0:00:05,0)
""",
        encoding="utf-8",
    )

    assert parse_analysis_summary(summary_path) == []


def test_multi_sequence_filename_maps_by_care_timeframe(tmp_path):
    summary_path = tmp_path / "analysis_summary.txt"
    summary_path.write_text(
        """File: multi.xlsx
  Parent: 5.4.1 Freispielsituation (0:00:00,0 - 0:00:30,0)
    Child: 6.1.1 Pflegesituation (0:00:01,0 - 0:00:05,0)
      ↳ Sequence (1 events):
          1. 5.3.1 FK spricht (0:00:01,0 - 0:00:02,0)
    Child: 6.1.1 Pflegesituation (0:00:10,0 - 0:00:15,0)
      ↳ Sequence (1 events):
          1. 5.3.1 FK spricht (0:00:10,0 - 0:00:12,0)
""",
        encoding="utf-8",
    )
    sequence_map = pd.DataFrame(
        [
            {
                "id": "id_0",
                "Filename": "multi.xlsx",
                "care_start_s": 1.0,
                "care_end_s": 5.0,
                "cluster": 1,
            },
            {
                "id": "id_1",
                "Filename": "multi.xlsx",
                "care_start_s": 10.0,
                "care_end_s": 15.0,
                "cluster": 2,
            },
        ]
    )

    events = attach_blocks_to_sequence_ids(
        parse_analysis_summary(summary_path),
        sequence_map,
    )

    assert events[["id", "duration_s"]].to_dict(orient="records") == [
        {"id": "id_0", "duration_s": 1.0},
        {"id": "id_1", "duration_s": 2.0},
    ]


def test_merge_intervals_deduplicates_and_merges_overlaps():
    assert merge_intervals([(1.0, 2.0), (1.0, 2.0), (1.5, 3.0), (4.0, 5.0)]) == [
        (1.0, 3.0),
        (4.0, 5.0),
    ]


def test_code_matching_normalizes_pk_ak_suffixes():
    assert code_matches("5.3.1", "5.3.1 PK", "exact")
    assert code_matches("5.3.1", "5.3.1 AK", "exact")
    assert code_matches("5.3.1.2", "5.3.1 PK", "prefix")


def test_aggregate_code_durations_includes_zero_observations():
    sequence_map = pd.DataFrame(
        [
            {
                "id": "id_0",
                "Filename": "a.xlsx",
                "cluster": 1,
                "care_start_s": 0.0,
                "care_end_s": 10.0,
            },
            {
                "id": "id_1",
                "Filename": "b.xlsx",
                "cluster": 2,
                "care_start_s": 0.0,
                "care_end_s": 10.0,
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "id": "id_0",
                "code": "5.3.1",
                "event_start_s": 1.0,
                "event_end_s": 2.0,
            }
        ]
    )

    observations = aggregate_code_durations(
        events,
        sequence_map,
        target_code="5.3.1",
        clusters=(1, 2),
        match_mode="exact",
    )

    assert observations[["id", "duration_s"]].to_dict(orient="records") == [
        {"id": "id_0", "duration_s": 1.0},
        {"id": "id_1", "duration_s": 0.0},
    ]


def test_aggregate_code_durations_accepts_target_with_suffix():
    sequence_map = pd.DataFrame(
        [
            {
                "id": "id_0",
                "Filename": "a.xlsx",
                "cluster": 1,
                "care_start_s": 0.0,
                "care_end_s": 10.0,
            },
            {
                "id": "id_1",
                "Filename": "b.xlsx",
                "cluster": 2,
                "care_start_s": 0.0,
                "care_end_s": 10.0,
            },
        ]
    )
    events = pd.DataFrame(
        [
            {
                "id": "id_0",
                "code": "5.3.1",
                "event_start_s": 1.0,
                "event_end_s": 2.0,
            }
        ]
    )

    observations = aggregate_code_durations(
        events,
        sequence_map,
        target_code="5.3.1 PK",
        clusters=(1, 2),
        match_mode="exact",
    )

    assert observations["duration_s"].tolist() == [1.0, 0.0]
    assert observations["matched_code"].tolist() == ["5.3.1", "5.3.1"]


def test_save_violin_plots_creates_requested_files(tmp_path):
    observations = pd.DataFrame(
        [
            {
                "id": "id_0",
                "Filename": "a.xlsx",
                "cluster": 1,
                "care_start_s": 0.0,
                "care_end_s": 10.0,
                "target_code": "5.3.1 PK",
                "matched_code": "5.3.1",
                "duration_s": 1.0,
                "has_code": True,
            },
            {
                "id": "id_1",
                "Filename": "b.xlsx",
                "cluster": 2,
                "care_start_s": 0.0,
                "care_end_s": 10.0,
                "target_code": "5.3.1 PK",
                "matched_code": "5.3.1",
                "duration_s": 2.0,
                "has_code": True,
            },
        ]
    )

    paths = save_violin_plots(observations, tmp_path, formats=["png"])

    assert len(paths) == 1
    assert paths[0].exists()
    assert paths[0].suffix == ".png"


def test_statistical_result_reports_directional_ttest():
    observations = pd.DataFrame(
        [
            {"target_code": "5.3.1", "cluster": 1, "duration_s": 5.0},
            {"target_code": "5.3.1", "cluster": 1, "duration_s": 6.0},
            {"target_code": "5.3.1", "cluster": 1, "duration_s": 7.0},
            {"target_code": "5.3.1", "cluster": 2, "duration_s": 1.0},
            {"target_code": "5.3.1", "cluster": 2, "duration_s": 2.0},
            {"target_code": "5.3.1", "cluster": 2, "duration_s": 3.0},
        ]
    )

    result = statistical_result(observations, clusters=(1, 2))

    assert result["mean_difference_a_minus_b"] == 4.0
    assert result["direction"] == "cluster_1_greater"
    assert result["directional_alternative"] == "greater"
    assert result["welch_directional_p"] < result["welch_p"]


def test_build_analysis_writes_expected_code_results(tmp_path):
    summary_path = tmp_path / "analysis_summary.txt"
    extracted_path = tmp_path / "extracted_sequences.csv"
    labels_path = tmp_path / "cluster_labels.csv"

    summary_path.write_text(
        """File: a.xlsx
  Parent: 5.4.1 Freispielsituation (0:00:00,0 - 0:00:10,0)
    Child: 6.1.1 Pflegesituation (0:00:01,0 - 0:00:05,0)
      ↳ Sequence (1 events):
          1. 5.3.1 FK spricht (0:00:01,0 - 0:00:02,0)
File: b.xlsx
  Parent: 5.4.1 Freispielsituation (0:00:00,0 - 0:00:10,0)
    Child: 6.1.1 Pflegesituation (0:00:01,0 - 0:00:05,0)
      ↳ Sequence (1 events):
          1. 5.3.1 FK spricht (0:00:01,0 - 0:00:04,0)
""",
        encoding="utf-8",
    )
    pd.DataFrame(
        [
            {
                "Filename": "a.xlsx",
                "Sequence_Code": "6.1.1 PK",
                "Sequence_Start": "0:00:01,0",
                "Sequence_End": "0:00:05,0",
                "id": "a_0",
            },
            {
                "Filename": "b.xlsx",
                "Sequence_Code": "6.1.1 PK",
                "Sequence_Start": "0:00:01,0",
                "Sequence_End": "0:00:05,0",
                "id": "b_0",
            },
        ]
    ).to_csv(extracted_path, index=False)
    pd.DataFrame({"cluster": [1, 2]}, index=["a_0", "b_0"]).to_csv(labels_path)

    observations, results = build_analysis(
        summary_path,
        extracted_path,
        labels_path,
        codes=["5.3.1"],
        clusters=(1, 2),
        match_mode="exact",
        tolerance_s=0.3,
    )

    assert observations["duration_s"].tolist() == [1.0, 3.0]
    assert results.iloc[0]["target_code"] == "5.3.1"
