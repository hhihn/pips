#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import numpy as np
import pandas as pd
from typing import Dict, Tuple, Optional

import matplotlib.pyplot as plt

from scipy.cluster.hierarchy import linkage, dendrogram, fcluster
from scipy.spatial.distance import pdist


# =============================================================================
# HILFSFUNKTIONEN (aus deinem Script, leicht aufgeräumt)
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


def extract_fachkraft_id(filename: str) -> str:
    # "11-P-4_transformed.xlsx" -> "11"
    parts = str(filename).split("-")
    return parts[0] if parts else "unknown"


def load_and_prepare_data(csv_path: str) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["base_code"] = df["Sequence_Code"].apply(extract_base_code)
    df["child_type"] = df["Sequence_Code"].str.extract(r" (PK|AK)$")[0].fillna("NA")
    df["start_sec"] = df["Sequence_Start"].apply(time_to_seconds)
    df["end_sec"] = df["Sequence_End"].apply(time_to_seconds)
    df["duration"] = df["end_sec"] - df["start_sec"]
    df["fachkraft"] = df["Filename"].apply(extract_fachkraft_id)
    return df


# =============================================================================
# FK-PROFILE BAUEN (Normalisierung + binär/frequency)
# =============================================================================


def build_fk_code_matrix(
    df: pd.DataFrame,
    exclude_prefixes: Tuple[str, ...] = ("6.1",),
    mode: str = "per_situation_rate",
) -> pd.DataFrame:
    """
    Erzeugt FK × Code Matrix.

    mode:
      - "binary": 0/1 ob Code bei FK jemals vorkommt (über alle Situationen)
      - "counts": Rohcounts über alle Situationen
      - "per_situation_rate": Counts / #Situationen der FK (empfohlen)
    """
    df = df.copy()

    # optional Codes ausschließen (z.B. 6.1.* = Phasenrahmen)
    def _keep(code: str) -> bool:
        return not any(str(code).startswith(p) for p in exclude_prefixes)

    df = df[df["base_code"].apply(_keep)].copy()
    df = df[df["base_code"].astype(str).str.len() > 0].copy()

    # Rohcounts: FK × Code
    fk_counts = df.groupby(["fachkraft", "base_code"]).size().unstack(fill_value=0)

    if mode == "counts":
        return fk_counts

    if mode == "binary":
        return (fk_counts > 0).astype(int)

    if mode == "per_situation_rate":
        # #Situationen pro FK
        situations_per_fk = df.groupby("fachkraft")["id"].nunique()
        # divide counts by number of situations (align index)
        rates = fk_counts.div(situations_per_fk, axis=0).fillna(0.0)
        return rates

    raise ValueError(f"Unknown mode: {mode}")


# =============================================================================
# DISTANZ + LINKAGE (Jaccard für binär)
# =============================================================================


def compute_distance_matrix(X: pd.DataFrame, metric: str) -> np.ndarray:
    """
    Gibt condensed distance vector (wie pdist) zurück.
    """
    arr = X.values.astype(float)

    if metric == "jaccard":
        # Jaccard erwartet 0/1. Falls nicht binär, vorher binärisieren.
        # Wir erzwingen das hier robust:
        arr_bin = (arr > 0).astype(int)
        return pdist(arr_bin, metric="jaccard")

    return pdist(arr, metric=metric)


def suggest_cut_distance_by_largest_jump(Z: np.ndarray) -> float:
    """
    Z ist linkage matrix.
    Z[:,2] sind Merge-Distanzen in aufsteigender Reihenfolge.
    Wir suchen den größten Sprung und schneiden knapp darunter.
    """
    d = Z[:, 2]
    if len(d) < 2:
        return float(d[-1]) if len(d) == 1 else 0.0

    jumps = np.diff(d)
    jmax = int(np.argmax(jumps))
    # Cut "vor" dem großen Sprung: zwischen d[jmax] und d[jmax+1]
    cut = float((d[jmax] + d[jmax + 1]) / 2.0)
    return cut


# =============================================================================
# CLUSTERING + PROFILE + EXPORTS
# =============================================================================


def cluster_fachkraefte(
    X: pd.DataFrame,
    out_dir: str,
    distance_metric: str = "jaccard",
    linkage_method: str = "average",
    cut_k: Optional[int] = None,
    cut_distance: Optional[float] = None,
    top_codes_for_interpretation: int = 12,
    top_codes_for_heatmap: int = 25,
) -> Dict:
    """
    Clustert Fachkräfte und erzeugt:
      - dendrogram.png
      - fk_clusters.csv
      - cluster_profiles.csv
      - heatmap_fk_topcodes.png

    cut_k: wenn gesetzt, bestimmt Anzahl Cluster
    cut_distance: wenn gesetzt, Distanz-Cut
    Wenn beides None: cut_distance wird automatisch über größten Sprung gewählt.
    """
    os.makedirs(out_dir, exist_ok=True)

    # Distanz + linkage
    dist_vec = compute_distance_matrix(X, metric=distance_metric)
    Z = linkage(dist_vec, method=linkage_method)

    # Cut bestimmen
    if cut_k is not None:
        clusters = fcluster(Z, t=int(cut_k), criterion="maxclust")
        cut_info = {"type": "k", "value": int(cut_k)}
    else:
        if cut_distance is None:
            cut_distance = suggest_cut_distance_by_largest_jump(Z)
        clusters = fcluster(Z, t=float(cut_distance), criterion="distance")
        cut_info = {"type": "distance", "value": float(cut_distance)}

    fk_ids = X.index.tolist()
    cluster_df = pd.DataFrame({"fachkraft": fk_ids, "cluster": clusters}).sort_values(
        ["cluster", "fachkraft"]
    )
    cluster_df.to_csv(os.path.join(out_dir, "fk_clusters.csv"), index=False)

    # --- Dendrogramm plotten ---
    plt.figure(figsize=(max(10, len(fk_ids) * 0.4), 6))
    dendrogram(
        Z,
        labels=fk_ids,
        leaf_rotation=90,
        leaf_font_size=8,
        color_threshold=(cut_info["value"] if cut_info["type"] == "distance" else None),
    )
    plt.title(
        f"Dendrogramm Fachkräfte | metric={distance_metric} | linkage={linkage_method} | cut={cut_info['type']}:{cut_info['value']}"
    )
    plt.xlabel("Fachkraft")
    plt.ylabel("Distanz")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "dendrogram.png"), dpi=160)
    plt.close()

    # --- Clusterprofile (Interpretation) ---
    # Profil = Mittelwerte pro Code innerhalb Cluster
    X_with_cluster = X.copy()
    X_with_cluster["cluster"] = clusters

    overall_mean = X.mean(axis=0)
    overall_std = X.std(axis=0).replace(0, np.nan)

    profile_rows = []
    for cid in sorted(np.unique(clusters)):
        members = X_with_cluster[X_with_cluster["cluster"] == cid].drop(
            columns=["cluster"]
        )
        mean_vec = members.mean(axis=0)

        delta = mean_vec - overall_mean
        z = (delta / overall_std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        # Top Codes nach Delta und Z
        top_delta = delta.sort_values(ascending=False).head(
            top_codes_for_interpretation
        )
        top_z = z.sort_values(ascending=False).head(top_codes_for_interpretation)

        profile_rows.append(
            {
                "cluster": cid,
                "n_fachkraefte": len(members),
                "top_codes_by_delta": ", ".join(
                    [f"{c}({top_delta[c]:.2f})" for c in top_delta.index]
                ),
                "top_codes_by_z": ", ".join(
                    [f"{c}({top_z[c]:.2f})" for c in top_z.index]
                ),
            }
        )

    profiles_df = pd.DataFrame(profile_rows).sort_values("cluster")
    profiles_df.to_csv(os.path.join(out_dir, "cluster_profiles.csv"), index=False)

    # --- Heatmap FK × TopCodes (nach Cluster sortiert) ---
    # wähle "informative" Codes: höchste Varianz oder höchste Gesamtmean
    # hier: Varianz
    code_variance = X.var(axis=0).sort_values(ascending=False)
    top_codes = code_variance.head(top_codes_for_heatmap).index.tolist()

    X_plot = X[top_codes].copy()
    # sortiere FK nach Cluster
    ordered_fks = cluster_df["fachkraft"].tolist()
    X_plot = X_plot.loc[ordered_fks]

    # Standardisieren pro Code für bessere Lesbarkeit (z-score pro Spalte)
    Xz = X_plot.apply(
        lambda col: (col - col.mean()) / (col.std() if col.std() > 0 else 1.0), axis=0
    )

    plt.figure(
        figsize=(max(12, len(top_codes) * 0.35), max(6, len(ordered_fks) * 0.25))
    )
    plt.imshow(Xz.values, aspect="auto", interpolation="nearest")
    plt.yticks(ticks=np.arange(len(ordered_fks)), labels=ordered_fks, fontsize=7)
    plt.xticks(
        ticks=np.arange(len(top_codes)), labels=top_codes, rotation=90, fontsize=7
    )
    plt.colorbar(label="z-score (pro Code)")
    plt.title("Heatmap: Fachkräfte × TopCodes (z-scored), nach Cluster sortiert")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "heatmap_fk_topcodes.png"), dpi=160)
    plt.close()

    return {
        "X": X,
        "dist_vec": dist_vec,
        "linkage": Z,
        "clusters": cluster_df,
        "profiles": profiles_df,
        "cut": cut_info,
        "top_codes_heatmap": top_codes,
    }


# =============================================================================
# REPORT: Zwei Varianten (6.2.1 vs 6.2.2) + FK-Typen
# =============================================================================


def filter_df_by_files_containing_code(
    df: pd.DataFrame, target_code: str
) -> pd.DataFrame:
    files = df.loc[df["base_code"] == target_code, "Filename"].unique()
    return df[df["Filename"].isin(files)].copy()


def run_fk_typing_pipeline(
    csv_path: str,
    output_root: str = "fk_typing_reports",
    fk_matrix_mode: str = "binary",  # "binary" empfohlen für Jaccard
    distance_metric: str = "jaccard",  # passt zu binary
    linkage_method: str = "average",  # passt zu Jaccard
    cut_k: Optional[int] = None,  # z.B. 4, 6, 8
    cut_distance: Optional[float] = None,  # optional
):
    os.makedirs(output_root, exist_ok=True)

    df_all = load_and_prepare_data(csv_path)

    for code in ["6.2.1", "6.2.2"]:
        df_sub = filter_df_by_files_containing_code(df_all, code)
        out_dir = os.path.join(output_root, f"files_with_{code}")

        print(f"\n=== FK-Typing für Dateien mit {code} ===")
        print(
            f"Rows: {len(df_sub)} | Filenames: {df_sub['Filename'].nunique()} | FKs: {df_sub['fachkraft'].nunique()}"
        )

        X = build_fk_code_matrix(df_sub, exclude_prefixes=("6.1",), mode=fk_matrix_mode)

        if X.shape[0] < 2:
            print("Zu wenige Fachkräfte für Clustering in diesem Subset.")
            continue

        result = cluster_fachkraefte(
            X=X,
            out_dir=out_dir,
            distance_metric=distance_metric,
            linkage_method=linkage_method,
            cut_k=cut_k,
            cut_distance=cut_distance,
        )

        print(f"Saved outputs to: {out_dir}")
        print(f"Cut used: {result['cut']}")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Beispiel:
    # - binär + Jaccard + average-linkage
    # - Cut automatisch (größter Sprung)
    run_fk_typing_pipeline(
        csv_path="extracted_sequences.csv",
        output_root="fk_typing_reports",
        fk_matrix_mode="binary",
        distance_metric="jaccard",
        linkage_method="average",
        cut_k=None,
        cut_distance=None,
    )
