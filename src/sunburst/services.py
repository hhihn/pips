from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.sunburst.andere_analysis import (
    analyze_andere_by_ring,
    analyze_codes_causing_andere,
    create_andere_summary,
)
from src.sunburst.branching_analysis import analyze_branching_codes, analyze_branching_nodes
from src.sunburst.cooccurrrence import analyze_code_cooccurrences, create_cooccurrence_summary
from src.sunburst.context import AnalysisContext


@dataclass
class BranchingAnalyzerService:
    def analyze(
        self,
        seqs_labels: list[list[str]],
        branch_depth: int | None,
        min_parent_count: int,
        min_child_count: int,
        min_distinct_children: int,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        branching_codes = analyze_branching_codes(
            seqs_labels,
            max_depth=branch_depth,
            min_parent_count=min_parent_count,
            min_child_count=min_child_count,
            min_distinct_children=min_distinct_children,
        )
        branching_nodes = analyze_branching_nodes(
            seqs_labels,
            max_depth=branch_depth,
            min_parent_count=min_parent_count,
            min_child_count=min_child_count,
            min_distinct_children=min_distinct_children,
        )
        return branching_codes, branching_nodes


@dataclass
class CooccurrenceAnalyzerService:
    context: AnalysisContext

    def analyze(self, df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        same_start_counts, same_window_counts = analyze_code_cooccurrences(
            df, context=self.context
        )
        summary = create_cooccurrence_summary(same_start_counts, same_window_counts)
        return same_start_counts, same_window_counts, summary


@dataclass
class AndereAnalyzerService:
    context: AnalysisContext
    start_lookahead_n: int
    combo_time_match_mode: str

    def analyze(
        self,
        df: pd.DataFrame,
        per_path: pd.DataFrame,
    ) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, pd.DataFrame]]:
        andere_by_ring = analyze_andere_by_ring(per_path, context=self.context)
        codes_causing_andere = analyze_codes_causing_andere(
            df,
            per_path,
            start_lookahead_n=self.start_lookahead_n,
            combo_time_match_mode=self.combo_time_match_mode,
            context=self.context,
        )
        andere_summary = create_andere_summary(andere_by_ring, codes_causing_andere)
        return andere_by_ring, codes_causing_andere, andere_summary
