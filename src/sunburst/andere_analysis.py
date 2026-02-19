#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyze PLACEHOLDER_OTHER ("Andere") occurrences in each ring.
Identify which codes are present but not selected for each ring.
"""

from typing import Dict, Literal
import pandas as pd
from src.sunburst.code_util import CodeUtil

code_util = CodeUtil()


def analyze_andere_by_ring(per_path_df: pd.DataFrame) -> pd.DataFrame:
    """
    Count how many times "Andere" appears in each ring.

    Returns DataFrame with columns:
    - Ring: innen, mitte, aussen, aussenring
    - Andere_Count: Number of occurrences
    - Total_Paths: Total paths analyzed
    - Percentage: Percentage of paths with "Andere" in this ring
    """
    token_columns = {
        "innen": "innen_token",
        "mitte": "mitte_token",
        "aussen": "aussen_token",
        "aussenring": "aussenring_token",
    }

    analysis_rows = []
    for ring, col in token_columns.items():
        # Count total paths
        total = len(per_path_df)

        # Count paths where this ring contains "Andere"
        # Note: token columns store strings like "[\'Andere\']", so we check for the placeholder
        andere_count = (
            per_path_df[col].str.contains(code_util.PLACEHOLDER_OTHER, na=False).sum()
        )

        percentage = (andere_count / total * 100) if total > 0 else 0

        analysis_rows.append(
            {
                "Ring": ring,
                "Andere_Count": andere_count,
                "Total_Paths": total,
                "Percentage": f"{percentage:.1f}%",
            }
        )

    return pd.DataFrame(analysis_rows)


def analyze_codes_causing_andere(
    df: pd.DataFrame,
    per_path_df: pd.DataFrame,
    start_lookahead_n: int = 12,
    combo_time_match_mode: Literal["exact", "overlap"] = "exact",
) -> pd.DataFrame:
    """
    For each ring, identify what codes were present in bundles
    that resulted in "Andere" selection.
    """
    from src.sunburst.helper import normalize_code, parse_time_to_seconds, build_time_bundles

    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    d = d[d["code"].isin(code_util.ALLOWED_CODES)].copy()

    group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]

    analysis_rows = []

    for key, g in d.groupby(group_cols, sort=True):
        if isinstance(key, tuple):
            filename, pid = key
        else:
            filename, pid = key, ""

        # Find corresponding row in per_path_df
        path_row = per_path_df[
            (per_path_df["Filename"] == filename) & (per_path_df["id"] == pid)
        ]

        if path_row.empty:
            continue

        # Sort by time
        g_sorted = g.copy()
        g_sorted["code_priority"] = g_sorted["code"].map(
            lambda c: code_util.CODE_TO_PRIO.get(c, (999, 999))
        )
        g_sorted = g_sorted.sort_values(by=["start_s", "end_s", "code_priority"]).drop(
            "code_priority", axis=1
        )

        # Group by bundles in the same mode used for path building
        bundles = []
        for bundle_group in build_time_bundles(
            g_sorted, combo_time_match_mode=combo_time_match_mode
        ):
            bundles.append(
                {
                    "start_s": float(bundle_group["start_s"].min()),
                    "end_s": float(bundle_group["end_s"].max()),
                    "codes": bundle_group["code"].tolist(),
                }
            )

        bundles.sort(key=lambda b: (b["start_s"], b["end_s"]))

        n_bundles = len(bundles)
        if n_bundles == 0:
            continue

        bundles = bundles[: max(4, start_lookahead_n)]
        n_bundles = len(bundles)

        # Split into 4 rings
        base = n_bundles // 4
        rem = n_bundles % 4
        sizes = [base + (1 if i < rem else 0) for i in range(4)]

        ring_bundles = [[], [], [], []]
        idx0 = 0
        for ring_idx, sz in enumerate(sizes):
            for bundle in bundles[idx0 : idx0 + sz]:
                ring_bundles[ring_idx].extend(bundle["codes"])
            idx0 += sz

        # Check which rings have "Andere"
        ring_names = ["innen", "mitte", "aussen", "aussenring"]
        token_columns = [
            "innen_token",
            "mitte_token",
            "aussen_token",
            "aussenring_token",
        ]

        for ring_idx, (ring_name, token_col, codes_in_ring) in enumerate(
            zip(ring_names, token_columns, ring_bundles)
        ):
            # Check if this ring has "Andere"
            token_value = path_row[token_col]
            if code_util.PLACEHOLDER_OTHER in str(token_value):
                # This ring selected "Andere" - record what codes were available
                for code in codes_in_ring:
                    analysis_rows.append(
                        {
                            "Ring": ring_name,
                            "Code": code,
                            "Label": code_util.LABEL_MAP.get(code, code),
                            "Available_In_Andere_Cases": 1,
                        }
                    )

    # Aggregate to count occurrences using groupby and sum [1][3]
    if analysis_rows:
        result_df = pd.DataFrame(analysis_rows)
        # Use groupby() with agg() for cleaner aggregation
        aggregated = (
            result_df.groupby(["Ring", "Code", "Label"])["Available_In_Andere_Cases"]
            .sum()
            .reset_index(name="Count")
        )
        aggregated = aggregated.sort_values(["Ring", "Count"], ascending=[True, False])
        return aggregated
    else:
        return pd.DataFrame()


def create_andere_summary(
    andere_by_ring: pd.DataFrame, codes_causing_andere: pd.DataFrame
) -> Dict[str, pd.DataFrame]:
    """
    Create comprehensive summary of "Andere" occurrences.

    Returns dictionary with:
    - "summary": Overview table by ring
    - "codes": Detailed codes present in "Andere" cases
    """
    return {
        "summary": andere_by_ring,
        "codes": codes_causing_andere,
    }


def print_andere_report(summary_dict: Dict[str, pd.DataFrame]):
    """Pretty-print the "Andere" analysis report."""
    print("\n" + "=" * 80)
    print("ANALYSE: 'Andere' (PLACEHOLDER_OTHER) NACH RING")
    print("=" * 80)

    print("\n[1] ZUSAMMENFASSUNG PRO RING:")
    print("-" * 80)
    print(summary_dict["summary"].to_string(index=False))

    print("\n\n[2] VERFÜGBARE CODES BEI 'Andere'-SELEKTION:")
    print("-" * 80)
    if not summary_dict["codes"].empty:
        # Group by ring for better readability
        for ring in ["innen", "mitte", "aussen", "aussenring"]:
            ring_data = summary_dict["codes"][summary_dict["codes"]["Ring"] == ring]
            if not ring_data.empty:
                print(f"\n{ring.upper()}:")
                print(ring_data[["Code", "Label", "Count"]].to_string(index=False))
    else:
        print("(Keine Daten verfügbar)")

    print("\n" + "=" * 80 + "\n")
