from pathlib import Path
import sys

import pandas as pd
import pytest


OMA_DIR = Path(__file__).resolve().parents[1] / "oma"
sys.path.insert(0, str(OMA_DIR))

from CostScheme import CostScheme
from OMAConfig import OMAConfig
from OMAPipeline import OMAPipeline
from OptimalMatcher import OptimalMatcher


def test_custom_substitution_costs_are_symmetric():
    costs = {
        ("A", "B"): 0.5,
    }

    scheme = CostScheme(
        alphabet=["A", "B"],
        custom_substitution_costs=costs,
    )

    assert scheme.substitution_cost("A", "B") == 0.5
    assert scheme.substitution_cost("B", "A") == 0.5


def test_conflicting_symmetric_substitution_costs_raise():
    with pytest.raises(ValueError, match="Conflicting symmetric"):
        CostScheme(
            alphabet=["A", "B"],
            custom_substitution_costs={
                ("A", "B"): 0.5,
                ("B", "A"): 1.5,
            },
        )


def test_state_specific_indel_cost_changes_deletion_cost():
    scheme = CostScheme(
        alphabet=["A", "B"],
        indel_cost=1.0,
        custom_indel_costs={"A": 3.0},
    )
    matcher = OptimalMatcher(scheme)

    assert matcher.distance(["A"], []) == 3.0
    assert matcher.distance(["B"], []) == 1.0


def test_high_substitution_cost_can_be_bypassed_by_low_indels():
    scheme = CostScheme(
        alphabet=["A", "B"],
        indel_cost=1.0,
        custom_substitution_costs={("A", "B"): 5.0},
    )
    matcher = OptimalMatcher(scheme)

    assert matcher.distance(["A"], ["B"]) == 2.0


def test_high_substitution_and_indel_costs_make_important_state_costly():
    scheme = CostScheme(
        alphabet=["A", "B"],
        indel_cost=1.0,
        custom_substitution_costs={("A", "B"): 5.0},
        custom_indel_costs={"A": 4.0, "B": 4.0},
    )
    matcher = OptimalMatcher(scheme)

    assert matcher.distance(["A"], ["B"]) == 5.0


def test_compound_state_costs_average_components():
    scheme = CostScheme(
        alphabet=["A|B", "C"],
        indel_cost=1.0,
        custom_substitution_costs={
            ("A", "C"): 2.0,
            ("B", "C"): 4.0,
        },
        custom_indel_costs={
            "A": 2.0,
            "B": 4.0,
        },
    )

    assert scheme.substitution_cost("A|B", "C") == 3.0
    assert scheme.indel_cost("A|B") == 3.0


def test_loads_costs_from_csv_and_json(tmp_path):
    substitution_path = tmp_path / "substitution.csv"
    indel_path = tmp_path / "indel.json"
    pd.DataFrame(
        [
            {"state_a": "A", "state_b": "B", "cost": 0.25},
        ]
    ).to_csv(substitution_path, index=False)
    indel_path.write_text('{"A": 2.5}', encoding="utf-8")

    scheme = CostScheme.from_files(
        alphabet=["A", "B"],
        substitution_costs_path=substitution_path,
        indel_costs_path=indel_path,
    )

    assert scheme.substitution_cost("A", "B") == 0.25
    assert scheme.indel_cost("A") == 2.5


def test_pipeline_merges_config_and_constructor_costs(tmp_path):
    input_path = tmp_path / "sequences.csv"
    pd.DataFrame(
        [
            {
                "Filename": "f1",
                "Sequence_Code": "A",
                "Sequence_Start": "0:00:00,0",
                "Sequence_End": "0:00:01,0",
                "id": "s1",
            },
            {
                "Filename": "f2",
                "Sequence_Code": "B",
                "Sequence_Start": "0:00:00,0",
                "Sequence_End": "0:00:01,0",
                "id": "s2",
            },
        ]
    ).to_csv(input_path, index=False)

    config = OMAConfig(
        input_path=input_path,
        output_dir=tmp_path / "out",
        sequence_representation="sts",
        overlap_strategy="split",
        custom_substitution_costs={("A", "B"): 5.0},
        custom_indel_costs={"A": 3.0},
        min_clusters=2,
        max_clusters=2,
    )
    pipeline = OMAPipeline(
        config,
        custom_substitution_costs={("A", "B"): 0.75},
        custom_indel_costs={"B": 4.0},
    )

    cost_scheme = CostScheme.from_files(
        alphabet=["A", "B"],
        default_substitution_cost=config.default_substitution_cost,
        indel_cost=config.indel_cost,
        custom_substitution_costs={
            **(config.custom_substitution_costs or {}),
            **pipeline.custom_substitution_costs,
        },
        custom_indel_costs={
            **(config.custom_indel_costs or {}),
            **pipeline.custom_indel_costs,
        },
        compound_cost_strategy=config.compound_cost_strategy,
    )

    assert cost_scheme.substitution_cost("A", "B") == 0.75
    assert cost_scheme.indel_cost("A") == 3.0
    assert cost_scheme.indel_cost("B") == 4.0
