from typing import Tuple

import pandas as pd

from src.sunburst.helper import normalize_code, parse_time_to_seconds
from src.sunburst.context import AnalysisContext, get_default_context


def _ordered_pair(
    code1: str, code2: str, context: AnalysisContext | None = None
) -> tuple[str, str]:
    ctx = context if context is not None else get_default_context()

    def _key(c: str) -> tuple[int, int, str]:
        pr = ctx.code_to_prio.get(c, (999, 999))
        return (pr[0], pr[1], c)

    return tuple(sorted((code1, code2), key=_key))


def analyze_code_cooccurrences(
    df: pd.DataFrame, context: AnalysisContext | None = None
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Analyze temporal co-occurrences of codes.
    Returns two tables:
    1. Codes starting at same time
    2. Codes with identical (start_s, end_s) windows
    """
    ctx = context if context is not None else get_default_context()
    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    d = d[d["code"].isin(ctx.allowed_codes)].copy()

    # ===== CO-OCCURRENCE 1: Same Start Time =====
    same_start_pairs = []
    for (_filename, start_time), group in d.groupby(["Filename", "start_s"]):
        codes_at_time = group["code"].unique()
        if len(codes_at_time) > 1:
            # Generate all pairs
            for i, code1 in enumerate(codes_at_time):
                for code2 in codes_at_time[i + 1 :]:
                    left, right = _ordered_pair(code1, code2, context=ctx)
                    same_start_pairs.append(
                        {
                            "code1": left,
                            "label1": ctx.label_map.get(left, left),
                            "code2": right,
                            "label2": ctx.label_map.get(right, right),
                            "start_time": start_time,
                            "cooccurrence_type": "Same Start Time",
                        }
                    )

    same_start_df = pd.DataFrame(same_start_pairs)
    if not same_start_df.empty:
        same_start_counts = (
            same_start_df.groupby(["code1", "label1", "code2", "label2"])
            .size()
            .reset_index(name="count")
            .sort_values("count", ascending=False)
        )
    else:
        same_start_counts = pd.DataFrame()

    # ===== CO-OCCURRENCE 2: Same Start AND End Time (Exact Bundles) =====
    same_window_pairs = []
    for (_filename, start_time, end_time), group in d.groupby(
        ["Filename", "start_s", "end_s"]
    ):
        codes_in_window = group["code"].unique()
        if len(codes_in_window) > 1:
            for i, code1 in enumerate(codes_in_window):
                for code2 in codes_in_window[i + 1 :]:
                    left, right = _ordered_pair(code1, code2, context=ctx)
                    same_window_pairs.append(
                        {
                            "code1": left,
                            "label1": ctx.label_map.get(left, left),
                            "code2": right,
                            "label2": ctx.label_map.get(right, right),
                            "start_time": start_time,
                            "end_time": end_time,
                            "duration": end_time - start_time,
                            "cooccurrence_type": "Same Start & End Time",
                        }
                    )

    same_window_df = pd.DataFrame(same_window_pairs)
    if not same_window_df.empty:
        same_window_counts = (
            same_window_df.groupby(["code1", "label1", "code2", "label2"])
            .agg({"duration": ["mean", "min", "max"], "start_time": "count"})
            .reset_index()
        )
        same_window_counts.columns = [
            "code1",
            "label1",
            "code2",
            "label2",
            "avg_duration",
            "min_duration",
            "max_duration",
            "count",
        ]
        same_window_counts = same_window_counts.sort_values("count", ascending=False)
    else:
        same_window_counts = pd.DataFrame()

    return same_start_counts, same_window_counts


def create_cooccurrence_summary(
    same_start_df: pd.DataFrame, same_window_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Create a summary table of all unique co-occurring pairs with frequency.
    """
    summary_rows = []

    # From same start time
    if not same_start_df.empty:
        for _, row in same_start_df.iterrows():
            summary_rows.append(
                {
                    "Code_Pair": f"{row['code1']} ↔ {row['code2']}",
                    "Code1": row["code1"],
                    "Code2": row["code2"],
                    "Label1": row["label1"],
                    "Label2": row["label2"],
                    "Same_Start_Count": row["count"],
                    "Same_Window_Count": 0,
                    "Cooccurrence_Type": "Same Start Time Only",
                }
            )

    # From same window (update counts if pairs already exist)
    if not same_window_df.empty:
        existing_pairs = {
            f"{row['Code1']} ↔ {row['Code2']}": idx
            for idx, row in enumerate(summary_rows)
        }
        for _, row in same_window_df.iterrows():
            pair_key = f"{row['code1']} ↔ {row['code2']}"
            if pair_key in existing_pairs:
                idx = existing_pairs[pair_key]
                summary_rows[idx]["Same_Window_Count"] = int(row["count"])
                summary_rows[idx]["Cooccurrence_Type"] = "Both Same Start & Window"
            else:
                summary_rows.append(
                    {
                        "Code_Pair": pair_key,
                        "Code1": row["code1"],
                        "Code2": row["code2"],
                        "Label1": row["label1"],
                        "Label2": row["label2"],
                        "Same_Start_Count": 0,
                        "Same_Window_Count": int(row["count"]),
                        "Cooccurrence_Type": "Same Window Only",
                    }
                )

    return pd.DataFrame(summary_rows).sort_values("Same_Window_Count", ascending=False)
