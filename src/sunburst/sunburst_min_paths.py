#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI entrypoint for the stage-based sunburst analysis pipeline.
"""

from __future__ import annotations

import argparse
import logging

from src.sunburst.analysis_pipeline import PipelineConfig, SunburstAnalysisPipeline


def build_arg_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="../extracted_sequences.csv", help="Input CSV")
    ap.add_argument("--out_prefix", default="out_paths", help="Prefix für Output-Dateien")
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
    ap.add_argument(
        "--all_codes_together",
        action="store_true",
        default=False,
        help="Use all-codes-together approach.",
    )
    ap.add_argument(
        "--combo_time_match_mode",
        choices=["keine", "exact", "overlap"],
        default="exact",
        help="Combo-Modus: keine, exact, overlap.",
    )
    ap.add_argument(
        "--log_level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level.",
    )
    return ap


def main() -> None:
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config = PipelineConfig(
        csv=args.csv,
        out_prefix=args.out_prefix,
        max_depth=args.max_depth,
        start_lookahead_n=args.start_lookahead_n,
        min_support=args.min_support,
        rare_label=args.rare_label,
        drop_rare_paths=args.drop_rare_paths,
        cooccurrence_csv=args.cooccurrence_csv,
        min_window_count=args.min_window_count,
        refresh_data_driven_rules=args.refresh_data_driven_rules,
        no_sunburst=args.no_sunburst,
        no_branching_analysis=args.no_branching_analysis,
        branching_max_depth=args.branching_max_depth,
        min_branch_parent_count=args.min_branch_parent_count,
        min_branch_child_count=args.min_branch_child_count,
        min_branch_children=args.min_branch_children,
        all_codes_together=args.all_codes_together,
        combo_time_match_mode=args.combo_time_match_mode,
    )
    SunburstAnalysisPipeline(config).run()


if __name__ == "__main__":
    main()
