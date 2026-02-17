from typing import Tuple, List
import pandas as pd
from itertools import combinations
from src.sunburst.helper import normalize_code, parse_time_to_seconds
from src.sunburst.code_util import CodeUtil


def analyze_code_cooccurrences(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Analyze temporal co-occurrences of codes at arbitrary lengths.

    Returns two tables:
    1. All pairwise combinations (for backward compatibility)
    2. All temporal bundles (complete groups of codes)
    """
    # Get singleton instance
    code_util = CodeUtil()

    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    # Use singleton's ALLOWED_CODES
    d = d[d["code"].isin(code_util.ALLOWED_CODES)].copy()

    # ===== CO-OCCURRENCE: Complete Bundles (All codes at same window) =====
    bundle_records = []

    for (start_time, end_time), group in d.groupby(["start_s", "end_s"]):
        codes_in_window = sorted(group["code"].unique().tolist())

        if len(codes_in_window) > 1:
            # Create bundle identifier (all codes together)
            bundle_key = " + ".join(codes_in_window)
            # Use singleton's LABEL_MAP
            labels = [code_util.LABEL_MAP.get(c, c) for c in codes_in_window]
            bundle_label = " + ".join(labels)

            bundle_records.append(
                {
                    "bundle_key": bundle_key,
                    "bundle_label": bundle_label,
                    "num_codes": len(codes_in_window),
                    "codes": codes_in_window,
                    "start_time": start_time,
                    "end_time": end_time,
                    "duration": end_time - start_time,
                }
            )

    # Create DataFrame and aggregate by bundle
    bundles_df = pd.DataFrame(bundle_records)

    if not bundles_df.empty:
        bundle_counts = (
            bundles_df.groupby(["bundle_key", "bundle_label", "num_codes"])
            .agg({"duration": ["mean", "min", "max"], "start_time": "count"})
            .reset_index()
        )
        bundle_counts.columns = [
            "bundle_key",
            "bundle_label",
            "num_codes",
            "avg_duration",
            "min_duration",
            "max_duration",
            "count",
        ]
        bundle_counts = bundle_counts.sort_values("count", ascending=False)
    else:
        bundle_counts = pd.DataFrame()

    # ===== BACKWARD COMPATIBILITY: Generate pairwise combinations =====
    pair_records = []
    for _, row in bundles_df.iterrows():
        codes = row["codes"]
        for code1, code2 in combinations(codes, 2):
            pair_records.append(
                {
                    "code1": code1,
                    "label1": code_util.LABEL_MAP.get(code1, code1),
                    "code2": code2,
                    "label2": code_util.LABEL_MAP.get(code2, code2),
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "duration": row["duration"],
                }
            )

    pairs_df = pd.DataFrame(pair_records)

    if not pairs_df.empty:
        pair_counts = (
            pairs_df.groupby(["code1", "label1", "code2", "label2"])
            .agg({"duration": ["mean", "min", "max"], "start_time": "count"})
            .reset_index()
        )
        pair_counts.columns = [
            "code1",
            "label1",
            "code2",
            "label2",
            "avg_duration",
            "min_duration",
            "max_duration",
            "count",
        ]
        pair_counts = pair_counts.sort_values("count", ascending=False)
    else:
        pair_counts = pd.DataFrame()

    return pair_counts, bundle_counts


def create_cooccurrence_summary(
    pair_df: pd.DataFrame, bundle_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Create summary of all co-occurring code groups, ranked by frequency.
    """
    summary_rows = []

    # Add pairwise co-occurrences
    if not pair_df.empty:
        for _, row in pair_df.iterrows():
            summary_rows.append(
                {
                    "Group": f"{row['code1']} ↔ {row['code2']}",
                    "Num_Codes": 2,
                    "Codes": [row["code1"], row["code2"]],
                    "Labels": f"{row['label1']} + {row['label2']}",
                    "Avg_Duration": row["avg_duration"],
                    "Count": int(row["count"]),
                    "Group_Type": "Pair",
                }
            )

    # Add larger bundles
    if not bundle_df.empty:
        for _, row in bundle_df.iterrows():
            summary_rows.append(
                {
                    "Group": row["bundle_key"],
                    "Num_Codes": int(row["num_codes"]),
                    "Codes": row["bundle_key"].split(" + "),
                    "Labels": row["bundle_label"],
                    "Avg_Duration": row["avg_duration"],
                    "Count": int(row["count"]),
                    "Group_Type": f"{int(row['num_codes'])}-Tuple",
                }
            )

    result = pd.DataFrame(summary_rows)
    return result.sort_values(["Num_Codes", "Count"], ascending=[False, False])


def generate_combo_rules_from_bundles(
    bundle_df: pd.DataFrame, min_count: int = 5
) -> List[Tuple]:
    """
    Generate combo rules (for merging) from frequently occurring bundles.
    Only bundles with count >= min_count become rules.

    Returns list of (tuple_of_codes, label, count)
    """
    code_util = CodeUtil()
    rules = []

    if bundle_df.empty:
        return rules

    # Filter by minimum count
    significant_bundles = bundle_df[bundle_df["count"] >= min_count]

    for _, row in significant_bundles.iterrows():
        codes = row["bundle_key"].split(" + ")
        codes_tuple = tuple(
            sorted(codes, key=lambda c: code_util.CODE_TO_PRIO.get(c, (999, 999)))
        )
        label = row["bundle_label"]
        count = int(row["count"])

        rules.append((codes_tuple, label, count))

    return sorted(rules, key=lambda x: x[2], reverse=True)
