#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Hierarchisches Clustering – NICHT nach Fachkraft, sondern NUR nach Filename.

- Jede Zeile = ein Video/Sequence-File (Filename)
- Features = Code-Profile pro Filename (binary / counts / per_situation_rate)
- Distanz = Jaccard (für binary empfohlen)
- Linkage = average (passt zu Jaccard)
- Cut: erzwingt IMMER genau k Cluster (maxclust) -> ALLE Filenames landen sicher in einem Cluster
- Outputs pro Subset (6.2.1 / 6.2.2):
  - dendrogram.png
  - file_clusters.csv
  - cluster_profiles.csv
  - heatmap_files_topcodes.png
"""

import os
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional, List

import matplotlib.pyplot as plt

from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from scipy.spatial.distance import pdist


# =============================================================================
# HILFSFUNKTIONEN
# =============================================================================

def time_to_seconds(time_str: str) -> float:
    if not isinstance(time_str, str) or not time_str.strip():
        return 0.0
    time_str = time_str.strip().replace(",", ".").strip('"')
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
    except ValueError:
        pass
    return 0.0


def extract_base_code(code: str) -> str:
    if pd.isna(code):
        return ""
    return str(code).replace(" PK", "").replace(" AK", "").strip()


def load_and_prepare_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["base_code"] = df["Sequence_Code"].apply(extract_base_code)
    df["child_type"] = df["Sequence_Code"].str.extract(r" (PK|AK)$")[0].fillna("NA")
    df["start_sec"] = df["Sequence_Start"].apply(time_to_seconds)
    df["end_sec"] = df["Sequence_End"].apply(time_to_seconds)
    df["duration"] = df["end_sec"] - df["start_sec"]
    return df


# =============================================================================
# FILE-PROFILE BAUEN
# =============================================================================

def build_file_code_matrix(
    df: pd.DataFrame,
    exclude_prefixes: Tuple[str, ...] = ("6.1",),
    mode: str = "binary",
) -> pd.DataFrame:
    """
    Erzeugt Filename × Code Matrix.

    mode:
      - "binary": 0/1 ob Code im File vorkommt
      - "counts": Rohcounts im File
      - "per_situation_rate": Counts / #Situationen im File (id.nunique pro Filename)
    """
    d = df.copy()

    def _keep(code: str) -> bool:
        return not any(str(code).startswith(p) for p in exclude_prefixes)

    d = d[d["base_code"].apply(_keep)].copy()
    d = d[d["base_code"].astype(str).str.len() > 0].copy()

    # Rohcounts: Filename × Code
    file_counts = d.groupby(["Filename", "base_code"]).size().unstack(fill_value=0)

    if mode == "counts":
        return file_counts

    if mode == "binary":
        return (file_counts > 0).astype(int)

    if mode == "per_situation_rate":
        if "id" not in d.columns:
            # fallback: pro file 1 "Situation"
            denom = pd.Series(1, index=file_counts.index)
        else:
            denom = d.groupby("Filename")["id"].nunique()
        rates = file_counts.div(denom, axis=0).fillna(0.0)
        return rates

    raise ValueError(f"Unknown mode: {mode}")


# =============================================================================
# DISTANZ + LINKAGE
# =============================================================================

def compute_distance_matrix(X: pd.DataFrame, metric: str) -> np.ndarray:
    arr = X.values.astype(float)

    if metric == "jaccard":
        arr_bin = (arr > 0).astype(int)
        return pdist(arr_bin, metric="jaccard")

    return pdist(arr, metric=metric)


# =============================================================================
# CLUSTERING + OUTPUTS
# =============================================================================

def cluster_files(
    X: pd.DataFrame,
    out_dir: str,
    distance_metric: str = "jaccard",
    linkage_method: str = "average",
    cut_k: int = 4,  # <- WICHTIG: erzwingt genau k Cluster
    top_codes_for_interpretation: int = 12,
    top_codes_for_heatmap: int = 25,
) -> Dict:
    os.makedirs(out_dir, exist_ok=True)

    # Distanz + linkage
    dist_vec = compute_distance_matrix(X, metric=distance_metric)
    Z = linkage(dist_vec, method=linkage_method)

    # Cut: EXAKT k Cluster => alle Filenames landen sicher in einem Cluster
    k = int(max(1, cut_k))
    clusters = fcluster(Z, t=k, criterion="maxclust")
    cut_info = {"type": "k", "value": k}

    file_ids = X.index.tolist()
    cluster_df = (
        pd.DataFrame({"Filename": file_ids, "cluster": clusters})
        .sort_values(["cluster", "Filename"])
        .reset_index(drop=True)
    )
    cluster_df.to_csv(os.path.join(out_dir, "file_clusters.csv"), index=False)

    # --- Dendrogramm ---
    # Größe dynamisch, damit Labels nicht “verschwinden”
    fig_w = max(12, len(file_ids) * 0.55)
    fig_h = 6
    plt.figure(figsize=(fig_w, fig_h))
    dendrogram(
        Z,
        labels=file_ids,
        leaf_rotation=90,
        leaf_font_size=8,
        color_threshold=None,  # bei maxclust weniger sinnvoll
    )
    plt.title(
        f"Dendrogramm Sequenzen | metric={distance_metric} | linkage={linkage_method} | cut=k:{k}"
    )
    plt.xlabel("Filename")
    plt.ylabel("Distanz")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "dendrogram.png"), dpi=180)
    plt.close()

    # --- Clusterprofile ---
    X_with_cluster = X.copy()
    X_with_cluster["cluster"] = clusters

    overall_mean = X.mean(axis=0)
    overall_std = X.std(axis=0).replace(0, np.nan)

    profile_rows = []
    for cid in sorted(np.unique(clusters)):
        members = X_with_cluster[X_with_cluster["cluster"] == cid].drop(columns=["cluster"])
        mean_vec = members.mean(axis=0)

        delta = mean_vec - overall_mean
        z = (delta / overall_std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        top_delta = delta.sort_values(ascending=False).head(top_codes_for_interpretation)
        top_z = z.sort_values(ascending=False).head(top_codes_for_interpretation)

        profile_rows.append({
            "cluster": cid,
            "n_files": len(members),
            "top_codes_by_delta": ", ".join([f"{c}({top_delta[c]:.2f})" for c in top_delta.index]),
            "top_codes_by_z": ", ".join([f"{c}({top_z[c]:.2f})" for c in top_z.index]),
        })

    profiles_df = pd.DataFrame(profile_rows).sort_values("cluster")
    profiles_df.to_csv(os.path.join(out_dir, "cluster_profiles.csv"), index=False)

    # --- Heatmap ---
    code_variance = X.var(axis=0).sort_values(ascending=False)
    top_codes = code_variance.head(top_codes_for_heatmap).index.tolist()

    X_plot = X[top_codes].copy()
    ordered_files = cluster_df["Filename"].tolist()
    X_plot = X_plot.loc[ordered_files]

    # z-score pro Code-Spalte
    Xz = X_plot.apply(lambda col: (col - col.mean()) / (col.std() if col.std() > 0 else 1.0), axis=0)

    plt.figure(figsize=(max(12, len(top_codes) * 0.35), max(6, len(ordered_files) * 0.30)))
    plt.imshow(Xz.values, aspect="auto", interpolation="nearest")
    plt.yticks(ticks=np.arange(len(ordered_files)), labels=ordered_files, fontsize=7)
    plt.xticks(ticks=np.arange(len(top_codes)), labels=top_codes, rotation=90, fontsize=7)
    plt.colorbar(label="z-score (pro Code)")
    plt.title("Heatmap: Filenames × TopCodes (z-scored), nach Cluster sortiert")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "heatmap_files_topcodes.png"), dpi=180)
    plt.close()

    return {
        "X": X,
        "linkage": Z,
        "clusters": cluster_df,
        "profiles": profiles_df,
        "cut": cut_info,
        "top_codes_heatmap": top_codes,
    }


# =============================================================================
# SUBSETS (6.2.1 / 6.2.2)
# =============================================================================

def filter_df_by_files_containing_code(df: pd.DataFrame, target_code: str) -> pd.DataFrame:
    files = df.loc[df["base_code"] == target_code, "Filename"].unique()
    return df[df["Filename"].isin(files)].copy()


def run_sequence_clustering_pipeline(
    csv_path: str = "extracted_sequences.csv",
    output_root: str = "sequence_typing_reports",
    matrix_mode: str = "binary",
    distance_metric: str = "jaccard",
    linkage_method: str = "average",
    cut_k: int = 4,
):
    os.makedirs(output_root, exist_ok=True)

    df_all = load_and_prepare_data(csv_path)

    for code in ["6.2.1", "6.2.2"]:
        df_sub = filter_df_by_files_containing_code(df_all, code)
        out_dir = os.path.join(output_root, f"files_with_{code}")

        print(f"\n=== Sequence-Clustering für Dateien mit {code} ===")
        print(f"Rows: {len(df_sub)} | Filenames: {df_sub['Filename'].nunique()}")

        X = build_file_code_matrix(df_sub, exclude_prefixes=("6.1",), mode=matrix_mode)

        if X.shape[0] < 2:
            print("Zu wenige Filenames für Clustering in diesem Subset.")
            continue

        result = cluster_files(
            X=X,
            out_dir=out_dir,
            distance_metric=distance_metric,
            linkage_method=linkage_method,
            cut_k=cut_k,  # <- erzwingt “alle sind irgendwo drin”
        )

        print(f"Saved outputs to: {out_dir}")
        print(f"Cut used: {result['cut']}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Standard: 4 Cluster, alle Filenames bekommen einen Cluster
    run_sequence_clustering_pipeline(
        csv_path="extracted_sequences.csv",
        output_root="sequence_typing_reports",
        matrix_mode="binary",
        distance_metric="jaccard",
        linkage_method="average",
        cut_k=4,
    )
