from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.sunburst.code_util import CodeUtil
from src.sunburst.context import AnalysisContext


class ComboRulesRepository(Protocol):
    def load_context(
        self,
        cooccurrence_csv: str,
        min_window_count: int = 5,
        refresh: bool = False,
    ) -> AnalysisContext:
        ...


@dataclass
class CodeUtilRulesRepository:
    """Adapter repository that isolates rule-loading side effects from callers."""

    code_util: CodeUtil

    def load_context(
        self,
        cooccurrence_csv: str,
        min_window_count: int = 5,
        refresh: bool = False,
    ) -> AnalysisContext:
        self.code_util.load_data_driven_rules(
            cooccurrence_csv=cooccurrence_csv,
            min_window_count=min_window_count,
            refresh=refresh,
        )
        return AnalysisContext.from_code_util(self.code_util)
