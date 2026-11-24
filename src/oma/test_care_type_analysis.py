from pathlib import Path

import numpy as np
import pandas as pd

from CareTypeAnalyzer import CareTypeAnalyzer
from OMAConfig import OMAConfig
from SequenceClusterer import SequenceClusterer


def _config(**overrides):
    return OMAConfig(
        input_path=Path("unused.csv"),
        care_type_codes={
            "6.2.1": "nase_putzen",
            "6.2.2": "gesicht_abwischen",
        },
        care_type_permutations=0,
        pseudo_f_permutations=0,
        **overrides,
    )


def _distance_matrix():
    return pd.DataFrame(
        [
            [0.0, 1.0, 5.0, 5.0],
            [1.0, 0.0, 5.0, 5.0],
            [5.0, 5.0, 0.0, 1.0],
            [5.0, 5.0, 1.0, 0.0],
        ],
        index=["s1", "s2", "s3", "s4"],
        columns=["s1", "s2", "s3", "s4"],
    )


def test_sequence_care_types_maps_exact_normalized_marker_codes():
    df = pd.DataFrame(
        [
            {"id": "s1", "Filename": "a.xlsx", "Sequence_Code": "6.2.1 PK"},
            {"id": "s1", "Filename": "a.xlsx", "Sequence_Code": "6.2.10 PK"},
            {"id": "s2", "Filename": "b.xlsx", "Sequence_Code": "6.2.2 PK"},
            {"id": "s3", "Filename": "c.xlsx", "Sequence_Code": "6.2.1 PK"},
            {"id": "s3", "Filename": "c.xlsx", "Sequence_Code": "6.2.2 PK"},
        ]
    )

    care_types = CareTypeAnalyzer(_config()).sequence_care_types(df)

    assert care_types[["id", "care_type", "care_type_status"]].to_dict(
        "records"
    ) == [
        {"id": "s1", "care_type": "nase_putzen", "care_type_status": "clean"},
        {
            "id": "s2",
            "care_type": "gesicht_abwischen",
            "care_type_status": "clean",
        },
        {"id": "s3", "care_type": "mixed", "care_type_status": "mixed"},
    ]
    assert care_types.loc[0, "matched_care_codes"] == "6.2.1"


def test_sequence_care_types_fails_when_marker_is_missing():
    df = pd.DataFrame(
        [
            {"id": "s1", "Filename": "a.xlsx", "Sequence_Code": "6.2.10 PK"},
        ]
    )

    try:
        CareTypeAnalyzer(_config()).sequence_care_types(df)
    except ValueError as exc:
        assert "Care type markers are missing" in str(exc)
    else:
        raise AssertionError("Expected missing care marker to fail QC.")


def test_distance_group_comparison_reuses_pseudo_f_formula():
    care_types = pd.DataFrame(
        [
            {"id": "s1", "care_type": "nase_putzen", "care_type_status": "clean"},
            {"id": "s2", "care_type": "nase_putzen", "care_type_status": "clean"},
            {
                "id": "s3",
                "care_type": "gesicht_abwischen",
                "care_type_status": "clean",
            },
            {
                "id": "s4",
                "care_type": "gesicht_abwischen",
                "care_type_status": "clean",
            },
        ]
    )
    config = _config()
    result = CareTypeAnalyzer(config).distance_group_comparison(
        _distance_matrix(),
        care_types,
        SequenceClusterer(config),
    )
    row = result.iloc[0]

    assert row["pseudo_f_score"] == 49.0
    assert row["sst"] == 25.5
    assert row["ssw"] == 1.0
    assert row["ssb"] == 24.5
    np.testing.assert_allclose(row["r_squared"], 24.5 / 25.5)
    assert pd.isna(row["p_value"])


def test_cluster_association_uses_fisher_for_small_two_by_two_table():
    care_types = pd.DataFrame(
        [
            {"id": "s1", "care_type": "nase_putzen", "care_type_status": "clean"},
            {"id": "s2", "care_type": "nase_putzen", "care_type_status": "clean"},
            {
                "id": "s3",
                "care_type": "gesicht_abwischen",
                "care_type_status": "clean",
            },
            {"id": "s4", "care_type": "mixed", "care_type_status": "mixed"},
        ]
    )
    labels = pd.Series([1, 2, 1, 2], index=["s1", "s2", "s3", "s4"])

    result = CareTypeAnalyzer(_config()).cluster_association(care_types, labels)
    row = result.iloc[0]

    assert row["test"] == "fisher_exact"
    assert row["n_total"] == 3
    assert row["n_mixed_excluded"] == 1
    assert 0.0 <= row["p_value"] <= 1.0
