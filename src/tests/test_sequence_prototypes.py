from pathlib import Path
import sys

import pandas as pd


OMA_DIR = Path(__file__).resolve().parents[1] / "oma"
sys.path.insert(0, str(OMA_DIR))

from OMAConfig import OMAConfig
from SequenceInterpreter import SequenceInterpreter


class DummyCodeNameMapper:
    def rename_state(self, state):
        return {
            "A": "Alpha",
            "B": "Beta",
            "C": "Gamma",
            "X": "X-ray",
        }.get(state, state)


def test_prototypical_sequences_returns_all_ties_with_metadata():
    sequences = {
        "s1": ["A", "B"],
        "s2": ["A", "C"],
        "s3": ["X"],
    }
    labels = pd.Series([1, 1, 2], index=["s1", "s2", "s3"], name="cluster")
    distance_matrix = pd.DataFrame(
        [
            [0.0, 1.0, 5.0],
            [1.0, 0.0, 5.0],
            [5.0, 5.0, 0.0],
        ],
        index=["s1", "s2", "s3"],
        columns=["s1", "s2", "s3"],
    )
    config = OMAConfig(input_path=Path("unused.csv"))

    prototypes = SequenceInterpreter(config).prototypical_sequences(
        sequences=sequences,
        labels=labels,
        distance_matrix=distance_matrix,
        filenames={"s1": "one.xlsx", "s2": "two.xlsx", "s3": "three.xlsx"},
        code_name_mapper=DummyCodeNameMapper(),
    )

    assert prototypes["id"].tolist() == ["s1", "s2", "s3"]
    assert prototypes["filename"].tolist() == ["one.xlsx", "two.xlsx", "three.xlsx"]
    assert prototypes["tie_size"].tolist() == [2, 2, 1]
    assert prototypes.loc[0, "sequence_codes"] == "A -> B"
    assert prototypes.loc[0, "sequence_long_names"] == "Alpha -> Beta"
    assert prototypes.loc[0, "farthest_ids"] == "s2"
    assert prototypes.loc[0, "farthest_filenames"] == "two.xlsx"
    assert prototypes.loc[0, "farthest_sequence_codes"] == "A -> C"
    assert prototypes.loc[0, "farthest_sequence_long_names"] == "Alpha -> Gamma"


def test_prototypical_sequences_reports_all_farthest_ties():
    sequences = {
        "s1": ["A"],
        "s2": ["B"],
        "s3": ["C"],
    }
    labels = pd.Series([1, 1, 1], index=["s1", "s2", "s3"], name="cluster")
    distance_matrix = pd.DataFrame(
        [
            [0.0, 2.0, 2.0],
            [2.0, 0.0, 3.0],
            [2.0, 3.0, 0.0],
        ],
        index=["s1", "s2", "s3"],
        columns=["s1", "s2", "s3"],
    )
    config = OMAConfig(input_path=Path("unused.csv"))

    prototypes = SequenceInterpreter(config).prototypical_sequences(
        sequences=sequences,
        labels=labels,
        distance_matrix=distance_matrix,
        filenames={"s1": "one.xlsx", "s2": "two.xlsx", "s3": "three.xlsx"},
        code_name_mapper=DummyCodeNameMapper(),
    )

    assert prototypes["id"].tolist() == ["s1"]
    assert prototypes.loc[0, "farthest_distance_to_prototype"] == 2.0
    assert prototypes.loc[0, "farthest_tie_size"] == 2
    assert prototypes.loc[0, "farthest_ids"] == "s2 || s3"
    assert prototypes.loc[0, "farthest_filenames"] == "two.xlsx || three.xlsx"
    assert prototypes.loc[0, "farthest_sequence_codes"] == "B || C"
    assert prototypes.loc[0, "farthest_sequence_long_names"] == "Beta || Gamma"


def test_prototypical_sequence_steps_expands_code_names():
    sequences = {"s1": ["A", "B"]}
    prototypes = pd.DataFrame(
        [
            {
                "cluster": 1,
                "id": "s1",
                "filename": "one.xlsx",
            }
        ]
    )
    config = OMAConfig(input_path=Path("unused.csv"))

    steps = SequenceInterpreter(config).prototypical_sequence_steps(
        prototypes=prototypes,
        sequences=sequences,
        code_name_mapper=DummyCodeNameMapper(),
    )

    assert steps.to_dict("records") == [
        {
            "cluster": 1,
            "id": "s1",
            "filename": "one.xlsx",
            "step": 1,
            "code": "A",
            "long_name": "Alpha",
        },
        {
            "cluster": 1,
            "id": "s1",
            "filename": "one.xlsx",
            "step": 2,
            "code": "B",
            "long_name": "Beta",
        },
    ]


def test_distances_to_prototypes_reports_each_sequence_for_each_tied_prototype():
    labels = pd.Series([1, 1, 2], index=["s1", "s2", "s3"], name="cluster")
    distance_matrix = pd.DataFrame(
        [
            [0.0, 1.0, 5.0],
            [1.0, 0.0, 5.0],
            [5.0, 5.0, 0.0],
        ],
        index=["s1", "s2", "s3"],
        columns=["s1", "s2", "s3"],
    )
    prototypes = pd.DataFrame(
        [
            {"cluster": 1, "id": "s1", "filename": "one.xlsx"},
            {"cluster": 1, "id": "s2", "filename": "two.xlsx"},
            {"cluster": 2, "id": "s3", "filename": "three.xlsx"},
        ]
    )
    config = OMAConfig(input_path=Path("unused.csv"))

    distances = SequenceInterpreter(config).distances_to_prototypes(
        labels=labels,
        distance_matrix=distance_matrix,
        prototypes=prototypes,
        filenames={"s1": "one.xlsx", "s2": "two.xlsx", "s3": "three.xlsx"},
    )

    assert distances.to_dict("records") == [
        {
            "cluster": 1,
            "id": "s1",
            "filename": "one.xlsx",
            "prototype_id": "s1",
            "prototype_filename": "one.xlsx",
            "distance_to_prototype": 0.0,
            "is_prototype": True,
        },
        {
            "cluster": 1,
            "id": "s2",
            "filename": "two.xlsx",
            "prototype_id": "s1",
            "prototype_filename": "one.xlsx",
            "distance_to_prototype": 1.0,
            "is_prototype": False,
        },
        {
            "cluster": 1,
            "id": "s2",
            "filename": "two.xlsx",
            "prototype_id": "s2",
            "prototype_filename": "two.xlsx",
            "distance_to_prototype": 0.0,
            "is_prototype": True,
        },
        {
            "cluster": 1,
            "id": "s1",
            "filename": "one.xlsx",
            "prototype_id": "s2",
            "prototype_filename": "two.xlsx",
            "distance_to_prototype": 1.0,
            "is_prototype": False,
        },
        {
            "cluster": 2,
            "id": "s3",
            "filename": "three.xlsx",
            "prototype_id": "s3",
            "prototype_filename": "three.xlsx",
            "distance_to_prototype": 0.0,
            "is_prototype": True,
        },
    ]
