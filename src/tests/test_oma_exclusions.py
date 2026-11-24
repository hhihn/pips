from pathlib import Path
import sys

import pandas as pd


OMA_DIR = Path(__file__).resolve().parents[1] / "oma"
sys.path.insert(0, str(OMA_DIR))

from MAXQDALoader import MaxQDALoader
from OMAConfig import OMAConfig
from SequenceBuilder import SequenceBuilder


def test_loader_does_not_drop_rows_with_excluded_codes(tmp_path):
    input_path = tmp_path / "sequences.csv"
    pd.DataFrame(
        [
            {
                "Filename": "f1",
                "Sequence_Code": "DROP PK",
                "Sequence_Start": "0:00:00,0",
                "Sequence_End": "0:00:01,0",
                "id": "s1",
            },
            {
                "Filename": "f1",
                "Sequence_Code": "KEEP PK",
                "Sequence_Start": "0:00:01,0",
                "Sequence_End": "0:00:02,0",
                "id": "s1",
            },
        ]
    ).to_csv(input_path, index=False)
    config = OMAConfig(
        input_path=input_path,
        excluded_codes=["DROP"],
    )

    loaded = MaxQDALoader(config).load()

    assert len(loaded) == 2
    assert loaded[config.code_col].tolist() == ["DROP PK", "KEEP PK"]


def test_sequence_builder_removes_only_excluded_codes_from_sequence():
    config = OMAConfig(
        input_path=Path("unused.csv"),
        time_step_seconds=1.0,
        overlap_strategy="split",
        include_empty_state=False,
        excluded_codes=["DROP"],
    )
    df = pd.DataFrame(
        [
            {
                "Sequence_Code": "DROP PK",
                "start_s": 0.0,
                "end_s": 1.0,
                "id": "s1",
            },
            {
                "Sequence_Code": "KEEP PK",
                "start_s": 0.0,
                "end_s": 1.0,
                "id": "s1",
            },
            {
                "Sequence_Code": "KEEP PK",
                "start_s": 1.0,
                "end_s": 2.0,
                "id": "s1",
            },
        ]
    )

    sequences = SequenceBuilder(config).build_sequences(df)

    assert sequences["s1"] == ["KEEP PK", "KEEP PK"]
