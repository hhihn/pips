"""Describe existing OMA clusters, supplementing care phases from upstream rows.

Run from any directory: python src/oma/export_cluster_code_presence.py
Clustering inputs, distances and labels are never rewritten. Supplementary
codes retain numeric IDs without PK/AK suffixes: no addressee is inferred.
Speech presence includes any upstream 5.3.1 annotation, regardless of addressee.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from MAXQDALoader import MaxQDALoader
from OMAConfig import OMAConfig
from SequenceInterpreter import SequenceInterpreter

ROOT = Path(__file__).resolve().parents[2]
PHASE_CODES = ("6.1.2", "6.1.3", "6.1.4", "6.4.1", "5.3.1")


def supplement_phases(extracted, upstream, labels):
    """Join by filename and exact care boundaries, never by row numbering."""
    extracted = extracted.copy()
    extracted["id"] = extracted["id"].astype(str)
    keys = ["Filename", "care_start_s", "care_end_s"]
    care = extracted[extracted.Sequence_Code.str.match(r"^6\.1\.1(?:\s|$)")].copy()
    for dest, source in (("care_start_s", "Sequence_Start"), ("care_end_s", "Sequence_End")):
        care[dest] = care[source].map(MaxQDALoader._parse_timestamp)
    care = care[["id", *keys]].drop_duplicates()
    if care.duplicated("id").any() or care.duplicated(keys).any():
        raise ValueError("Care windows must map uniquely to sequence IDs")
    if set(care.id) != set(labels.index):
        raise ValueError("Care windows and existing cluster IDs do not match")

    source = upstream.copy()
    source["numeric_code"] = source.Sequence_Code.astype(str).str.extract(r"^(\d+(?:\.\d+)*)", expand=False)
    source = source[source.numeric_code.isin(PHASE_CODES)].copy()
    for dest, origin in (("care_start_s", "Child_Start"), ("care_end_s", "Child_End")):
        source[dest] = source[origin].map(MaxQDALoader._parse_timestamp)
    source = source.merge(care, on=keys, how="inner", validate="many_to_one")
    missing_windows = care.merge(source[keys].drop_duplicates(), on=keys, how="left", indicator=True)
    if missing_windows._merge.eq("left_only").any():
        raise ValueError("Some existing sequences have no upstream phase rows; check source version")
    source["Sequence_Code"] = source.numeric_code
    additions = source[["id", "Filename", "Sequence_Code", "Sequence_Start", "Sequence_End"]].drop_duplicates()
    starts = additions.Sequence_Start.map(MaxQDALoader._parse_timestamp)
    ends = additions.Sequence_End.map(MaxQDALoader._parse_timestamp)
    if (ends <= starts).any():
        raise ValueError("Supplementary phase interval has non-positive duration")
    # Replace any previously included phases, making repeated runs idempotent.
    numeric = extracted.Sequence_Code.str.extract(r"^(\d+(?:\.\d+)*)", expand=False)
    combined = pd.concat([extracted[~numeric.isin(PHASE_CODES)], additions], ignore_index=True)
    return combined, additions


def export(extracted_path, upstream_path, output):
    labels = pd.read_csv(output / "cluster_labels.csv", index_col=0)["cluster"]
    labels.index = labels.index.astype(str)
    if not labels.index.is_unique:
        raise ValueError("Duplicate cluster sequence IDs")
    combined, additions = supplement_phases(pd.read_csv(extracted_path), pd.read_csv(upstream_path), labels)
    config = OMAConfig(input_path=extracted_path)
    frequencies = SequenceInterpreter(config).raw_cluster_code_frequencies(combined, labels)
    # Include explicit zeros for codes absent from a cluster.
    codes = sorted(combined.Sequence_Code.unique())
    matrix = pd.crosstab(combined.id, combined.Sequence_Code).reindex(index=labels.index, columns=codes, fill_value=0).gt(0).astype(int)
    matrix.insert(0, "cluster", labels)
    matrix.index.name = "id"
    frequencies.to_csv(output / "supplemented_cluster_code_frequencies.csv", index=False)
    additions.to_csv(output / "supplementary_phase_annotations.csv", index=False)
    matrix.to_csv(output / "sequence_code_presence.csv")
    excel = output / "excel"
    excel.mkdir(exist_ok=True)
    summary = frequencies.rename(columns={"long_name": "name", "raw_observation_count": "anzahl", "raw_observation_relative_within_cluster": "anzahl_relativ_im_cluster", "sequence_count_with_code": "anzahl_sequenzen_mit_code", "sequence_relative_with_code": "anzahl_sequenzen_mit_code_relativ_im_cluster"})
    summary.to_csv(excel / "anzahl_codes_per_cluster_per_sequenz.csv", index=False, sep=";", decimal=",", encoding="utf-8-sig", float_format="%.6f")
    # Chart-ready percentages, including zero counts.
    chart = matrix.drop(columns="cluster").groupby(labels).mean().T * 100
    chart.columns = [f"Cluster {cluster} (%)" for cluster in chart.columns]
    chart.index.name = "code"
    chart.to_csv(excel / "code_presence_percent_by_cluster.csv", sep=";", decimal=",", encoding="utf-8-sig", float_format="%.2f")
    print(frequencies[frequencies.code.isin(PHASE_CODES)][["cluster", "code", "sequence_count_with_code", "n_sequences_in_cluster", "sequence_percent_with_code"]].to_string(index=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--extracted", type=Path, default=ROOT / "src/extracted_sequences.csv")
    parser.add_argument("--upstream", type=Path, default=ROOT / "data/transformed/analysis_results/sequence_analysis.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "src/oma/oma_output")
    args = parser.parse_args()
    export(args.extracted, args.upstream, args.output)
