from typing import Tuple, List
import pandas as pd
from itertools import combinations
from src.sunburst.helper import normalize_code, parse_time_to_seconds
from src.sunburst.code_util import CodeUtil


def analyze_code_cooccurrences(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Analyze temporal co-occurrences of codes at arbitrary lengths.
    Preserves Filename for source tracking.

    Returns two tables:
    1. All pairwise combinations (for backward compatibility)
    2. All temporal bundles (complete groups of codes)
    """
    code_util = CodeUtil()
    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    d = d[d["code"].isin(code_util.ALLOWED_CODES)].copy()

    # ===== CO-OCCURRENCE: Complete Bundles (All codes at same window) =====
    bundle_records = []

    # Group by Filename AND time window to preserve file origin[1]
    for (filename, start_time, end_time), group in d.groupby(["Filename", "start_s", "end_s"]):
        codes_in_window = sorted(group["code"].unique().tolist())

        if len(codes_in_window) > 1:
            bundle_key = " + ".join(codes_in_window)
            labels = [code_util.LABEL_MAP.get(c, c) for c in codes_in_window]
            bundle_label = " + ".join(labels)

            bundle_records.append({
                "Filename": filename,  # ADD: Source file
                "bundle_key": bundle_key,
                "bundle_label": bundle_label,
                "num_codes": len(codes_in_window),
                "codes": codes_in_window,
                "start_time": start_time,
                "end_time": end_time,
                "duration": end_time - start_time,
            })

    # Create DataFrame and aggregate by bundle (excluding Filename from groupby)[4]
    bundles_df = pd.DataFrame(bundle_records)

    if not bundles_df.empty:
        # Group by bundle characteristics but keep Filename info[1]
        bundle_counts = (
            bundles_df.groupby(["bundle_key", "bundle_label", "num_codes"], as_index=False)
            .agg({
                "duration": ["mean", "min", "max"],
                "start_time": "count",
                "Filename": lambda x: list(x.unique())  # Collect unique filenames
            })
            .reset_index(drop=True)
        )

        # Flatten column names
        bundle_counts.columns = [
            "bundle_key",
            "bundle_label",
            "num_codes",
            "avg_duration",
            "min_duration",
            "max_duration",
            "count",
            "source_filenames",
        ]

        # Create a string representation of filenames for easier viewing
        bundle_counts["source_files"] = bundle_counts["source_filenames"].apply(
            lambda x: ", ".join(sorted(x))
        )

        bundle_counts = bundle_counts.sort_values("count", ascending=False)
    else:
        bundle_counts = pd.DataFrame()

    # ===== BACKWARD COMPATIBILITY: Generate pairwise combinations =====
    pair_records = []

    for _, row in bundles_df.iterrows():
        codes = row["codes"]
        for code1, code2 in combinations(codes, 2):
            pair_records.append({
                "Filename": row["Filename"],  # ADD: Source file
                "code1": code1,
                "label1": code_util.LABEL_MAP.get(code1, code1),
                "code2": code2,
                "label2": code_util.LABEL_MAP.get(code2, code2),
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "duration": row["duration"],
            })

    pairs_df = pd.DataFrame(pair_records)

    if not pairs_df.empty:
        pair_counts = (
            pairs_df.groupby(["code1", "label1", "code2", "label2"], as_index=False)
            .agg({
                "duration": ["mean", "min", "max"],
                "start_time": "count",
                "Filename": lambda x: list(x.unique())  # Collect unique filenames
            })
            .reset_index(drop=True)
        )

        # Flatten column names
        pair_counts.columns = [
            "code1",
            "label1",
            "code2",
            "label2",
            "avg_duration",
            "min_duration",
            "max_duration",
            "count",
            "source_filenames",
        ]

        # Create a string representation of filenames
        pair_counts["source_files"] = pair_counts["source_filenames"].apply(
            lambda x: ", ".join(sorted(x))
        )

        pair_counts = pair_counts.sort_values("count", ascending=False)
    else:
        pair_counts = pd.DataFrame()

    return pair_counts, bundle_counts


def create_cooccurrence_summary(
        pair_df: pd.DataFrame, bundle_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Create summary of all co-occurring code groups, ranked by frequency.
    Includes source filename information.
    """
    summary_rows = []

    # Add pairwise co-occurrences
    if not pair_df.empty:
        for _, row in pair_df.iterrows():
            summary_rows.append({
                "Group": f"{row['code1']} ↔ {row['code2']}",
                "Num_Codes": 2,
                "Codes": [row["code1"], row["code2"]],
                "Labels": f"{row['label1']} + {row['label2']}",
                "Avg_Duration": row["avg_duration"],
                "Count": int(row["count"]),
                "Group_Type": "Pair",
                "Source_Files": row.get("source_files", ""),  # ADD: Source files
            })

    # Add larger bundles
    if not bundle_df.empty:
        for _, row in bundle_df.iterrows():
            summary_rows.append({
                "Group": row["bundle_key"],
                "Num_Codes": int(row["num_codes"]),
                "Codes": row["bundle_key"].split(" + "),
                "Labels": row["bundle_label"],
                "Avg_Duration": row["avg_duration"],
                "Count": int(row["count"]),
                "Group_Type": f"{int(row['num_codes'])}-Tuple",
                "Source_Files": row.get("source_files", ""),  # ADD: Source files
            })

    result = pd.DataFrame(summary_rows)
    return result.sort_values(["Num_Codes", "Count"], ascending=[False, False])