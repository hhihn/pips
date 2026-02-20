#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zeitmuster-Check + Sunburst aus Pfad-CSV
Neu: Toggle zwischen zwei Ansätzen:
1. "Parts Approach" (Standard): Sequenz in 4 Teile (innen/mitte/aussen/aussenring)
2. "All Codes Together": Alle Codes zusammen betrachten
"""

import argparse
import logging
from pathlib import Path
from typing import List, Tuple
import pandas as pd
from src.sunburst.helper import (
    customwrap,
    wide_to_sunburst_nodes,
    sequences_to_sunburst_wide,
)
from src.sunburst.andere_analysis import print_andere_report
from src.sunburst.code_util import CodeUtil
from src.sunburst.context import AnalysisContext
from src.sunburst.rules_repo import CodeUtilRulesRepository
from src.sunburst.bundling import make_bundle_strategy
from src.sunburst.sequence_builders import PartsSequenceBuilder, AllCodesSequenceBuilder
from src.sunburst.services import (
    BranchingAnalyzerService,
    CooccurrenceAnalyzerService,
    AndereAnalyzerService,
)
from src.sunburst.time_series_loader import TimeSeriesLoader

try:
    import plotly.express as px
except Exception:
    px = None

logger = logging.getLogger(__name__)
CSV_ANALYSIS_ROOT = "csv_analysen"


def _csv_out_path(out_prefix: str, theme: str, suffix: str) -> Path:
    """Route CSV outputs into themed analysis folders."""
    out_prefix_path = Path(out_prefix)
    filename = f"{out_prefix_path.name}_{suffix}.csv"
    target_dir = out_prefix_path.parent / CSV_ANALYSIS_ROOT / theme
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / filename


def build_sequences_parts_approach(
    df: pd.DataFrame,
    start_lookahead_n: int = 12,
    combo_time_match_mode: str = "exact",
    context: AnalysisContext | None = None,
) -> Tuple[List[List[str]], pd.DataFrame]:
    """Build sequences via parts strategy using an injected analysis context."""
    ctx = context if context is not None else AnalysisContext.from_code_util(CodeUtil())
    strategy = make_bundle_strategy(combo_time_match_mode)
    builder = PartsSequenceBuilder(context=ctx, bundle_strategy=strategy)
    return builder.build(df, start_lookahead_n=start_lookahead_n)


def build_sequences_all_together(
    df: pd.DataFrame,
    start_lookahead_n: int = 12,
    context: AnalysisContext | None = None,
    combo_time_match_mode: str = "exact",
) -> Tuple[List[List[str]], pd.DataFrame]:
    """Build sequences via all-codes strategy using an injected analysis context."""
    ctx = context if context is not None else AnalysisContext.from_code_util(CodeUtil())
    builder = AllCodesSequenceBuilder(context=ctx)
    return builder.build(
        df,
        start_lookahead_n=start_lookahead_n,
        combo_time_match_mode=combo_time_match_mode,
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="../extracted_sequences.csv", help="Input CSV")
    ap.add_argument(
        "--out_prefix", default="out_paths", help="Prefix für Output-Dateien"
    )
    ap.add_argument("--max_depth", type=int, default=4, help="Max Tiefe für Sunburst")
    ap.add_argument(
        "--start_lookahead_n", type=int, default=5, help="Lookahead N Events pro Pfad"
    )
    ap.add_argument(
        "--min_support",
        type=int,
        default=1,
        help="Minimum number of occurrences for a full path in sunburst.",
    )
    ap.add_argument(
        "--rare_label",
        default="Andere (selten)",
        help="Bucket label for paths below --min_support.",
    )
    ap.add_argument(
        "--drop_rare_paths",
        action="store_true",
        help="Drop paths below --min_support instead of bucketing them.",
    )
    ap.add_argument(
        "--cooccurrence_csv",
        default="csv_analysen/cooccurrence/out_paths_cooccurrence_same_window.csv",
        help="Path to cooccurrence CSV",
    )
    ap.add_argument("--min_window_count", type=int, default=5)
    ap.add_argument("--refresh_data_driven_rules", action="store_true", default=False)
    ap.add_argument("--no_sunburst", action="store_true")
    ap.add_argument("--no_branching_analysis", action="store_true")
    ap.add_argument(
        "--branching_max_depth",
        type=int,
        default=None,
        help="Optional depth cap for branching analysis (defaults to --max_depth).",
    )
    ap.add_argument(
        "--min_branch_parent_count",
        type=int,
        default=3,
        help="Minimum outgoing transition count for a code/node to be considered.",
    )
    ap.add_argument(
        "--min_branch_child_count",
        type=int,
        default=1,
        help="Minimum count a child branch must have to be considered.",
    )
    ap.add_argument(
        "--min_branch_children",
        type=int,
        default=2,
        help="Minimum number of distinct children required to mark as branching.",
    )

    # === FEATURE TOGGLE: Choose analysis approach ===
    ap.add_argument(
        "--all_codes_together",
        action="store_true",
        default=False,
        help="Use all-codes-together approach. Overrides --use_parts_approach",
    )
    ap.add_argument(
        "--combo_time_match_mode",
        choices=["keine", "exact", "overlap"],
        default="exact",
        help="Combo-Modus: keine (deaktiviert), exact (gleiches Start/Ende), overlap (überlappende Zeitfenster).",
    )
    ap.add_argument(
        "--log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level.",
    )

    args = ap.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    code_util = CodeUtil()
    rules_repo = CodeUtilRulesRepository(code_util=code_util)
    if args.cooccurrence_csv:
        context = rules_repo.load_context(
            cooccurrence_csv=args.cooccurrence_csv,
            min_window_count=args.min_window_count,
            refresh=args.refresh_data_driven_rules,
        )
    else:
        context = AnalysisContext.from_code_util(code_util)

    dataset = TimeSeriesLoader().from_csv(args.csv)
    df = dataset.to_legacy_dataframe()
    logger.info(
        "Loaded %s events (%s interval, %s point).",
        len(dataset.events),
        sum(1 for e in dataset.events if e.start_seconds != e.end_seconds),
        sum(1 for e in dataset.events if e.start_seconds == e.end_seconds),
    )

    # === FEATURE TOGGLE: Select analysis approach ===
    if args.all_codes_together:
        logger.info("Using ALL_CODES_TOGETHER approach")
        seqs_labels, per_path = AllCodesSequenceBuilder(context=context).build(
            df,
            start_lookahead_n=args.start_lookahead_n,
            combo_time_match_mode=args.combo_time_match_mode,
        )
    else:
        logger.info("Using PARTS_APPROACH (4 rings: innen/mitte/aussen/aussenring)")
        logger.info("Combo time matching mode: %s", args.combo_time_match_mode)
        seqs_labels, per_path = PartsSequenceBuilder(
            context=context,
            bundle_strategy=make_bundle_strategy(args.combo_time_match_mode),
        ).build(
            df,
            start_lookahead_n=args.start_lookahead_n,
        )

    per_path_path = _csv_out_path(args.out_prefix, "pfade", "per_path_sequences")
    per_path.to_csv(per_path_path, index=False)
    counts = (
        per_path.groupby(["start_group", "sequence_labels"])
        .size()
        .reset_index(name="count")
        .sort_values(["start_group", "count"], ascending=[True, False])
    )
    path_counts_path = _csv_out_path(args.out_prefix, "pfade", "path_counts")
    counts.to_csv(path_counts_path, index=False)

    # === Branching Analysis ===
    if not args.no_branching_analysis:
        logger.info("Analyzing branching codes/nodes...")
        branch_depth = (
            args.branching_max_depth
            if args.branching_max_depth is not None
            else args.max_depth
        )
        branching_codes, branching_nodes = BranchingAnalyzerService().analyze(
            seqs_labels,
            branch_depth=branch_depth,
            min_parent_count=max(1, args.min_branch_parent_count),
            min_child_count=max(1, args.min_branch_child_count),
            min_distinct_children=max(2, args.min_branch_children),
        )
        branching_codes_path = _csv_out_path(args.out_prefix, "branching", "branching_codes")
        branching_nodes_path = _csv_out_path(args.out_prefix, "branching", "branching_nodes")
        branching_codes.to_csv(branching_codes_path, index=False)
        branching_nodes.to_csv(branching_nodes_path, index=False)
        logger.info(
            "Wrote: %s, %s",
            branching_codes_path,
            branching_nodes_path,
        )

    # === Co-occurrence Analysis ===
    logger.info("Analyzing code co-occurrences...")
    same_start_counts, same_window_counts, summary = CooccurrenceAnalyzerService(
        context=context
    ).analyze(df)
    co_start_path = _csv_out_path(args.out_prefix, "cooccurrence", "cooccurrence_same_start")
    co_window_path = _csv_out_path(args.out_prefix, "cooccurrence", "cooccurrence_same_window")
    co_summary_path = _csv_out_path(args.out_prefix, "cooccurrence", "cooccurrence_summary")
    same_start_counts.to_csv(co_start_path, index=False)
    same_window_counts.to_csv(co_window_path, index=False)
    summary.to_csv(co_summary_path, index=False)

    # === "Andere" Analysis ===
    if not args.all_codes_together:
        logger.info("Analyzing 'Andere' occurrences...")
        andere_by_ring, codes_causing_andere, andere_summary = AndereAnalyzerService(
            context=context,
            start_lookahead_n=args.start_lookahead_n,
            combo_time_match_mode=args.combo_time_match_mode,
        ).analyze(
            df,
            per_path,
        )
        andere_by_ring_path = _csv_out_path(args.out_prefix, "andere", "andere_by_ring")
        andere_codes_path = _csv_out_path(args.out_prefix, "andere", "codes_in_andere_cases")
        andere_by_ring.to_csv(andere_by_ring_path, index=False)
        codes_causing_andere.to_csv(andere_codes_path, index=False)
        print_andere_report(andere_summary)

    logger.info("Wrote output files with prefix: %s", args.out_prefix)

    # === Sunburst ===
    if args.no_sunburst or px is None:
        return

    wide = sequences_to_sunburst_wide(
        seqs_labels,
        max_depth=args.max_depth,
        min_support=max(1, args.min_support),
        rare_label=None if args.drop_rare_paths else args.rare_label,
    )
    nodes = wide_to_sunburst_nodes(wide, max_depth=args.max_depth)
    nodes["label"] = nodes["label"].map(lambda x: customwrap(x, width=20))

    fig = px.sunburst(
        nodes,
        ids="id",
        parents="parent_id",
        names="label",
        values="value",
    )
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>count=%{value}<br>p(child|parent)=%{customdata:.3f}<extra></extra>",
        customdata=nodes["p_child_given_parent"],
    )
    html_path = f"{args.out_prefix}_sunburst.html"
    fig.write_html(html_path)
    logger.info("Wrote: %s", html_path)


if __name__ == "__main__":
    main()
