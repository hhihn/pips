#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Two-level (hierarchical) FK-typing – erweitert um:

(1) Tree-Übersicht:
    - tree_hierarchy.txt (Main -> Sub -> Mitglieder)

(2) Gesamt-Heatmap nach hierarchical_cluster sortiert:
    - heatmap_fk_topcodes_hierarchical.png

Ordnerstruktur pro Subset (files_with_6.2.1 / files_with_6.2.2):
  - main_clusters.csv / main_profiles.csv / main_dendrogram.png / main_heatmap.png
  - fk_clusters_hierarchical.csv
  - tree_hierarchy.txt
  - heatmap_fk_topcodes_hierarchical.png
  - sub_main{CID}/ ... (nur für große Main-Cluster)
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


def extract_fachkraft_id(filename: str) -> str:
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
# FK-PROFILE BAUEN
# =============================================================================


def build_fk_code_matrix(
    df: pd.DataFrame,
    exclude_prefixes: Tuple[str, ...] = ("6.1",),
    mode: str = "per_situation_rate",
) -> pd.DataFrame:
    """
    FK × Code Matrix.

    mode:
      - "binary": 0/1 (jemals)
      - "counts": Rohcounts
      - "per_situation_rate": Counts / #Situationen der FK
    """
    df = df.copy()

    def _keep(code: str) -> bool:
        return not any(str(code).startswith(p) for p in exclude_prefixes)

    df = df[df["base_code"].apply(_keep)].copy()
    df = df[df["base_code"].astype(str).str.len() > 0].copy()

    fk_counts = df.groupby(["fachkraft", "base_code"]).size().unstack(fill_value=0)

    if mode == "counts":
        return fk_counts

    if mode == "binary":
        return (fk_counts > 0).astype(int)

    if mode == "per_situation_rate":
        situations_per_fk = df.groupby("fachkraft")["id"].nunique()
        return fk_counts.div(situations_per_fk, axis=0).fillna(0.0)

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


def suggest_cut_distance_by_largest_jump(Z: np.ndarray) -> float:
    d = Z[:, 2]
    if len(d) < 2:
        return float(d[-1]) if len(d) == 1 else 0.0
    jumps = np.diff(d)
    jmax = int(np.argmax(jumps))
    return float((d[jmax] + d[jmax + 1]) / 2.0)


# =============================================================================
# VISUALISIERUNG: HEATMAP (ohne seaborn)
# =============================================================================


def save_heatmap_fk_topcodes(
    X: pd.DataFrame,
    ordered_fks: List[str],
    top_codes: List[str],
    out_path: str,
    title: str,
):
    X_plot = X[top_codes].copy().loc[ordered_fks]

    # z-score pro Code
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
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160)
    plt.close()


# =============================================================================
# PROFILE (Delta + z)
# =============================================================================


def compute_cluster_profiles(
    X: pd.DataFrame,
    clusters: np.ndarray,
    top_codes_for_interpretation: int = 12,
) -> pd.DataFrame:
    X_with_cluster = X.copy()
    X_with_cluster["cluster"] = clusters

    overall_mean = X.mean(axis=0)
    overall_std = X.std(axis=0).replace(0, np.nan)

    rows = []
    for cid in sorted(np.unique(clusters)):
        members = X_with_cluster[X_with_cluster["cluster"] == cid].drop(
            columns=["cluster"]
        )
        mean_vec = members.mean(axis=0)

        delta = mean_vec - overall_mean
        z = (delta / overall_std).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        top_delta = delta.sort_values(ascending=False).head(
            top_codes_for_interpretation
        )
        top_z = z.sort_values(ascending=False).head(top_codes_for_interpretation)

        rows.append(
            {
                "cluster": int(cid),
                "n_fachkraefte": int(len(members)),
                "top_codes_by_delta": ", ".join(
                    [f"{c}({top_delta[c]:.2f})" for c in top_delta.index]
                ),
                "top_codes_by_z": ", ".join(
                    [f"{c}({top_z[c]:.2f})" for c in top_z.index]
                ),
            }
        )

    return pd.DataFrame(rows).sort_values("cluster").reset_index(drop=True)


# =============================================================================
# EIN LEVEL CLUSTERING (Baustein)
# =============================================================================


def cluster_one_level(
    X: pd.DataFrame,
    out_dir: str,
    prefix: str,
    distance_metric: str = "jaccard",
    linkage_method: str = "average",
    cut_k: Optional[int] = None,
    cut_distance: Optional[float] = None,
    top_codes_for_interpretation: int = 12,
    top_codes_for_heatmap: int = 25,
    dendrogram_title: Optional[str] = None,
) -> Dict:
    os.makedirs(out_dir, exist_ok=True)

    dist_vec = compute_distance_matrix(X, metric=distance_metric)
    Z = linkage(dist_vec, method=linkage_method)

    if cut_k is not None:
        clusters = fcluster(Z, t=int(cut_k), criterion="maxclust")
        cut_info = {"type": "k", "value": int(cut_k)}
        color_threshold = None
    else:
        if cut_distance is None:
            cut_distance = suggest_cut_distance_by_largest_jump(Z)
        clusters = fcluster(Z, t=float(cut_distance), criterion="distance")
        cut_info = {"type": "distance", "value": float(cut_distance)}
        color_threshold = float(cut_distance)

    fk_ids = X.index.tolist()
    cluster_df = pd.DataFrame({"fachkraft": fk_ids, "cluster": clusters}).sort_values(
        ["cluster", "fachkraft"]
    )
    cluster_df.to_csv(os.path.join(out_dir, f"{prefix}_clusters.csv"), index=False)

    # Dendrogramm
    plt.figure(figsize=(max(10, len(fk_ids) * 0.4), 6))
    dendrogram(
        Z,
        labels=fk_ids,
        leaf_rotation=90,
        leaf_font_size=8,
        color_threshold=color_threshold,
    )
    title = dendrogram_title or (
        f"Dendrogramm | metric={distance_metric} | linkage={linkage_method} | cut={cut_info['type']}:{cut_info['value']}"
    )
    plt.title(title)
    plt.xlabel("Fachkraft")
    plt.ylabel("Distanz")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, f"{prefix}_dendrogram.png"), dpi=160)
    plt.close()

    # Profiles
    profiles_df = compute_cluster_profiles(
        X, clusters, top_codes_for_interpretation=top_codes_for_interpretation
    )
    profiles_df.to_csv(os.path.join(out_dir, f"{prefix}_profiles.csv"), index=False)

    # Heatmap (TopCodes nach Varianz)
    code_variance = X.var(axis=0).sort_values(ascending=False)
    top_codes = code_variance.head(top_codes_for_heatmap).index.tolist()
    ordered_fks = cluster_df["fachkraft"].tolist()

    save_heatmap_fk_topcodes(
        X=X,
        ordered_fks=ordered_fks,
        top_codes=top_codes,
        out_path=os.path.join(out_dir, f"{prefix}_heatmap.png"),
        title=f"Heatmap: {prefix} (z-scored), nach Cluster sortiert",
    )

    return {
        "X": X,
        "dist_vec": dist_vec,
        "linkage": Z,
        "clusters_df": cluster_df,
        "clusters": clusters,
        "profiles_df": profiles_df,
        "cut": cut_info,
        "top_codes_heatmap": top_codes,
    }


# =============================================================================
# EXTRA OUTPUTS: TREE + HIERARCHY HEATMAP
# =============================================================================


def write_tree_overview(hier_df: pd.DataFrame, out_path: str):
    """
    Tree-Text:
      Main 1 (n=...)
        Sub 1 (n=...): 01, 02, ...
        Sub 2 (n=...): ...
      Main 2 ...
    """
    lines = []
    for mc in sorted(hier_df["main_cluster"].dropna().unique()):
        mc = int(mc)
        df_mc = hier_df[hier_df["main_cluster"] == mc]
        lines.append(f"MAIN {mc} (n={len(df_mc)}):")

        sub_vals = df_mc["sub_cluster"].dropna().unique()
        if len(sub_vals) == 0:
            members = ", ".join(df_mc["fachkraft"].astype(str).tolist())
            lines.append(f"  (kein Subclustering) Mitglieder: {members}")
            lines.append("")
            continue

        for sc in sorted(sub_vals):
            sc = int(sc)
            df_sc = df_mc[df_mc["sub_cluster"] == sc]
            members = ", ".join(df_sc["fachkraft"].astype(str).tolist())
            lines.append(f"  SUB {mc}.{sc} (n={len(df_sc)}): {members}")
        lines.append("")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def save_hierarchical_heatmap(
    X: pd.DataFrame,
    hier_df: pd.DataFrame,
    out_dir: str,
    top_codes_for_heatmap: int = 25,
):
    """
    Eine einzige Heatmap, sortiert nach hierarchical_cluster.
    """
    code_variance = X.var(axis=0).sort_values(ascending=False)
    top_codes = code_variance.head(top_codes_for_heatmap).index.tolist()

    # Sort order: main_cluster, sub_cluster (NaNs last), fachkraft
    df_sort = hier_df.copy()
    df_sort["sub_cluster_sort"] = df_sort["sub_cluster"].fillna(999999).astype(int)
    df_sort = df_sort.sort_values(["main_cluster", "sub_cluster_sort", "fachkraft"])
    ordered_fks = df_sort["fachkraft"].tolist()

    save_heatmap_fk_topcodes(
        X=X,
        ordered_fks=ordered_fks,
        top_codes=top_codes,
        out_path=os.path.join(out_dir, "heatmap_fk_topcodes_hierarchical.png"),
        title="Heatmap: Fachkräfte × TopCodes (z-scored), sortiert nach Main/Sub",
    )


# =============================================================================
# TWO-LEVEL CLUSTERING
# =============================================================================


def two_level_cluster_fachkraefte(
    X: pd.DataFrame,
    out_dir: str,
    distance_metric: str = "jaccard",
    linkage_method: str = "average",
    main_cut_k: Optional[int] = None,
    main_cut_distance: Optional[float] = None,
    sub_cut_k: Optional[int] = None,
    sub_cut_distance: Optional[float] = None,
    min_size_for_subclustering: int = 8,
    max_subclusters_cap: Optional[int] = None,
    top_codes_for_interpretation: int = 12,
    top_codes_for_heatmap: int = 25,
) -> Dict:
    os.makedirs(out_dir, exist_ok=True)

    # -----------------------------
    # Level 1: Main
    # -----------------------------
    main_res = cluster_one_level(
        X=X,
        out_dir=out_dir,
        prefix="main",
        distance_metric=distance_metric,
        linkage_method=linkage_method,
        cut_k=main_cut_k,
        cut_distance=main_cut_distance,
        top_codes_for_interpretation=top_codes_for_interpretation,
        top_codes_for_heatmap=top_codes_for_heatmap,
        dendrogram_title="Dendrogramm (MAIN): Fachkräfte",
    )

    main_df = main_res["clusters_df"].rename(columns={"cluster": "main_cluster"}).copy()
    main_df["sub_cluster"] = pd.NA
    main_df["hierarchical_cluster"] = main_df["main_cluster"].astype(str)

    sub_results = {}
    main_sizes = main_df["main_cluster"].value_counts().sort_index()

    # -----------------------------
    # Level 2: Subclustering je großem Main-Cluster
    # -----------------------------
    for mc, size in main_sizes.items():
        mc = int(mc)
        size = int(size)

        if size < min_size_for_subclustering:
            continue

        members = main_df.loc[main_df["main_cluster"] == mc, "fachkraft"].tolist()
        if len(members) < 2:
            continue

        X_sub = X.loc[members].copy()
        if X_sub.shape[0] < 2:
            continue

        eff_sub_cut_k = sub_cut_k
        if eff_sub_cut_k is not None:
            if max_subclusters_cap is not None:
                eff_sub_cut_k = int(min(eff_sub_cut_k, max_subclusters_cap))
            eff_sub_cut_k = int(min(eff_sub_cut_k, X_sub.shape[0]))
            if eff_sub_cut_k < 2:
                continue

        sub_dir = os.path.join(out_dir, f"sub_main{mc}")
        os.makedirs(sub_dir, exist_ok=True)

        sub_res = cluster_one_level(
            X=X_sub,
            out_dir=sub_dir,
            prefix=f"sub_main{mc}",
            distance_metric=distance_metric,
            linkage_method=linkage_method,
            cut_k=eff_sub_cut_k,
            cut_distance=sub_cut_distance,
            top_codes_for_interpretation=top_codes_for_interpretation,
            top_codes_for_heatmap=top_codes_for_heatmap,
            dendrogram_title=f"Dendrogramm (SUB): Main-Cluster {mc}",
        )

        sub_df = (
            sub_res["clusters_df"].rename(columns={"cluster": "sub_cluster"}).copy()
        )
        sub_df["sub_cluster"] = sub_df["sub_cluster"].astype(int)

        # Merge zurück
        main_df = main_df.merge(
            sub_df, on="fachkraft", how="left", suffixes=("", "_new")
        )
        mask = main_df["sub_cluster_new"].notna()
        main_df.loc[mask, "sub_cluster"] = main_df.loc[mask, "sub_cluster_new"].astype(
            int
        )
        main_df = main_df.drop(columns=["sub_cluster_new"])

        # Hierarchischer Label
        main_df["hierarchical_cluster"] = main_df.apply(
            lambda r: f"{int(r['main_cluster'])}.{int(r['sub_cluster'])}"
            if pd.notna(r["sub_cluster"])
            else f"{int(r['main_cluster'])}",
            axis=1,
        )

        sub_results[mc] = {"sub_dir": sub_dir, **sub_res}

    # -----------------------------
    # Export hierarchische Zuordnung
    # -----------------------------
    main_df = main_df.sort_values(
        ["main_cluster", "sub_cluster", "fachkraft"], na_position="last"
    )
    main_df.to_csv(os.path.join(out_dir, "fk_clusters_hierarchical.csv"), index=False)

    # -----------------------------
    # Zusatzoutputs: Tree + Gesamt-Heatmap
    # -----------------------------
    write_tree_overview(main_df, os.path.join(out_dir, "tree_hierarchy.txt"))
    save_hierarchical_heatmap(X, main_df, out_dir, top_codes_for_heatmap=25)

    return {
        "main": main_res,
        "hierarchical_assignments": main_df,
        "sub_results": sub_results,
    }


# =============================================================================
# PIPELINE: Zwei Subsets (6.2.1 vs 6.2.2)
# =============================================================================


def filter_df_by_files_containing_code(
    df: pd.DataFrame, target_code: str
) -> pd.DataFrame:
    files = df.loc[df["base_code"] == target_code, "Filename"].unique()
    return df[df["Filename"].isin(files)].copy()


def run_fk_typing_pipeline_two_level(
    csv_path: str,
    output_root: str = "fk_typing_reports_two_level",
    fk_matrix_mode: str = "binary",
    distance_metric: str = "jaccard",
    linkage_method: str = "average",
    # MAIN cut
    main_cut_k: Optional[int] = None,
    main_cut_distance: Optional[float] = None,
    # SUB cut
    sub_cut_k: Optional[int] = 3,
    sub_cut_distance: Optional[float] = None,
    # Regeln
    min_size_for_subclustering: int = 8,
    max_subclusters_cap: Optional[int] = 6,
):
    os.makedirs(output_root, exist_ok=True)
    df_all = load_and_prepare_data(csv_path)

    for code in ["6.2.1", "6.2.2"]:
        df_sub = filter_df_by_files_containing_code(df_all, code)
        out_dir = os.path.join(output_root, f"files_with_{code}")

        print(f"\n=== TWO-LEVEL FK-Typing für Dateien mit {code} ===")
        print(
            f"Rows: {len(df_sub)} | Filenames: {df_sub['Filename'].nunique()} | FKs: {df_sub['fachkraft'].nunique()}"
        )

        X = build_fk_code_matrix(df_sub, exclude_prefixes=("6.1",), mode=fk_matrix_mode)

        if X.shape[0] < 2:
            print("Zu wenige Fachkräfte für Clustering in diesem Subset.")
            continue

        res = two_level_cluster_fachkraefte(
            X=X,
            out_dir=out_dir,
            distance_metric=distance_metric,
            linkage_method=linkage_method,
            main_cut_k=main_cut_k,
            main_cut_distance=main_cut_distance,
            sub_cut_k=sub_cut_k,
            sub_cut_distance=sub_cut_distance,
            min_size_for_subclustering=min_size_for_subclustering,
            max_subclusters_cap=max_subclusters_cap,
            top_codes_for_interpretation=12,
            top_codes_for_heatmap=25,
        )

        print(f"Saved outputs to: {out_dir}")
        print(f"MAIN cut used: {res['main']['cut']}")
        print(
            "Wrote: fk_clusters_hierarchical.csv, tree_hierarchy.txt, heatmap_fk_topcodes_hierarchical.png"
        )


# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    run_fk_typing_pipeline_two_level(
        csv_path="extracted_sequences.csv",
        output_root="fk_typing_reports_two_level",
        fk_matrix_mode="binary",
        distance_metric="jaccard",
        linkage_method="average",
        main_cut_k=2,  # 2 Hauptcluster erzwingen
        main_cut_distance=None,
        sub_cut_k=3,  # Untercluster im großen Cluster
        sub_cut_distance=None,  # auto (largest jump) pro Sub-Cluster
        min_size_for_subclustering=8,  # nur "große" main clusters werden gesplittet
        max_subclusters_cap=6,
    )
