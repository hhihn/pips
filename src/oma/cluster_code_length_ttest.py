from __future__ import annotations

import argparse
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

os.environ.setdefault(
    "MPLCONFIGDIR",
    str(Path(tempfile.gettempdir()) / "oma_matplotlib_cache"),
)

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from scipy import stats


TIMEFRAME_RE = re.compile(r"\(([^()]+?)\s+-\s+([^()]+?)\)")
FILE_RE = re.compile(r"^File:\s+(.+?)\s*$")
CARE_CHILD_RE = re.compile(
    r"^\s*Child:\s+6\.1\.1\s+Pflegesituation\s+\(([^()]+?)\s+-\s+([^()]+?)\)"
)
SEQUENCE_RE = re.compile(r"^\s*↳ Sequence \((\d+) events\):")
EVENT_RE = re.compile(
    r"^\s*(\d+)\.\s+"
    r"(?P<code>\d+(?:\.\d+)*)(?:\s+.*)?"
    r"\((?P<start>[^()]+?)\s+-\s+(?P<end>[^()]+?)\)\s*$"
)


@dataclass(frozen=True)
class SummaryEvent:
    filename: str
    care_start_s: float
    care_end_s: float
    rank: int
    code: str
    start_s: float
    end_s: float


@dataclass(frozen=True)
class CareBlock:
    filename: str
    care_start_s: float
    care_end_s: float
    events: Tuple[SummaryEvent, ...]


def parse_timestamp(value: str) -> float:
    value = str(value).strip().replace(",", ".")
    parts = value.split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected timestamp format: {value}")

    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return hours * 3600 + minutes * 60 + seconds


def parse_analysis_summary(path: Path) -> List[CareBlock]:
    current_file: Optional[str] = None
    current_care: Optional[Tuple[float, float]] = None
    current_events: List[SummaryEvent] = []
    inside_sequence = False
    blocks: List[CareBlock] = []

    def flush_current_block() -> None:
        nonlocal current_care, current_events, inside_sequence
        if (
            current_file is not None
            and current_care is not None
            and current_events
        ):
            blocks.append(
                CareBlock(
                    filename=current_file,
                    care_start_s=current_care[0],
                    care_end_s=current_care[1],
                    events=tuple(current_events),
                )
            )
        current_care = None
        current_events = []
        inside_sequence = False

    for raw_line in Path(path).read_text(encoding="utf-8").splitlines():
        file_match = FILE_RE.match(raw_line)
        if file_match:
            flush_current_block()
            current_file = file_match.group(1).strip()
            continue

        care_match = CARE_CHILD_RE.match(raw_line)
        if care_match:
            flush_current_block()
            current_care = (
                parse_timestamp(care_match.group(1)),
                parse_timestamp(care_match.group(2)),
            )
            continue

        if current_care is None:
            continue

        if SEQUENCE_RE.match(raw_line):
            inside_sequence = True
            continue

        if inside_sequence:
            event_match = EVENT_RE.match(raw_line)
            if event_match:
                start_s = parse_timestamp(event_match.group("start"))
                end_s = parse_timestamp(event_match.group("end"))
                current_events.append(
                    SummaryEvent(
                        filename=current_file or "",
                        care_start_s=current_care[0],
                        care_end_s=current_care[1],
                        rank=int(event_match.group(1)),
                        code=event_match.group("code"),
                        start_s=start_s,
                        end_s=end_s,
                    )
                )
            elif raw_line.strip() and not raw_line.startswith("          "):
                inside_sequence = False

    flush_current_block()
    return blocks


def load_sequence_cluster_map(
    extracted_path: Path,
    cluster_labels_path: Path,
) -> pd.DataFrame:
    extracted = pd.read_csv(extracted_path)
    labels = pd.read_csv(cluster_labels_path, index_col=0)
    labels.index = labels.index.astype(str)

    care_rows = extracted[
        extracted["Sequence_Code"].astype(str).str.strip().str.startswith("6.1.1")
    ].copy()
    care_rows["care_start_s"] = care_rows["Sequence_Start"].map(parse_timestamp)
    care_rows["care_end_s"] = care_rows["Sequence_End"].map(parse_timestamp)
    care_rows["id"] = care_rows["id"].astype(str)

    mapping = care_rows[
        ["id", "Filename", "care_start_s", "care_end_s"]
    ].drop_duplicates()
    mapping = mapping.merge(
        labels[["cluster"]],
        left_on="id",
        right_index=True,
        how="left",
    )
    missing = mapping[mapping["cluster"].isna()]["id"].tolist()
    if missing:
        raise ValueError(f"Missing cluster labels for sequence ids: {missing}")

    mapping["cluster"] = mapping["cluster"].astype(int)
    return mapping


def attach_blocks_to_sequence_ids(
    blocks: Sequence[CareBlock],
    sequence_map: pd.DataFrame,
    tolerance_s: float = 0.3,
) -> pd.DataFrame:
    rows = []

    for block in blocks:
        candidates = sequence_map[
            (sequence_map["Filename"] == block.filename)
            & (
                (sequence_map["care_start_s"] - block.care_start_s)
                .abs()
                .le(tolerance_s)
            )
            & (
                (sequence_map["care_end_s"] - block.care_end_s)
                .abs()
                .le(tolerance_s)
            )
        ]

        if len(candidates) != 1:
            raise ValueError(
                "Could not map analysis_summary block uniquely to OMA id: "
                f"{block.filename} ({block.care_start_s} - {block.care_end_s}); "
                f"matched {len(candidates)} rows."
            )

        sequence_row = candidates.iloc[0]
        for event in block.events:
            rows.append(
                {
                    "id": sequence_row["id"],
                    "Filename": block.filename,
                    "cluster": int(sequence_row["cluster"]),
                    "care_start_s": block.care_start_s,
                    "care_end_s": block.care_end_s,
                    "rank": event.rank,
                    "code": event.code,
                    "event_start_s": event.start_s,
                    "event_end_s": event.end_s,
                    "duration_s": event.end_s - event.start_s,
                }
            )

    return pd.DataFrame(rows)


def code_matches(code: str, target: str, match_mode: str) -> bool:
    code = str(code)
    target = normalize_target_code(target)

    if match_mode == "exact":
        return code == target
    if match_mode == "prefix":
        return code == target or code.startswith(f"{target}.")
    if match_mode == "wildcard":
        pattern = "^" + re.escape(target).replace(r"\*", ".*") + "$"
        return re.match(pattern, code) is not None

    raise ValueError(f"Unknown match mode: {match_mode}")


def normalize_target_code(target: str) -> str:
    target = str(target).strip()
    return re.sub(r"\s+(PK|AK)$", "", target)


def merge_intervals(intervals: Iterable[Tuple[float, float]]) -> List[Tuple[float, float]]:
    sorted_intervals = sorted(
        {(float(start), float(end)) for start, end in intervals if end > start}
    )
    if not sorted_intervals:
        return []

    merged = [sorted_intervals[0]]
    for start, end in sorted_intervals[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))

    return merged


def aggregate_code_durations(
    events: pd.DataFrame,
    sequence_map: pd.DataFrame,
    target_code: str,
    clusters: Tuple[int, int],
    match_mode: str,
) -> pd.DataFrame:
    base = sequence_map[sequence_map["cluster"].isin(clusters)].copy()
    base = base[["id", "Filename", "cluster", "care_start_s", "care_end_s"]]

    matched = events[
        events["code"].map(lambda code: code_matches(code, target_code, match_mode))
    ].copy()

    duration_by_id = {}
    for sequence_id, group in matched.groupby("id"):
        intervals = zip(group["event_start_s"], group["event_end_s"])
        duration_by_id[sequence_id] = sum(
            end - start for start, end in merge_intervals(intervals)
        )

    base["target_code"] = target_code
    base["matched_code"] = normalize_target_code(target_code)
    base["duration_s"] = base["id"].map(duration_by_id).fillna(0.0)
    base["has_code"] = base["duration_s"] > 0
    return base.sort_values(["cluster", "id"]).reset_index(drop=True)


def shapiro_p(values: np.ndarray) -> float:
    if len(values) < 3 or np.allclose(values, values[0]):
        return float("nan")
    return float(stats.shapiro(values).pvalue)


def describe_group(values: np.ndarray) -> dict:
    return {
        "n": int(len(values)),
        "nonzero_n": int(np.count_nonzero(values)),
        "mean": float(np.mean(values)) if len(values) else float("nan"),
        "sd": float(np.std(values, ddof=1)) if len(values) > 1 else float("nan"),
        "median": float(np.median(values)) if len(values) else float("nan"),
        "min": float(np.min(values)) if len(values) else float("nan"),
        "max": float(np.max(values)) if len(values) else float("nan"),
    }


def cohens_d(group_a: np.ndarray, group_b: np.ndarray) -> float:
    if len(group_a) < 2 or len(group_b) < 2:
        return float("nan")
    pooled_df = len(group_a) + len(group_b) - 2
    pooled_var = (
        ((len(group_a) - 1) * np.var(group_a, ddof=1))
        + ((len(group_b) - 1) * np.var(group_b, ddof=1))
    ) / pooled_df
    if np.isclose(pooled_var, 0.0):
        return float("nan")
    return float((np.mean(group_a) - np.mean(group_b)) / math.sqrt(pooled_var))


def hedges_g(group_a: np.ndarray, group_b: np.ndarray) -> float:
    d = cohens_d(group_a, group_b)
    df = len(group_a) + len(group_b) - 2
    if np.isnan(d) or df <= 1:
        return float("nan")
    correction = 1 - (3 / (4 * df - 1))
    return float(d * correction)


def one_sided_p_from_two_sided_t(
    statistic: float,
    two_sided_p: float,
    alternative: str,
) -> float:
    if np.isnan(statistic) or np.isnan(two_sided_p):
        return float("nan")
    if alternative == "greater":
        return float(two_sided_p / 2 if statistic > 0 else 1 - two_sided_p / 2)
    if alternative == "less":
        return float(two_sided_p / 2 if statistic < 0 else 1 - two_sided_p / 2)
    raise ValueError(f"Unknown alternative: {alternative}")


def statistical_result(observations: pd.DataFrame, clusters: Tuple[int, int]) -> dict:
    cluster_a, cluster_b = clusters
    group_a = observations.loc[
        observations["cluster"] == cluster_a,
        "duration_s",
    ].to_numpy(dtype=float)
    group_b = observations.loc[
        observations["cluster"] == cluster_b,
        "duration_s",
    ].to_numpy(dtype=float)

    desc_a = describe_group(group_a)
    desc_b = describe_group(group_b)
    mean_difference = desc_a["mean"] - desc_b["mean"]
    if np.isnan(mean_difference) or np.isclose(mean_difference, 0.0):
        direction = "no_difference"
        one_sided_alternative = "two_sided_only"
    elif mean_difference > 0:
        direction = f"cluster_{cluster_a}_greater"
        one_sided_alternative = "greater"
    else:
        direction = f"cluster_{cluster_a}_less"
        one_sided_alternative = "less"
    normality_a = shapiro_p(group_a)
    normality_b = shapiro_p(group_b)
    all_zero = bool(np.allclose(group_a, 0.0) and np.allclose(group_b, 0.0))

    if all_zero:
        levene_p = float("nan")
        welch = student = None
    elif len(group_a) >= 2 and len(group_b) >= 2:
        levene_p = float(stats.levene(group_a, group_b, center="median").pvalue)
        welch = stats.ttest_ind(group_a, group_b, equal_var=False, nan_policy="omit")
        student = stats.ttest_ind(group_a, group_b, equal_var=True, nan_policy="omit")
    else:
        levene_p = float("nan")
        welch = student = None

    if len(group_a) >= 1 and len(group_b) >= 1:
        try:
            mann_whitney = stats.mannwhitneyu(
                group_a,
                group_b,
                alternative="two-sided",
            )
            mann_whitney_u = float(mann_whitney.statistic)
            mann_whitney_p = float(mann_whitney.pvalue)
        except ValueError:
            mann_whitney_u = float("nan")
            mann_whitney_p = float("nan")
    else:
        mann_whitney_u = float("nan")
        mann_whitney_p = float("nan")

    return {
        "target_code": str(observations["target_code"].iloc[0]),
        "cluster_a": cluster_a,
        "cluster_b": cluster_b,
        "mean_difference_a_minus_b": float(mean_difference),
        "direction": direction,
        "directional_alternative": one_sided_alternative,
        **{f"a_{key}": value for key, value in desc_a.items()},
        **{f"b_{key}": value for key, value in desc_b.items()},
        "shapiro_p_a": normality_a,
        "shapiro_p_b": normality_b,
        "normality_ok": bool(
            (np.isnan(normality_a) or normality_a >= 0.05)
            and (np.isnan(normality_b) or normality_b >= 0.05)
        ),
        "levene_p": levene_p,
        "equal_variance_ok": bool(np.isnan(levene_p) or levene_p >= 0.05),
        "welch_t": float(welch.statistic) if welch is not None else float("nan"),
        "welch_p": float(welch.pvalue) if welch is not None else float("nan"),
        "welch_directional_p": (
            one_sided_p_from_two_sided_t(
                float(welch.statistic),
                float(welch.pvalue),
                one_sided_alternative,
            )
            if welch is not None and one_sided_alternative in {"greater", "less"}
            else float("nan")
        ),
        "student_t": float(student.statistic) if student is not None else float("nan"),
        "student_p": float(student.pvalue) if student is not None else float("nan"),
        "student_directional_p": (
            one_sided_p_from_two_sided_t(
                float(student.statistic),
                float(student.pvalue),
                one_sided_alternative,
            )
            if student is not None and one_sided_alternative in {"greater", "less"}
            else float("nan")
        ),
        "mann_whitney_u": mann_whitney_u,
        "mann_whitney_p": mann_whitney_p,
        "cohens_d": cohens_d(group_a, group_b),
        "hedges_g": hedges_g(group_a, group_b),
        "all_zero": all_zero,
    }


def build_analysis(
    analysis_summary_path: Path,
    extracted_path: Path,
    cluster_labels_path: Path,
    codes: Sequence[str],
    clusters: Tuple[int, int],
    match_mode: str,
    tolerance_s: float,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    blocks = parse_analysis_summary(analysis_summary_path)
    sequence_map = load_sequence_cluster_map(extracted_path, cluster_labels_path)
    events = attach_blocks_to_sequence_ids(blocks, sequence_map, tolerance_s)

    observations = []
    results = []
    for code in codes:
        code_observations = aggregate_code_durations(
            events,
            sequence_map,
            target_code=code,
            clusters=clusters,
            match_mode=match_mode,
        )
        observations.append(code_observations)
        results.append(statistical_result(code_observations, clusters))

    return pd.concat(observations, ignore_index=True), pd.DataFrame(results)


def format_float(value: float) -> str:
    if pd.isna(value):
        return "n/a"
    return f"{value:.4g}"


def print_report(results: pd.DataFrame) -> None:
    for row in results.to_dict(orient="records"):
        print(f"\nCode {row['target_code']}")
        print(
            f"  Cluster {row['cluster_a']}: "
            f"n={row['a_n']}, nonzero={row['a_nonzero_n']}, "
            f"mean={format_float(row['a_mean'])}s, sd={format_float(row['a_sd'])}s"
        )
        print(
            f"  Cluster {row['cluster_b']}: "
            f"n={row['b_n']}, nonzero={row['b_nonzero_n']}, "
            f"mean={format_float(row['b_mean'])}s, sd={format_float(row['b_sd'])}s"
        )
        print(
            "  Assumptions: "
            f"Shapiro p={format_float(row['shapiro_p_a'])}/"
            f"{format_float(row['shapiro_p_b'])}; "
            f"Levene p={format_float(row['levene_p'])}"
        )
        print(
            "  Welch t-test: "
            f"t={format_float(row['welch_t'])}, p={format_float(row['welch_p'])}"
        )
        print(
            "  Directional Welch test: "
            f"{row['direction']} "
            f"(mean difference={format_float(row['mean_difference_a_minus_b'])}s), "
            f"one-sided p={format_float(row['welch_directional_p'])}"
        )
        print(
            "  Student t-test: "
            f"t={format_float(row['student_t'])}, p={format_float(row['student_p'])}"
        )
        print(
            "  Directional Student test: "
            f"one-sided p={format_float(row['student_directional_p'])}"
        )
        print(
            "  Mann-Whitney sensitivity: "
            f"U={format_float(row['mann_whitney_u'])}, "
            f"p={format_float(row['mann_whitney_p'])}"
        )
        print(
            f"  Effects: d={format_float(row['cohens_d'])}, "
            f"g={format_float(row['hedges_g'])}"
        )
        if row["all_zero"]:
            print("  Warning: both groups have zero duration for this code.")


def print_independence_note(observations: pd.DataFrame) -> None:
    sequence_rows = observations[["Filename", "id"]].drop_duplicates()
    multi_sequence_files = (
        sequence_rows.groupby("Filename")["id"].nunique().loc[lambda s: s > 1]
    )
    if multi_sequence_files.empty:
        print("Independence note: each filename contributes one OMA sequence id.")
        return

    print(
        "Independence note: using OMA sequence id as the observation unit; "
        f"{len(multi_sequence_files)} filenames contribute multiple sequence ids."
    )


def safe_filename(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip()).strip("_")


def save_violin_plots(
    observations: pd.DataFrame,
    output_dir: Path,
    formats: Sequence[str],
) -> List[Path]:
    plot_dir = output_dir / "plots"
    plot_dir.mkdir(parents=True, exist_ok=True)

    sns.set_theme(
        context="paper",
        style="whitegrid",
        font="DejaVu Sans",
        font_scale=1.15,
    )
    palette = sns.color_palette("colorblind", n_colors=observations["cluster"].nunique())
    saved_paths: List[Path] = []

    for target_code, code_data in observations.groupby("target_code", sort=False):
        plot_data = code_data.copy()
        plot_data["cluster_label"] = plot_data["cluster"].map(
            lambda cluster: f"Cluster {cluster}"
        )

        fig, ax = plt.subplots(figsize=(4.8, 4.0), constrained_layout=True)
        sns.violinplot(
            data=plot_data,
            x="cluster_label",
            y="duration_s",
            hue="cluster_label",
            palette=palette,
            inner=None,
            cut=0,
            linewidth=1.0,
            legend=False,
            ax=ax,
        )
        sns.boxplot(
            data=plot_data,
            x="cluster_label",
            y="duration_s",
            width=0.18,
            showcaps=True,
            showfliers=False,
            boxprops={"facecolor": "white", "edgecolor": "black", "linewidth": 0.9},
            whiskerprops={"color": "black", "linewidth": 0.9},
            medianprops={"color": "black", "linewidth": 1.2},
            ax=ax,
        )
        sns.stripplot(
            data=plot_data,
            x="cluster_label",
            y="duration_s",
            color="black",
            alpha=0.45,
            size=2.7,
            jitter=0.18,
            ax=ax,
        )
        ax.set_title(f"Duration of code {target_code}", pad=10)
        ax.set_xlabel("")
        ax.set_ylabel("Duration per OMA sequence (s)")
        sns.despine(ax=ax, trim=True)

        stem = f"violin_duration_{safe_filename(target_code)}"
        for fmt in formats:
            path = plot_dir / f"{stem}.{fmt}"
            fig.savefig(path, dpi=300, bbox_inches="tight")
            saved_paths.append(path)
        plt.close(fig)

    if observations["target_code"].nunique() > 1:
        facet_data = observations.copy()
        facet_data["cluster_label"] = facet_data["cluster"].map(
            lambda cluster: f"Cluster {cluster}"
        )
        grid = sns.catplot(
            data=facet_data,
            x="cluster_label",
            y="duration_s",
            col="target_code",
            kind="violin",
            hue="cluster_label",
            palette=palette,
            inner=None,
            cut=0,
            linewidth=1.0,
            legend=False,
            height=3.8,
            aspect=0.85,
            sharey=False,
        )
        grid.set_axis_labels("", "Duration per OMA sequence (s)")
        grid.set_titles("Code {col_name}")
        for ax in grid.axes.flat:
            sns.despine(ax=ax, trim=True)
        for fmt in formats:
            path = plot_dir / f"violin_duration_all_codes.{fmt}"
            grid.figure.savefig(path, dpi=300, bbox_inches="tight")
            saved_paths.append(path)
        plt.close(grid.figure)

    return saved_paths


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare per-sequence code durations between OMA clusters using "
            "analysis_summary.txt timeframes."
        )
    )
    parser.add_argument("--analysis-summary",
                        type=Path,
                        default=Path("../../data/transformed/analysis_results/analysis_summary.txt"))
    parser.add_argument("--extracted", type=Path, default=Path("../extracted_sequences.csv"))
    parser.add_argument("--cluster-labels", type=Path, default=Path("oma_output/cluster_labels.csv"))
    parser.add_argument("--codes", nargs="+", default=["5.3.1", "6.1.2", "6.1.4", "6.1.3", "2.2.3.4", "6.4.3", "6.4.4", "6.4.5"], type=str, dest="codes")
    parser.add_argument("--clusters", nargs=2, type=int, default=(1, 2))
    parser.add_argument(
        "--match",
        choices=["exact", "prefix", "wildcard"],
        default="exact",
    )
    parser.add_argument("--tolerance-s", type=float, default=0.3)
    parser.add_argument("--output-dir", type=Path, default=Path("oma_output"))
    parser.add_argument(
        "--plot-format",
        nargs="+",
        choices=["png", "pdf", "svg"],
        default=["png", "pdf"],
        help="Image formats for publication-ready violin plots.",
    )
    parser.add_argument(
        "--no-plots",
        action="store_true",
        help="Disable violin plot generation.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    observations, results = build_analysis(
        analysis_summary_path=args.analysis_summary,
        extracted_path=args.extracted,
        cluster_labels_path=args.cluster_labels,
        codes=args.codes,
        clusters=tuple(args.clusters),
        match_mode=args.match,
        tolerance_s=args.tolerance_s,
    )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    observations.to_csv(
        args.output_dir / "cluster_code_duration_observations.csv",
        index=False,
    )
    results.to_csv(
        args.output_dir / "cluster_code_duration_ttests.csv",
        index=False,
    )
    if not args.no_plots:
        plot_paths = save_violin_plots(
            observations,
            output_dir=args.output_dir,
            formats=args.plot_format,
        )
        print("Saved violin plots:")
        for path in plot_paths:
            print(f"  {path}")
    print_independence_note(observations)
    print_report(results)


if __name__ == "__main__":
    main()
