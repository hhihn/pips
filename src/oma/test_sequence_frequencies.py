from pathlib import Path

import pandas as pd

from OMAConfig import OMAConfig
from SequenceInterpreter import SequenceInterpreter


class DummyCodeNameMapper:
    def rename_state(self, state):
        state = state.removesuffix(" PK").removesuffix(" AK")
        return {
            "A": "Alpha",
            "B": "Beta",
            "C": "Gamma",
        }.get(state, state)


def test_cluster_code_frequencies_counts_occurrences_and_sequences():
    sequences = {
        "s1": ["A", "A", "B"],
        "s2": ["A", "C"],
        "s3": ["B", "B", "C"],
    }
    labels = pd.Series([1, 1, 2], index=["s1", "s2", "s3"], name="cluster")
    config = OMAConfig(input_path=Path("unused.csv"))

    frequencies = SequenceInterpreter(config).cluster_code_frequencies(
        sequences,
        labels,
        code_name_mapper=DummyCodeNameMapper(),
    )
    cluster_1_a = frequencies[
        (frequencies["cluster"] == 1) & (frequencies["code"] == "A")
    ].iloc[0]
    cluster_1_b = frequencies[
        (frequencies["cluster"] == 1) & (frequencies["code"] == "B")
    ].iloc[0]

    assert cluster_1_a["long_name"] == "Alpha"
    assert cluster_1_a["occurrence_count"] == 3
    assert cluster_1_a["total_code_occurrences_in_cluster"] == 5
    assert cluster_1_a["occurrence_relative_within_cluster"] == 0.6
    assert cluster_1_a["occurrence_percent_within_cluster"] == 60.0
    assert cluster_1_a["sequence_count_with_code"] == 2
    assert cluster_1_a["n_sequences_in_cluster"] == 2
    assert cluster_1_a["sequence_relative_with_code"] == 1.0
    assert cluster_1_a["sequence_percent_with_code"] == 100.0

    assert cluster_1_b["occurrence_count"] == 1
    assert cluster_1_b["sequence_count_with_code"] == 1
    assert cluster_1_b["sequence_relative_with_code"] == 0.5
    assert cluster_1_b["sequence_percent_with_code"] == 50.0


def test_cluster_code_frequencies_splits_compound_states_into_codes():
    sequences = {
        "s1": ["A|B", "A"],
        "s2": ["B|C"],
    }
    labels = pd.Series([1, 1], index=["s1", "s2"], name="cluster")
    config = OMAConfig(input_path=Path("unused.csv"))

    frequencies = SequenceInterpreter(config).cluster_code_frequencies(
        sequences,
        labels,
        code_name_mapper=DummyCodeNameMapper(),
    )
    by_code = frequencies.set_index("code")

    assert by_code.loc["A", "occurrence_count"] == 2
    assert by_code.loc["A", "sequence_count_with_code"] == 1
    assert by_code.loc["B", "occurrence_count"] == 2
    assert by_code.loc["B", "sequence_count_with_code"] == 2
    assert by_code.loc["C", "occurrence_count"] == 1
    assert by_code.loc["C", "sequence_count_with_code"] == 1
    assert by_code.loc["B", "total_code_occurrences_in_cluster"] == 5


def test_raw_cluster_code_frequencies_count_annotation_rows():
    df = pd.DataFrame(
        [
            {"id": "s1", "Sequence_Code": "A PK"},
            {"id": "s1", "Sequence_Code": "A PK"},
            {"id": "s1", "Sequence_Code": "B PK"},
            {"id": "s2", "Sequence_Code": "A PK"},
            {"id": "s2", "Sequence_Code": "C PK"},
            {"id": "s3", "Sequence_Code": "B PK"},
        ]
    )
    labels = pd.Series([1, 1, 2], index=["s1", "s2", "s3"], name="cluster")
    config = OMAConfig(input_path=Path("unused.csv"))

    frequencies = SequenceInterpreter(config).raw_cluster_code_frequencies(
        df,
        labels,
        code_name_mapper=DummyCodeNameMapper(),
    )
    cluster_1_a = frequencies[
        (frequencies["cluster"] == 1) & (frequencies["code"] == "A PK")
    ].iloc[0]
    cluster_1_b = frequencies[
        (frequencies["cluster"] == 1) & (frequencies["code"] == "B PK")
    ].iloc[0]

    assert cluster_1_a["long_name"] == "Alpha"
    assert cluster_1_a["raw_observation_count"] == 3
    assert cluster_1_a["total_raw_code_observations_in_cluster"] == 5
    assert cluster_1_a["raw_observation_relative_within_cluster"] == 0.6
    assert cluster_1_a["raw_observation_percent_within_cluster"] == 60.0
    assert cluster_1_a["sequence_count_with_code"] == 2
    assert cluster_1_a["n_sequences_in_cluster"] == 2
    assert cluster_1_a["sequence_percent_with_code"] == 100.0

    assert cluster_1_b["raw_observation_count"] == 1
    assert cluster_1_b["sequence_count_with_code"] == 1
    assert cluster_1_b["sequence_percent_with_code"] == 50.0


def test_raw_cluster_code_frequencies_fail_for_unmapped_ids():
    df = pd.DataFrame([{"id": "s1", "Sequence_Code": "A PK"}])
    labels = pd.Series([1], index=["other"], name="cluster")
    config = OMAConfig(input_path=Path("unused.csv"))

    try:
        SequenceInterpreter(config).raw_cluster_code_frequencies(
            df,
            labels,
            code_name_mapper=DummyCodeNameMapper(),
        )
    except ValueError as exc:
        assert "Missing cluster labels" in str(exc)
    else:
        raise AssertionError("Expected raw ids without cluster labels to fail.")
