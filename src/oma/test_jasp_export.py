from pathlib import Path

import pandas as pd

from export_jasp_oma_dataset import export_excel_datasets, export_jasp_datasets


def _write_fixture(oma_output: Path) -> None:
    oma_output.mkdir(parents=True, exist_ok=True)
    ids = ["s1", "s2", "s3", "s4"]
    pd.DataFrame(
        [
            [0.0, 1.0, 4.0, 5.0],
            [1.0, 0.0, 3.0, 6.0],
            [4.0, 3.0, 0.0, 2.0],
            [5.0, 6.0, 2.0, 0.0],
        ],
        index=ids,
        columns=ids,
    ).to_csv(oma_output / "oma_distance_matrix.csv")
    pd.DataFrame(
        {"cluster": [1, 1, 2, 2]},
        index=ids,
    ).to_csv(oma_output / "cluster_labels.csv")
    pd.DataFrame(
        [
            {
                "id": "s1",
                "filename": "a.xlsx",
                "care_type": "nase_putzen",
                "care_type_status": "clean",
                "matched_care_codes": "6.2.1",
                "matched_care_labels": "nase_putzen",
                "n_matched_care_types": 1,
            },
            {
                "id": "s2",
                "filename": "b.xlsx",
                "care_type": "nase_putzen",
                "care_type_status": "clean",
                "matched_care_codes": "6.2.1",
                "matched_care_labels": "nase_putzen",
                "n_matched_care_types": 1,
            },
            {
                "id": "s3",
                "filename": "c.xlsx",
                "care_type": "gesicht_abwischen",
                "care_type_status": "clean",
                "matched_care_codes": "6.2.2",
                "matched_care_labels": "gesicht_abwischen",
                "n_matched_care_types": 1,
            },
            {
                "id": "s4",
                "filename": "d.xlsx",
                "care_type": "mixed",
                "care_type_status": "mixed",
                "matched_care_codes": "6.2.1 | 6.2.2",
                "matched_care_labels": "nase_putzen | gesicht_abwischen",
                "n_matched_care_types": 2,
            },
        ]
    ).to_csv(oma_output / "care_type_by_sequence.csv", index=False)
    pd.DataFrame(
        [
            {
                "comparison": "care_type_permanova",
                "n_total": 3,
                "n_mixed_excluded": 1,
                "pseudo_f_score": 2.5,
                "r_squared": 0.2,
                "p_value": 0.12,
                "permutations": 999,
            }
        ]
    ).to_csv(oma_output / "care_type_distance_permanova.csv", index=False)
    pd.DataFrame(
        [
            {
                "test": "fisher_exact",
                "n_total": 3,
                "p_value": 1.0,
                "odds_ratio": 0.5,
                "cramers_v": 0.1,
                "chi_square": 0.25,
                "degrees_of_freedom": 1,
            }
        ]
    ).to_csv(oma_output / "care_type_cluster_association.csv", index=False)
    pd.DataFrame(
        [
            {
                "recommendation": "keep_pooled_oma_as_primary_analysis",
                "separate_oma_recommended": False,
            }
        ]
    ).to_csv(oma_output / "care_type_recommendation.csv", index=False)
    pd.DataFrame(
        [
            {
                "cluster": 1,
                "code": "A",
                "long_name": "Alpha",
                "occurrence_count": 3,
                "occurrence_relative_within_cluster": 0.6,
                "occurrence_percent_within_cluster": 60.0,
                "sequence_count_with_code": 2,
                "sequence_relative_with_code": 1.0,
                "sequence_percent_with_code": 100.0,
                "n_sequences_in_cluster": 2,
                "total_code_occurrences_in_cluster": 5,
            }
        ]
    ).to_csv(oma_output / "cluster_code_frequencies.csv", index=False)
    pd.DataFrame(
        [
            {
                "cluster": 1,
                "code": "A PK",
                "long_name": "Alpha",
                "raw_observation_count": 4,
                "raw_observation_relative_within_cluster": 0.8,
                "raw_observation_percent_within_cluster": 80.0,
                "sequence_count_with_code": 2,
                "sequence_relative_with_code": 1.0,
                "sequence_percent_with_code": 100.0,
                "n_sequences_in_cluster": 2,
                "total_raw_code_observations_in_cluster": 5,
            }
        ]
    ).to_csv(oma_output / "raw_cluster_code_frequencies.csv", index=False)


def test_export_jasp_datasets_writes_expected_files(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    written_paths = export_jasp_datasets(oma_output, out, n_mds_components=2)

    assert {path.name for path in written_paths} == {
        "jasp_sequence_level.csv",
        "jasp_distance_features.csv",
        "jasp_distance_feature_columns.csv",
        "jasp_pairwise_distances.csv",
        "jasp_care_cluster_counts.csv",
        "jasp_cluster_code_frequencies.csv",
        "jasp_raw_cluster_code_frequencies.csv",
        "jasp_analysis_summary.csv",
    }
    assert all(path.exists() for path in written_paths)


def test_sequence_level_marks_mixed_cases_and_adds_distance_summaries(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    export_jasp_datasets(oma_output, out, n_mds_components=2)
    sequence_level = pd.read_csv(out / "jasp_sequence_level.csv")
    mixed = sequence_level[sequence_level["id"] == "s4"].iloc[0]
    s1 = sequence_level[sequence_level["id"] == "s1"].iloc[0]

    assert mixed["care_type_status"] == "mixed"
    assert not bool(mixed["is_clean_care_type"])
    assert s1["mean_distance_same_care_type_clean"] == 1.0
    assert s1["mean_distance_other_care_type_clean"] == 4.0
    assert {"mds_1", "mds_2"}.issubset(sequence_level.columns)


def test_distance_features_preserve_original_distances(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    export_jasp_datasets(oma_output, out, n_mds_components=0)
    features = pd.read_csv(out / "jasp_distance_features.csv")
    feature_columns = pd.read_csv(out / "jasp_distance_feature_columns.csv")
    feature_lookup = dict(
        zip(feature_columns["sequence_id"], feature_columns["distance_feature"])
    )
    s1 = features[features["id"] == "s1"].iloc[0]

    assert s1[feature_lookup["s1"]] == 0.0
    assert s1[feature_lookup["s3"]] == 4.0


def test_pairwise_and_count_outputs_support_jasp_contingency_checks(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    export_jasp_datasets(oma_output, out, n_mds_components=0)
    pairwise = pd.read_csv(out / "jasp_pairwise_distances.csv")
    counts = pd.read_csv(out / "jasp_care_cluster_counts.csv")

    assert len(pairwise) == 6
    assert set(pairwise["same_cluster"]) == {"yes", "no"}
    assert counts.to_dict("records") == [
        {
            "care_type": "gesicht_abwischen",
            "cluster": 1,
            "count": 0,
            "care_type_status": "clean",
        },
        {
            "care_type": "gesicht_abwischen",
            "cluster": 2,
            "count": 1,
            "care_type_status": "clean",
        },
        {
            "care_type": "nase_putzen",
            "cluster": 1,
            "count": 2,
            "care_type_status": "clean",
        },
        {
            "care_type": "nase_putzen",
            "cluster": 2,
            "count": 0,
            "care_type_status": "clean",
        },
    ]


def test_analysis_summary_carries_existing_test_values(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    export_jasp_datasets(oma_output, out, n_mds_components=0)
    summary = pd.read_csv(out / "jasp_analysis_summary.csv").iloc[0]

    assert summary["distance_test"] == "care_type_permanova"
    assert summary["distance_pseudo_f"] == 2.5
    assert summary["distance_r_squared"] == 0.2
    assert summary["cluster_association_test"] == "fisher_exact"
    assert summary["cluster_association_cramers_v"] == 0.1
    assert summary["recommendation"] == "keep_pooled_oma_as_primary_analysis"


def test_export_copies_cluster_code_frequencies_for_jasp(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    export_jasp_datasets(oma_output, out, n_mds_components=0)
    frequencies = pd.read_csv(out / "jasp_cluster_code_frequencies.csv")

    assert frequencies.to_dict("records") == [
        {
            "cluster": 1,
            "code": "A",
            "long_name": "Alpha",
            "occurrence_count": 3,
            "occurrence_relative_within_cluster": 0.6,
            "occurrence_percent_within_cluster": 60.0,
            "sequence_count_with_code": 2,
            "sequence_relative_with_code": 1.0,
            "sequence_percent_with_code": 100.0,
            "n_sequences_in_cluster": 2,
            "total_code_occurrences_in_cluster": 5,
        }
    ]


def test_export_copies_raw_cluster_code_frequencies_for_jasp(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)

    export_jasp_datasets(oma_output, out, n_mds_components=0)
    frequencies = pd.read_csv(out / "jasp_raw_cluster_code_frequencies.csv")

    assert frequencies.to_dict("records") == [
        {
            "cluster": 1,
            "code": "A PK",
            "long_name": "Alpha",
            "raw_observation_count": 4,
            "raw_observation_relative_within_cluster": 0.8,
            "raw_observation_percent_within_cluster": 80.0,
            "sequence_count_with_code": 2,
            "sequence_relative_with_code": 1.0,
            "sequence_percent_with_code": 100.0,
            "n_sequences_in_cluster": 2,
            "total_raw_code_observations_in_cluster": 5,
        }
    ]


def test_excel_export_uses_german_excel_friendly_number_format(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "excel"
    _write_fixture(oma_output)

    written_paths = export_excel_datasets(oma_output, out, n_mds_components=0)

    assert "excel_raw_cluster_code_frequencies.csv" in {
        path.name for path in written_paths
    }
    raw_text = (out / "excel_raw_cluster_code_frequencies.csv").read_text(
        encoding="utf-8-sig"
    )

    assert "raw_observation_relative_within_cluster;" in raw_text
    assert "0,800000;80,000000;" in raw_text

    frequencies = pd.read_csv(
        out / "excel_raw_cluster_code_frequencies.csv",
        sep=";",
        decimal=",",
    )
    assert frequencies.iloc[0]["raw_observation_percent_within_cluster"] == 80.0


def test_missing_metadata_id_fails_with_clear_error(tmp_path):
    oma_output = tmp_path / "oma_output"
    out = tmp_path / "jasp"
    _write_fixture(oma_output)
    care_types = pd.read_csv(oma_output / "care_type_by_sequence.csv")
    care_types = care_types[care_types["id"] != "s4"]
    care_types.to_csv(oma_output / "care_type_by_sequence.csv", index=False)

    try:
        export_jasp_datasets(oma_output, out, n_mds_components=0)
    except ValueError as exc:
        assert "Missing care type rows" in str(exc)
    else:
        raise AssertionError("Expected missing care type metadata to fail.")
