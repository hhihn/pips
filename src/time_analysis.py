import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt
import re


# ---------------------- helpers ----------------------
def map_code_to_name(code: str) -> str:
    mapping = {
        "5.3.1": "FK spricht mit K",
        "2.2.1.2": "Körperkontakt",
        "2.1.3.1": "FK führt Hdlg. für K aus",
        "5.2": "Kindlicher Widerstand",
        "6.4.1": "FK fordert K zu Hdlg. auf",
        "6.5.3": "K führt Hdlg. aus",
        "2.1.3.2": "Gemeinsame Hdlg.",
        "2.1.3.4": "FK macht Hdlg. vor",
    }
    return mapping.get(code, code)


def parse_time_to_seconds(t: str) -> float:
    """Convert '0:00:29,6' → seconds."""
    if pd.isna(t) or not isinstance(t, str):
        return 0.0
    t = t.strip().replace(",", ".")
    parts = t.split(":")
    try:
        if len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
        return float(parts[0])
    except ValueError:
        return 0.0


def extract_code_prefix(code: str, level: int | None = None) -> str:
    """
    Extract prefix up to given dot-level:
        level=1 -> '2'
        level=2 -> '2.1'
        level=3 -> '2.1.1'
        level=None or high -> full code.
    """
    if not isinstance(code, str):
        return "OTHER"
    parts = re.findall(r"\d+", code)
    if not parts:
        return "OTHER"
    if level is None or level >= len(parts):
        return ".".join(parts)
    return ".".join(parts[:level])


def group_codes(code):
    if code == "5.2.2" or code == "5.2.1":
        return "5.2"
    return code


# ---------------------- core analysis ----------------------
def compute_relative_lengths_within_6_1_1(
    csv_path: str,
    grouping_level: int = 2,
    export_plots: bool = True,
    target_window_code="2.1.1.1",
    exclude_codes: list[str] = None,
    aggregate_codes: list[str] = None,
):
    """
    Compute relative durations of all codes within each 6.1.1 window,
    drop codes where all relative_len==1, then group by code prefix of chosen level.

    Args:
        csv_path: input CSV path
        grouping_level: how many levels of code hierarchy to group by (1,2,3,...)
        export_plots: write PNGs
    """
    df = pd.read_csv(csv_path)
    for c in ["Filename", "Sequence_Code", "Sequence_Start", "Sequence_End", "id"]:
        if c not in df.columns:
            raise ValueError(f"Missing column {c}")
    df.drop(df[df["Sequence_Code"].str.contains(" AK")].index, inplace=True)
    df["Extracted_Codes"] = df["Sequence_Code"].apply(extract_code_prefix)
    if exclude_codes:
        df.drop(df[df["Extracted_Codes"].isin(exclude_codes)].index, inplace=True)
    df["Extracted_Codes"] = df["Extracted_Codes"].apply(group_codes)
    df["Extracted_Codes_Labels"] = df["Extracted_Codes"].apply(map_code_to_name)
    # convert times
    df["start_sec"] = df["Sequence_Start"].apply(parse_time_to_seconds)
    df["end_sec"] = df["Sequence_End"].apply(parse_time_to_seconds)
    df["duration"] = df["end_sec"] - df["start_sec"]
    # ---- remove groups with fewer than n_min observations ----
    n_min = 2
    group_sizes = df.groupby("Sequence_Code").size()
    valid_groups = group_sizes[group_sizes >= n_min].index

    removed = len(group_sizes) - len(valid_groups)
    df = df[df["Sequence_Code"].isin(valid_groups)]

    print(f"Removed {removed} groups with < {n_min} observations.")
    results = []

    # ---- compute relative length per 6.1.1 window ----
    for (fname, fid), sub in df.groupby(["Filename", "id"]):
        six_rows = sub[sub["Extracted_Codes"] == target_window_code]
        if six_rows.empty:
            continue
        for _, win in six_rows.iterrows():
            wstart, wend = win["start_sec"], win["end_sec"]
            wlen = wend - wstart
            if wlen <= 0:
                continue
            inside = sub[(sub["start_sec"] >= wstart) & (sub["end_sec"] <= wend)].copy()
            if inside.empty:
                continue
            inside["id"] = fid
            inside["Filename"] = fname
            inside["Win_length"] = wlen

            # --- split into aggregated vs non-aggregated codes ---
            to_aggregate = inside[inside["Extracted_Codes"].isin(aggregate_codes)]
            to_keep = inside[~inside["Extracted_Codes"].isin(aggregate_codes)]

            aggregated_rows = []

            if not to_aggregate.empty:
                print("aggregating", to_aggregate)
                summed = to_aggregate.groupby("Extracted_Codes", as_index=False).agg(
                    {
                        "duration": "sum",
                        "id": "first",
                        "Filename": "first",
                        "Win_length": "first",
                        "Extracted_Codes_Labels": "first",
                    }
                )
                print("summed", summed)
                summed["relative_len"] = summed["duration"] / wlen
                aggregated_rows.append(summed)

            # --- keep non-aggregated codes unchanged ---
            if not to_keep.empty:
                to_keep = to_keep.copy()
                to_keep["relative_len"] = to_keep["duration"] / wlen
                aggregated_rows.append(to_keep)

            # --- collect results ---
            if aggregated_rows:
                results.append(pd.concat(aggregated_rows, ignore_index=True))
    print(results)
    if not results:
        print(f"No valid {target_window_code} windows.")
        return None

    all_rel = pd.concat(results, ignore_index=True)

    # ---- exclude codes whose all measurements ==1 ----
    code_all_one = (
        all_rel.groupby("Extracted_Codes")["relative_len"]
        .apply(lambda x: (x == 1).all())
        .reset_index(name="all_one")
    )
    full_codes = set(code_all_one[code_all_one["all_one"]]["Extracted_Codes"])
    all_rel = all_rel[~all_rel["Extracted_Codes"].isin(full_codes)]
    print(f"Removed {len(full_codes)} codes where all lengths ==1.")

    # ---- add hierarchical grouping key ----
    all_rel["GroupKey"] = all_rel["Extracted_Codes"].apply(
        lambda c: extract_code_prefix(c, grouping_level)
    )

    # ---- summaries ----
    per_id_summary = (
        all_rel.groupby(["id", "GroupKey"])["relative_len"]
        .mean()
        .reset_index(name="avg_relative_len")
    )
    total_summary = (
        all_rel.groupby("GroupKey")["relative_len"]
        .mean()
        .reset_index(name="overall_avg_relative_len")
    )

    # ------------------------------------------------------------------
    # Plotting
    # ------------------------------------------------------------------
    sns.set_theme(style="whitegrid", font="DejaVu Sans", context="talk")

    # Compute sorting order by median (ascending)
    median_order = (
        all_rel.groupby("GroupKey")["relative_len"]
        .median()
        .sort_values(ascending=True)
        .index.tolist()
    )

    # Barplot – Avg by Group (for reference)
    plt.figure(figsize=(14, 6))

    # counts per group
    all_rel.groupby("GroupKey").size().reindex(total_summary["GroupKey"])

    sns.barplot(
        data=total_summary,
        y="GroupKey",
        x="overall_avg_relative_len",
        color="steelblue",
    )

    # annotate counts on bars
    # for i, (value, count) in enumerate(
    #     zip(total_summary["overall_avg_relative_len"], group_counts)
    # ):
    #     ax.text(
    #         x=value,
    #         y=i,
    #         s=f"n={count}",
    #         va="center",
    #         ha="left",
    #         fontsize=11,
    #         color="black",
    #     )

    # plt.title(f"Average Relative Length by Code Level {grouping_level}")
    # plt.xlabel(f"Average Fraction of {target_window_code} Interval")
    # plt.ylabel(f"Code Group (Level {grouping_level})")

    # rotate y-axis labels if needed (optional)
    plt.tight_layout()

    if export_plots:
        plt.savefig(f"avg_relative_len_level{grouping_level}.png", dpi=300)
    plt.show()

    # --------------------------------------------------------------
    # Boxplot – distribution, sorted by ascending median
    # --------------------------------------------------------------
    plot_dist(
        all_rel,
        median_order,
        grouping_level,
        export_plots=True,
        target_window_code=target_window_code,
    )

    print("Analysis complete – flexible grouping applied.")
    return {
        "details": all_rel,
        "per_id_summary": per_id_summary,
        "total_summary": total_summary,
    }


def plot_dist(
    all_rel: pd.DataFrame,
    median_order,
    grouping_level: int,
    export_plots: bool = False,
    target_window_code: str = "",
):
    plt.figure(figsize=(12, 6))

    ax = sns.boxplot(
        data=all_rel,
        x="Extracted_Codes_Labels",
        y="relative_len",
        palette="Set2",
        fliersize=0,
    )

    sns.stripplot(
        data=all_rel,
        x="Extracted_Codes_Labels",
        y="relative_len",
        color="black",
        alpha=0.66,
        size=5,
        jitter=0.1,
        ax=ax,
    )

    # ---- counts per group ----
    counts = all_rel.groupby("Extracted_Codes_Labels").size()

    # ---- add n above each box ----
    y_max = all_rel["relative_len"].max()
    y_offset = y_max * 0.05

    for i, group in enumerate(ax.get_xticklabels()):
        label = group.get_text()
        n = counts.get(label, 0)
        ax.text(
            i,
            y_max + y_offset,
            f"n={n}",
            ha="center",
            va="bottom",
            fontsize=11,
            color="black",
        )

    # ---- rotate x labels ----
    plt.xticks(rotation=30, ha="right")

    # plt.title(
    #    f"Distribution of Relative Lengths by Code Group (level {grouping_level}) – "
    #    "sorted by median ascending"
    # )
    plt.ylabel(f"Relative length within {target_window_code}")
    plt.xlabel("")

    plt.tight_layout()

    if export_plots:
        plt.savefig(
            f"relative_len_distribution_level{grouping_level}_median_sorted.png",
            dpi=300,
        )
    plt.show()


# codes, die nicht in die Zeitverteilungsanalyse rein sollen:
# alle, deren rel. länge 1.0 beträgt
# 2.1.1.4
# 2.1.3.6
# 6.4.4
# 6.4.3

# 5.2.1 und 5.2.2 zusammen fassen zu 5.2

# reihenfolge

# ---------------- Example run ----------------
if __name__ == "__main__":
    csv_file = "extracted_sequences.csv"
    # choose grouping level: 1 = first digit, 2 = first two, 3 = etc., None = full code
    results = compute_relative_lengths_within_6_1_1(
        csv_file,
        grouping_level=None,
        target_window_code="6.1.2",
        exclude_codes=[
            # "2.1.1.4",
            # "2.1.3.6",
            # "6.4.4",
            # "6.4.3",
            # "2.2.4.2",
            # "2.2.3.14",
            # "2.2.3.4",
            # "6.3.3",
            # "6.3.5",
            # "6.3.1",
            # "2.1.1.1",
        ],
        aggregate_codes=[],
    )
