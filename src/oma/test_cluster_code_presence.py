import pandas as pd
import pytest

from export_cluster_code_presence import supplement_phases
from OMAConfig import OMAConfig
from SequenceInterpreter import SequenceInterpreter


def fixtures():
    extracted = pd.DataFrame([
        ["a", "video.xlsx", "6.1.1 PK", "0:00:00,0", "0:00:10,0"],
        ["b", "video.xlsx", "6.1.1 PK", "0:00:10,0", "0:00:20,0"],
    ], columns=["id", "Filename", "Sequence_Code", "Sequence_Start", "Sequence_End"])
    upstream = pd.DataFrame([
        ["video.xlsx", "0:00:00,0", "0:00:10,0", "6.1.2 phase", "0:00:00,0", "0:00:01,0"],
        ["video.xlsx", "0:00:00,0", "0:00:10,0", "6.1.2 phase", "0:00:02,0", "0:00:03,0"],
        ["video.xlsx", "0:00:10,0", "0:00:20,0", "6.1.3 phase", "0:00:11,0", "0:00:12,0"],
    ], columns=["Filename", "Child_Start", "Child_End", "Sequence_Code", "Sequence_Start", "Sequence_End"])
    return extracted, upstream, pd.Series([1, 2], index=["a", "b"], name="cluster")


def test_join_uses_care_window_and_counts_each_sequence_once(tmp_path):
    extracted, upstream, labels = fixtures()
    combined, additions = supplement_phases(extracted, upstream, labels)
    assert additions.groupby("id").size().to_dict() == {"a": 2, "b": 1}
    scores = SequenceInterpreter(OMAConfig(input_path=tmp_path)).raw_cluster_code_frequencies(combined, labels)
    phase = scores[(scores.cluster == 1) & (scores.code == "6.1.2")].iloc[0]
    assert phase.raw_observation_count == 2
    assert phase.sequence_count_with_code == 1
    again, _ = supplement_phases(combined, upstream, labels)
    pd.testing.assert_frame_equal(combined, again)


def test_missing_source_window_fails_instead_of_reporting_absence():
    extracted, upstream, labels = fixtures()
    with pytest.raises(ValueError, match="no upstream phase rows"):
        supplement_phases(extracted, upstream.iloc[:2], labels)
