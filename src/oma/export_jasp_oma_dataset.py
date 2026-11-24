#!/usr/bin/env python3
"""Export OMA outputs as JASP-friendly CSV datasets."""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


def load_distance_matrix(path: Path) -> pd.DataFrame:
    distance_matrix = pd.read_csv(path, index_col=0)
    distance_matrix.index = distance_matrix.index.astype(str)
    distance_matrix.columns = distance_matrix.columns.astype(str)
    distance_matrix = distance_matrix.astype(float)

    if distance_matrix.shape[0] != distance_matrix.shape[1]:
        raise ValueError("OMA distance matrix must be square.")

    if not distance_matrix.index.equals(distance_matrix.columns):
        raise ValueError(
            "OMA distance matrix rows and columns must contain the same "
            "sequence ids in the same order."
        )

    values = distance_matrix.to_numpy(dtype=float)
    if not np.all(np.isfinite(values)):
        raise ValueError("OMA distance matrix contains non-finite values.")

    if not np.allclose(values, values.T):
        raise ValueError("OMA distance matrix must be symmetric.")

    if not np.allclose(np.diag(values), 0.0):
        raise ValueError("OMA distance matrix diagonal must be zero.")

    return distance_matrix


def load_cluster_labels(path: Path) -> pd.DataFrame:
    labels = pd.read_csv(path, index_col=0)
    labels.index = labels.index.astype(str)

    if "cluster" not in labels.columns:
        raise ValueError("Cluster labels file must contain a 'cluster' column.")

    return labels[["cluster"]]


def load_care_types(path: Path) -> pd.DataFrame:
    care_types = pd.read_csv(path)
    required = {"id", "care_type", "care_type_status"}
    missing = required.difference(care_types.columns)
    if missing:
        raise ValueError(f"Care type file is missing required columns: {missing}")

    care_types = care_types.copy()
    care_types["id"] = care_types["id"].astype(str)
    return care_types


def load_optional_single_row(path: Path) -> Dict[str, object]:
    if not path.exists():
        return {}

    df = pd.read_csv(path)
    if df.empty:
        return {}

    return df.iloc[0].to_dict()


def align_metadata(
    distance_matrix: pd.DataFrame,
    cluster_labels: pd.DataFrame,
    care_types: pd.DataFrame,
) -> pd.DataFrame:
    ids = distance_matrix.index.astype(str)
    labels = cluster_labels.reindex(ids)
    care = care_types.set_index("id").reindex(ids)

    missing_labels = labels[labels["cluster"].isna()].index.tolist()
    if missing_labels:
        raise ValueError(f"Missing cluster labels for sequence ids: {missing_labels}")

    missing_care = care[care["care_type"].isna()].index.tolist()
    if missing_care:
        raise ValueError(f"Missing care type rows for sequence ids: {missing_care}")

    metadata = care.copy()
    metadata.insert(0, "id", ids)
    metadata["cluster"] = labels["cluster"].to_numpy()
    metadata["is_clean_care_type"] = (
        metadata["care_type_status"].astype(str) == "clean"
    )
    metadata["care_type_for_clean_tests"] = metadata["care_type"].where(
        metadata["is_clean_care_type"],
        "",
    )

    return metadata.reset_index(drop=True)


def classical_mds(distance_matrix: pd.DataFrame, n_components: int = 2) -> pd.DataFrame:
    n = distance_matrix.shape[0]
    ids = distance_matrix.index.astype(str)
    if n == 0 or n_components <= 0:
        return pd.DataFrame(index=ids)

    values = distance_matrix.to_numpy(dtype=float)
    centering = np.eye(n) - np.ones((n, n)) / n
    gram = -0.5 * centering @ (values**2) @ centering
    eigenvalues, eigenvectors = np.linalg.eigh(gram)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    coordinates = np.zeros((n, n_components), dtype=float)
    for component in range(min(n_components, n)):
        eigenvalue = eigenvalues[component]
        if eigenvalue > 0:
            coordinates[:, component] = (
                eigenvectors[:, component] * np.sqrt(eigenvalue)
            )

    return pd.DataFrame(
        coordinates,
        index=ids,
        columns=[f"mds_{i + 1}" for i in range(n_components)],
    )


def sequence_level_dataset(
    distance_matrix: pd.DataFrame,
    metadata: pd.DataFrame,
    n_mds_components: int = 2,
) -> pd.DataFrame:
    result = metadata.copy()
    ids = result["id"].astype(str).tolist()

    result["mean_distance_all"] = [
        _mean_to_mask(distance_matrix, sequence_id, distance_matrix.index != sequence_id)
        for sequence_id in ids
    ]
    result["median_distance_all"] = [
        _median_to_mask(distance_matrix, sequence_id, distance_matrix.index != sequence_id)
        for sequence_id in ids
    ]
    result["min_distance_other"] = [
        _min_to_mask(distance_matrix, sequence_id, distance_matrix.index != sequence_id)
        for sequence_id in ids
    ]
    result["max_distance_other"] = [
        _max_to_mask(distance_matrix, sequence_id, distance_matrix.index != sequence_id)
        for sequence_id in ids
    ]

    clean_lookup = result.set_index("id")["is_clean_care_type"].to_dict()
    care_lookup = result.set_index("id")["care_type"].to_dict()
    cluster_lookup = result.set_index("id")["cluster"].to_dict()

    result["mean_distance_same_care_type_clean"] = [
        _mean_to_ids(
            distance_matrix,
            sequence_id,
            [
                other_id
                for other_id in ids
                if other_id != sequence_id
                and clean_lookup[sequence_id]
                and clean_lookup[other_id]
                and care_lookup[other_id] == care_lookup[sequence_id]
            ],
        )
        for sequence_id in ids
    ]
    result["mean_distance_other_care_type_clean"] = [
        _mean_to_ids(
            distance_matrix,
            sequence_id,
            [
                other_id
                for other_id in ids
                if other_id != sequence_id
                and clean_lookup[sequence_id]
                and clean_lookup[other_id]
                and care_lookup[other_id] != care_lookup[sequence_id]
            ],
        )
        for sequence_id in ids
    ]
    result["mean_distance_same_cluster"] = [
        _mean_to_ids(
            distance_matrix,
            sequence_id,
            [
                other_id
                for other_id in ids
                if other_id != sequence_id
                and cluster_lookup[other_id] == cluster_lookup[sequence_id]
            ],
        )
        for sequence_id in ids
    ]
    result["mean_distance_other_cluster"] = [
        _mean_to_ids(
            distance_matrix,
            sequence_id,
            [
                other_id
                for other_id in ids
                if other_id != sequence_id
                and cluster_lookup[other_id] != cluster_lookup[sequence_id]
            ],
        )
        for sequence_id in ids
    ]

    if n_mds_components > 0:
        coordinates = classical_mds(distance_matrix, n_mds_components)
        result = result.merge(
            coordinates.reset_index().rename(columns={"index": "id"}),
            on="id",
            how="left",
        )

    return result


def distance_features_dataset(
    distance_matrix: pd.DataFrame,
    metadata: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    feature_names = _distance_feature_names(distance_matrix.columns.astype(str))
    distances = distance_matrix.copy()
    distances.columns = [feature_names[sequence_id] for sequence_id in distances.columns]
    distances.insert(0, "id", distances.index.astype(str))

    feature_metadata = pd.DataFrame(
        [
            {
                "sequence_id": sequence_id,
                "distance_feature": feature_name,
            }
            for sequence_id, feature_name in feature_names.items()
        ]
    )

    return metadata.merge(distances, on="id", how="left"), feature_metadata


def pairwise_distances_dataset(
    distance_matrix: pd.DataFrame,
    metadata: pd.DataFrame,
) -> pd.DataFrame:
    by_id = metadata.set_index("id")
    ids = distance_matrix.index.astype(str).tolist()
    rows = []

    for left_index, id_a in enumerate(ids[:-1]):
        for id_b in ids[left_index + 1 :]:
            row_a = by_id.loc[id_a]
            row_b = by_id.loc[id_b]
            clean_pair = bool(
                row_a["is_clean_care_type"] and row_b["is_clean_care_type"]
            )
            same_clean_care_type = bool(
                clean_pair and row_a["care_type"] == row_b["care_type"]
            )
            rows.append(
                {
                    "id_a": id_a,
                    "id_b": id_b,
                    "filename_a": row_a.get("filename", ""),
                    "filename_b": row_b.get("filename", ""),
                    "care_type_a": row_a["care_type"],
                    "care_type_b": row_b["care_type"],
                    "care_type_status_a": row_a["care_type_status"],
                    "care_type_status_b": row_b["care_type_status"],
                    "care_type_pair": _pair_label(row_a["care_type"], row_b["care_type"]),
                    "cluster_a": row_a["cluster"],
                    "cluster_b": row_b["cluster"],
                    "oma_distance": float(distance_matrix.loc[id_a, id_b]),
                    "both_clean_care_type": _yes_no(clean_pair),
                    "same_clean_care_type": _yes_no(same_clean_care_type),
                    "same_cluster": _yes_no(row_a["cluster"] == row_b["cluster"]),
                }
            )

    return pd.DataFrame(rows)


def care_cluster_counts_dataset(metadata: pd.DataFrame) -> pd.DataFrame:
    clean = metadata[metadata["is_clean_care_type"]].copy()
    care_types = sorted(clean["care_type"].dropna().unique().tolist())
    clusters = sorted(clean["cluster"].dropna().unique().tolist())
    observed = (
        clean.groupby(["care_type", "cluster"], dropna=False)
        .size()
        .rename("count")
    )
    rows = []

    for care_type in care_types:
        for cluster in clusters:
            rows.append(
                {
                    "care_type": care_type,
                    "cluster": cluster,
                    "count": int(observed.get((care_type, cluster), 0)),
                    "care_type_status": "clean",
                }
            )

    return pd.DataFrame(rows)


def analysis_summary_dataset(oma_output: Path) -> pd.DataFrame:
    permanova = load_optional_single_row(
        oma_output / "care_type_distance_permanova.csv"
    )
    association = load_optional_single_row(
        oma_output / "care_type_cluster_association.csv"
    )
    recommendation = load_optional_single_row(
        oma_output / "care_type_recommendation.csv"
    )

    return pd.DataFrame(
        [
            {
                "distance_test": permanova.get("comparison", ""),
                "distance_n_total": permanova.get("n_total", np.nan),
                "distance_n_mixed_excluded": permanova.get(
                    "n_mixed_excluded",
                    np.nan,
                ),
                "distance_pseudo_f": permanova.get("pseudo_f_score", np.nan),
                "distance_r_squared": permanova.get("r_squared", np.nan),
                "distance_p_value": permanova.get("p_value", np.nan),
                "distance_permutations": permanova.get("permutations", np.nan),
                "cluster_association_test": association.get("test", ""),
                "cluster_association_n_total": association.get("n_total", np.nan),
                "cluster_association_p_value": association.get("p_value", np.nan),
                "cluster_association_odds_ratio": association.get(
                    "odds_ratio",
                    np.nan,
                ),
                "cluster_association_cramers_v": association.get(
                    "cramers_v",
                    np.nan,
                ),
                "cluster_association_chi_square": association.get(
                    "chi_square",
                    np.nan,
                ),
                "cluster_association_df": association.get(
                    "degrees_of_freedom",
                    np.nan,
                ),
                "recommendation": recommendation.get("recommendation", ""),
                "separate_oma_recommended": recommendation.get(
                    "separate_oma_recommended",
                    "",
                ),
            }
        ]
    )


def load_optional_dataframe(path: Path) -> Optional[pd.DataFrame]:
    if not path.exists():
        return None

    return pd.read_csv(path)


def oma_export_datasets(
    oma_output: Path,
    n_mds_components: int = 2,
) -> Dict[str, pd.DataFrame]:
    oma_output = Path(oma_output)
    distance_matrix = load_distance_matrix(oma_output / "oma_distance_matrix.csv")
    cluster_labels = load_cluster_labels(oma_output / "cluster_labels.csv")
    care_types = load_care_types(oma_output / "care_type_by_sequence.csv")
    metadata = align_metadata(distance_matrix, cluster_labels, care_types)

    sequence_level = sequence_level_dataset(
        distance_matrix,
        metadata,
        n_mds_components=n_mds_components,
    )
    distance_features, feature_metadata = distance_features_dataset(
        distance_matrix,
        metadata,
    )
    pairwise_distances = pairwise_distances_dataset(distance_matrix, metadata)
    care_cluster_counts = care_cluster_counts_dataset(metadata)
    analysis_summary = analysis_summary_dataset(oma_output)
    cluster_code_frequencies = load_optional_dataframe(
        oma_output / "cluster_code_frequencies.csv"
    )
    raw_cluster_code_frequencies = load_optional_dataframe(
        oma_output / "raw_cluster_code_frequencies.csv"
    )

    outputs = {
        "jasp_sequence_level.csv": sequence_level,
        "jasp_distance_features.csv": distance_features,
        "jasp_distance_feature_columns.csv": feature_metadata,
        "jasp_pairwise_distances.csv": pairwise_distances,
        "jasp_care_cluster_counts.csv": care_cluster_counts,
        "jasp_analysis_summary.csv": analysis_summary,
    }
    if cluster_code_frequencies is not None:
        outputs["jasp_cluster_code_frequencies.csv"] = cluster_code_frequencies
    if raw_cluster_code_frequencies is not None:
        outputs["jasp_raw_cluster_code_frequencies.csv"] = (
            raw_cluster_code_frequencies
        )

    return outputs


def export_jasp_datasets(
    oma_output: Path,
    out_dir: Optional[Path] = None,
    n_mds_components: int = 2,
) -> List[Path]:
    oma_output = Path(oma_output)
    out_dir = Path(out_dir) if out_dir is not None else oma_output / "jasp"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = oma_export_datasets(oma_output, n_mds_components=n_mds_components)

    written_paths = []
    for filename, dataframe in outputs.items():
        path = out_dir / filename
        dataframe.to_csv(path, index=False, encoding="utf-8")
        written_paths.append(path)

    return written_paths


def export_excel_datasets(
    oma_output: Path,
    out_dir: Optional[Path] = None,
    n_mds_components: int = 2,
) -> List[Path]:
    oma_output = Path(oma_output)
    out_dir = Path(out_dir) if out_dir is not None else oma_output / "excel"
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs = oma_export_datasets(oma_output, n_mds_components=n_mds_components)

    written_paths = []
    for filename, dataframe in outputs.items():
        excel_filename = filename.replace("jasp_", "excel_", 1)
        path = out_dir / excel_filename
        dataframe.to_csv(
            path,
            index=False,
            encoding="utf-8-sig",
            sep=";",
            decimal=",",
            float_format="%.6f",
        )
        written_paths.append(path)

    return written_paths


def _mean_to_mask(
    distance_matrix: pd.DataFrame,
    sequence_id: str,
    mask: np.ndarray,
) -> float:
    values = distance_matrix.loc[sequence_id].to_numpy(dtype=float)[mask]
    if values.size == 0:
        return np.nan

    return float(np.mean(values))


def _median_to_mask(
    distance_matrix: pd.DataFrame,
    sequence_id: str,
    mask: np.ndarray,
) -> float:
    values = distance_matrix.loc[sequence_id].to_numpy(dtype=float)[mask]
    if values.size == 0:
        return np.nan

    return float(np.median(values))


def _min_to_mask(
    distance_matrix: pd.DataFrame,
    sequence_id: str,
    mask: np.ndarray,
) -> float:
    values = distance_matrix.loc[sequence_id].to_numpy(dtype=float)[mask]
    if values.size == 0:
        return np.nan

    return float(np.min(values))


def _max_to_mask(
    distance_matrix: pd.DataFrame,
    sequence_id: str,
    mask: np.ndarray,
) -> float:
    values = distance_matrix.loc[sequence_id].to_numpy(dtype=float)[mask]
    if values.size == 0:
        return np.nan

    return float(np.max(values))


def _mean_to_ids(
    distance_matrix: pd.DataFrame,
    sequence_id: str,
    target_ids: List[str],
) -> float:
    if not target_ids:
        return np.nan

    values = distance_matrix.loc[sequence_id, target_ids].to_numpy(dtype=float)
    return float(np.mean(values))


def _distance_feature_names(sequence_ids: pd.Index) -> Dict[str, str]:
    used = set()
    names = {}

    for sequence_id in sequence_ids:
        base = "dist_to_" + re.sub(r"[^A-Za-z0-9_]+", "_", str(sequence_id))
        base = re.sub(r"_+", "_", base).strip("_")
        if not base:
            base = "dist_to_sequence"

        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1

        used.add(name)
        names[str(sequence_id)] = name

    return names


def _pair_label(value_a: object, value_b: object) -> str:
    values = sorted([str(value_a), str(value_b)])
    return " | ".join(values)


def _yes_no(value: bool) -> str:
    return "yes" if bool(value) else "no"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create JASP-ready CSV datasets from OMA output files.",
    )
    parser.add_argument(
        "--oma-output",
        type=Path,
        default=Path("oma_output"),
        help="Directory containing OMA output CSV files.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory. Defaults to <oma-output>/jasp.",
    )
    parser.add_argument(
        "--mds-components",
        type=int,
        default=2,
        help="Number of classical MDS coordinate columns to include.",
    )
    parser.add_argument(
        "--excel-out",
        type=Path,
        default=None,
        help="Excel-friendly output directory. Defaults to <oma-output>/excel.",
    )
    parser.add_argument(
        "--skip-excel",
        action="store_true",
        help="Only write JASP CSVs, not Excel-friendly CSVs.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    written_paths = export_jasp_datasets(
        oma_output=args.oma_output,
        out_dir=args.out,
        n_mds_components=args.mds_components,
    )

    print("Wrote JASP-ready datasets:")
    for path in written_paths:
        print(f"- {path}")

    if not args.skip_excel:
        excel_paths = export_excel_datasets(
            oma_output=args.oma_output,
            out_dir=args.excel_out,
            n_mds_components=args.mds_components,
        )

        print("Wrote Excel-friendly datasets:")
        for path in excel_paths:
            print(f"- {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
