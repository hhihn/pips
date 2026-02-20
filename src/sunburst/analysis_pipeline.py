from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from src.sunburst.andere_analysis import print_andere_report
from src.sunburst.bundling import make_bundle_strategy
from src.sunburst.code_util import CodeUtil
from src.sunburst.context import AnalysisContext
from src.sunburst.helper import customwrap, sequences_to_sunburst_wide, wide_to_sunburst_nodes
from src.sunburst.rules_repo import CodeUtilRulesRepository
from src.sunburst.sequence_builders import AllCodesSequenceBuilder, PartsSequenceBuilder
from src.sunburst.services import (
    AndereAnalyzerService,
    BranchingAnalyzerService,
    CooccurrenceAnalyzerService,
)
from src.sunburst.time_series_loader import TimeSeriesLoader
from src.sunburst.time_series_model import TimeSeriesDataset

logger = logging.getLogger(__name__)
CSV_ANALYSIS_ROOT = "csv_analysen"


@dataclass(frozen=True)
class PipelineConfig:
    csv: str
    out_prefix: str = "out_paths"
    max_depth: int = 4
    start_lookahead_n: int = 5
    min_support: int = 1
    rare_label: str = "Andere (selten)"
    drop_rare_paths: bool = False
    cooccurrence_csv: str = "csv_analysen/cooccurrence/out_paths_cooccurrence_same_window.csv"
    min_window_count: int = 5
    refresh_data_driven_rules: bool = False
    no_sunburst: bool = False
    no_branching_analysis: bool = False
    branching_max_depth: int | None = None
    min_branch_parent_count: int = 3
    min_branch_child_count: int = 1
    min_branch_children: int = 2
    all_codes_together: bool = False
    combo_time_match_mode: str = "exact"


@dataclass(frozen=True)
class LoadResult:
    dataset: TimeSeriesDataset


@dataclass(frozen=True)
class NormalizeResult:
    dataframe: pd.DataFrame


@dataclass(frozen=True)
class ValidateResult:
    dataframe: pd.DataFrame


@dataclass(frozen=True)
class AnalyzeResult:
    context: AnalysisContext
    dataframe: pd.DataFrame
    seqs_labels: list[list[str]]
    per_path: pd.DataFrame
    path_counts: pd.DataFrame
    branching_codes: pd.DataFrame | None
    branching_nodes: pd.DataFrame | None
    cooccurrence_same_start: pd.DataFrame
    cooccurrence_same_window: pd.DataFrame
    cooccurrence_summary: pd.DataFrame
    andere_by_ring: pd.DataFrame | None
    codes_in_andere_cases: pd.DataFrame | None
    andere_summary: dict[str, pd.DataFrame] | None


@dataclass(frozen=True)
class ExportResult:
    files: dict[str, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class VisualizeResult:
    html_path: Path | None


@dataclass(frozen=True)
class PipelineRunResult:
    load: LoadResult
    normalize: NormalizeResult
    validate: ValidateResult
    analyze: AnalyzeResult
    export: ExportResult
    visualize: VisualizeResult


class SunburstAnalysisPipeline:
    """Stage-based pipeline: load -> normalize -> validate -> analyze -> export -> visualize."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def load(self) -> LoadResult:
        dataset = TimeSeriesLoader().from_csv(self.config.csv)
        logger.info(
            "Loaded %s events (%s interval, %s point).",
            len(dataset.events),
            sum(1 for e in dataset.events if e.start_seconds != e.end_seconds),
            sum(1 for e in dataset.events if e.start_seconds == e.end_seconds),
        )
        return LoadResult(dataset=dataset)

    def normalize(self, load_result: LoadResult) -> NormalizeResult:
        df = load_result.dataset.to_legacy_dataframe()
        return NormalizeResult(dataframe=df)

    def validate(self, normalize_result: NormalizeResult) -> ValidateResult:
        d = normalize_result.dataframe
        required_cols = {"Sequence_Code", "Filename", "Sequence_Start", "Sequence_End"}
        missing = sorted(required_cols - set(d.columns))
        if missing:
            raise ValueError(f"Missing required normalized columns: {', '.join(missing)}")

        if d.empty:
            raise ValueError("Input dataset is empty after normalization.")

        start_s = pd.to_timedelta(d["Sequence_Start"], errors="coerce")
        end_s = pd.to_timedelta(d["Sequence_End"], errors="coerce")
        if start_s.isna().any() or end_s.isna().any():
            raise ValueError("Found invalid normalized time values in Sequence_Start/Sequence_End.")

        if (end_s < start_s).any():
            raise ValueError("Found rows with end time earlier than start time.")

        return ValidateResult(dataframe=d)

    def analyze(self, validate_result: ValidateResult) -> AnalyzeResult:
        code_util = CodeUtil()
        rules_repo = CodeUtilRulesRepository(code_util=code_util)
        if self.config.cooccurrence_csv:
            context = rules_repo.load_context(
                cooccurrence_csv=self.config.cooccurrence_csv,
                min_window_count=self.config.min_window_count,
                refresh=self.config.refresh_data_driven_rules,
            )
        else:
            context = AnalysisContext.from_code_util(code_util)

        df = validate_result.dataframe
        if self.config.all_codes_together:
            logger.info("Using ALL_CODES_TOGETHER approach")
            seqs_labels, per_path = AllCodesSequenceBuilder(context=context).build(
                df,
                start_lookahead_n=self.config.start_lookahead_n,
                combo_time_match_mode=self.config.combo_time_match_mode,
            )
        else:
            logger.info("Using PARTS_APPROACH (4 rings: innen/mitte/aussen/aussenring)")
            logger.info("Combo time matching mode: %s", self.config.combo_time_match_mode)
            seqs_labels, per_path = PartsSequenceBuilder(
                context=context,
                bundle_strategy=make_bundle_strategy(self.config.combo_time_match_mode),
            ).build(
                df,
                start_lookahead_n=self.config.start_lookahead_n,
            )

        path_counts = (
            per_path.groupby(["start_group", "sequence_labels"])
            .size()
            .reset_index(name="count")
            .sort_values(["start_group", "count"], ascending=[True, False])
        )

        branching_codes = None
        branching_nodes = None
        if not self.config.no_branching_analysis:
            logger.info("Analyzing branching codes/nodes...")
            branch_depth = (
                self.config.branching_max_depth
                if self.config.branching_max_depth is not None
                else self.config.max_depth
            )
            branching_codes, branching_nodes = BranchingAnalyzerService().analyze(
                seqs_labels,
                branch_depth=branch_depth,
                min_parent_count=max(1, self.config.min_branch_parent_count),
                min_child_count=max(1, self.config.min_branch_child_count),
                min_distinct_children=max(2, self.config.min_branch_children),
            )

        logger.info("Analyzing code co-occurrences...")
        same_start_counts, same_window_counts, summary = CooccurrenceAnalyzerService(
            context=context
        ).analyze(df)

        andere_by_ring = None
        codes_causing_andere = None
        andere_summary = None
        if not self.config.all_codes_together:
            logger.info("Analyzing 'Andere' occurrences...")
            andere_by_ring, codes_causing_andere, andere_summary = AndereAnalyzerService(
                context=context,
                start_lookahead_n=self.config.start_lookahead_n,
                combo_time_match_mode=self.config.combo_time_match_mode,
            ).analyze(df, per_path)

        return AnalyzeResult(
            context=context,
            dataframe=df,
            seqs_labels=seqs_labels,
            per_path=per_path,
            path_counts=path_counts,
            branching_codes=branching_codes,
            branching_nodes=branching_nodes,
            cooccurrence_same_start=same_start_counts,
            cooccurrence_same_window=same_window_counts,
            cooccurrence_summary=summary,
            andere_by_ring=andere_by_ring,
            codes_in_andere_cases=codes_causing_andere,
            andere_summary=andere_summary,
        )

    def export(self, analyze_result: AnalyzeResult) -> ExportResult:
        out_prefix = self.config.out_prefix
        files: dict[str, Path] = {}

        per_path_path = self._csv_out_path(out_prefix, "pfade", "per_path_sequences")
        analyze_result.per_path.to_csv(per_path_path, index=False)
        files["per_path_sequences"] = per_path_path

        path_counts_path = self._csv_out_path(out_prefix, "pfade", "path_counts")
        analyze_result.path_counts.to_csv(path_counts_path, index=False)
        files["path_counts"] = path_counts_path

        if analyze_result.branching_codes is not None and analyze_result.branching_nodes is not None:
            branching_codes_path = self._csv_out_path(out_prefix, "branching", "branching_codes")
            branching_nodes_path = self._csv_out_path(out_prefix, "branching", "branching_nodes")
            analyze_result.branching_codes.to_csv(branching_codes_path, index=False)
            analyze_result.branching_nodes.to_csv(branching_nodes_path, index=False)
            files["branching_codes"] = branching_codes_path
            files["branching_nodes"] = branching_nodes_path

        co_start_path = self._csv_out_path(out_prefix, "cooccurrence", "cooccurrence_same_start")
        co_window_path = self._csv_out_path(out_prefix, "cooccurrence", "cooccurrence_same_window")
        co_summary_path = self._csv_out_path(out_prefix, "cooccurrence", "cooccurrence_summary")
        analyze_result.cooccurrence_same_start.to_csv(co_start_path, index=False)
        analyze_result.cooccurrence_same_window.to_csv(co_window_path, index=False)
        analyze_result.cooccurrence_summary.to_csv(co_summary_path, index=False)
        files["cooccurrence_same_start"] = co_start_path
        files["cooccurrence_same_window"] = co_window_path
        files["cooccurrence_summary"] = co_summary_path

        if (
            analyze_result.andere_by_ring is not None
            and analyze_result.codes_in_andere_cases is not None
        ):
            andere_by_ring_path = self._csv_out_path(out_prefix, "andere", "andere_by_ring")
            andere_codes_path = self._csv_out_path(out_prefix, "andere", "codes_in_andere_cases")
            analyze_result.andere_by_ring.to_csv(andere_by_ring_path, index=False)
            analyze_result.codes_in_andere_cases.to_csv(andere_codes_path, index=False)
            files["andere_by_ring"] = andere_by_ring_path
            files["codes_in_andere_cases"] = andere_codes_path

        logger.info("Wrote output files with prefix: %s", out_prefix)
        return ExportResult(files=files)

    def visualize(self, analyze_result: AnalyzeResult) -> VisualizeResult:
        if self.config.no_sunburst:
            return VisualizeResult(html_path=None)

        try:
            import plotly.express as px
        except Exception:
            logger.warning("Plotly is unavailable; skipping sunburst visualization stage.")
            return VisualizeResult(html_path=None)

        wide = sequences_to_sunburst_wide(
            analyze_result.seqs_labels,
            max_depth=self.config.max_depth,
            min_support=max(1, self.config.min_support),
            rare_label=None if self.config.drop_rare_paths else self.config.rare_label,
        )
        nodes = wide_to_sunburst_nodes(wide, max_depth=self.config.max_depth)
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
        html_path = Path(f"{self.config.out_prefix}_sunburst.html")
        fig.write_html(str(html_path))
        logger.info("Wrote: %s", html_path)
        return VisualizeResult(html_path=html_path)

    def run(self) -> PipelineRunResult:
        loaded = self.load()
        normalized = self.normalize(loaded)
        validated = self.validate(normalized)
        analyzed = self.analyze(validated)
        exported = self.export(analyzed)
        visualized = self.visualize(analyzed)
        if analyzed.andere_summary is not None:
            print_andere_report(analyzed.andere_summary)
        return PipelineRunResult(
            load=loaded,
            normalize=normalized,
            validate=validated,
            analyze=analyzed,
            export=exported,
            visualize=visualized,
        )

    @staticmethod
    def _csv_out_path(out_prefix: str, theme: str, suffix: str) -> Path:
        out_prefix_path = Path(out_prefix)
        filename = f"{out_prefix_path.name}_{suffix}.csv"
        target_dir = out_prefix_path.parent / CSV_ANALYSIS_ROOT / theme
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / filename
