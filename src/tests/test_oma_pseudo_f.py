from pathlib import Path
import sys

import numpy as np
import pandas as pd


OMA_DIR = Path(__file__).resolve().parents[1] / "oma"
sys.path.insert(0, str(OMA_DIR))

from OMAConfig import OMAConfig
from SequenceClusterer import SequenceClusterer


def _distance_matrix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [0.0, 1.0, 5.0, 5.0],
            [1.0, 0.0, 5.0, 5.0],
            [5.0, 5.0, 0.0, 1.0],
            [5.0, 5.0, 1.0, 0.0],
        ],
        index=["a", "b", "c", "d"],
        columns=["a", "b", "c", "d"],
    )


def _three_cluster_distance_matrix() -> pd.DataFrame:
    return pd.DataFrame(
        [
            [0.0, 1.0, 5.0, 5.0, 4.0, 4.0],
            [1.0, 0.0, 5.0, 5.0, 4.0, 4.0],
            [5.0, 5.0, 0.0, 1.0, 3.0, 3.0],
            [5.0, 5.0, 1.0, 0.0, 3.0, 3.0],
            [4.0, 4.0, 3.0, 3.0, 0.0, 1.0],
            [4.0, 4.0, 3.0, 3.0, 1.0, 0.0],
        ],
        index=["a", "b", "c", "d", "e", "f"],
        columns=["a", "b", "c", "d", "e", "f"],
    )


def _clusterer(**overrides) -> SequenceClusterer:
    config = OMAConfig(
        input_path=Path("unused.csv"),
        min_clusters=2,
        max_clusters=3,
        pseudo_f_permutations=10,
        **overrides,
    )
    return SequenceClusterer(config)


def test_pseudo_f_statistic_uses_distance_matrix_discrepancy_formula():
    labels = pd.Series([1, 1, 2, 2], index=["a", "b", "c", "d"])

    stats = _clusterer().pseudo_f_statistic(_distance_matrix(), labels)

    assert stats["sst"] == 25.5
    assert stats["ssw"] == 1.0
    assert stats["ssb"] == 24.5
    assert stats["pseudo_f_score"] == 49.0


def test_pseudo_f_permutation_p_value_is_deterministic():
    labels = pd.Series([1, 1, 2, 2], index=["a", "b", "c", "d"])
    clusterer = _clusterer(random_state=7)

    first = clusterer.pseudo_f_permutation_p_value(
        _distance_matrix(),
        labels,
        n_permutations=20,
    )
    second = clusterer.pseudo_f_permutation_p_value(
        _distance_matrix(),
        labels,
        n_permutations=20,
    )

    assert first == second
    assert 0.0 <= first <= 1.0


def test_choose_number_of_clusters_reports_pseudo_f_and_sorts_by_it():
    scores = _clusterer(random_state=3).choose_number_of_clusters(
        _distance_matrix()
    )

    expected_columns = {
        "n_clusters",
        "silhouette_score",
        "pseudo_f_score",
        "pseudo_f_p_value",
        "pseudo_f_permutations",
        "sst",
        "ssw",
        "ssb",
    }

    assert expected_columns.issubset(scores.columns)
    assert scores["pseudo_f_score"].is_monotonic_decreasing
    assert np.all(
        (scores["pseudo_f_p_value"] >= 0.0)
        & (scores["pseudo_f_p_value"] <= 1.0)
    )


def test_pairwise_permanova_reports_expected_two_cluster_pseudo_f():
    labels = pd.Series([1, 1, 2, 2], index=["a", "b", "c", "d"])

    result = _clusterer().pairwise_permanova(
        _distance_matrix(),
        labels,
        n_permutations=0,
    )
    row = result.iloc[0]

    assert len(result) == 1
    assert row["cluster_a"] == 1
    assert row["cluster_b"] == 2
    assert row["n_a"] == 2
    assert row["n_b"] == 2
    assert row["pseudo_f_score"] == 49.0
    assert row["sst"] == 25.5
    assert row["ssw"] == 1.0
    assert row["ssb"] == 24.5
    assert pd.isna(row["p_value"])
    assert not row["significant"]


def test_pairwise_permanova_applies_bonferroni_correction():
    labels = pd.Series([1, 1, 2, 2, 3, 3], index=["a", "b", "c", "d", "e", "f"])

    result = _clusterer(random_state=11).pairwise_permanova(
        _three_cluster_distance_matrix(),
        labels,
        n_permutations=10,
    )
    expected_adjusted = np.minimum(result["p_value"].to_numpy() * 3, 1.0)

    assert len(result) == 3
    assert result["p_adjust_method"].eq("bonferroni").all()
    assert result["permutations"].eq(10).all()
    np.testing.assert_allclose(
        result["p_value_adjusted"].to_numpy(),
        expected_adjusted,
    )
    assert result["significant"].dtype == bool


def test_pairwise_permanova_permutation_p_values_are_deterministic():
    labels = pd.Series([1, 1, 2, 2, 3, 3], index=["a", "b", "c", "d", "e", "f"])
    clusterer = _clusterer(random_state=13)

    first = clusterer.pairwise_permanova(
        _three_cluster_distance_matrix(),
        labels,
        n_permutations=20,
    )
    second = clusterer.pairwise_permanova(
        _three_cluster_distance_matrix(),
        labels,
        n_permutations=20,
    )

    pd.testing.assert_frame_equal(first, second)
