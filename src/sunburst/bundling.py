from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal

import pandas as pd


class BundleStrategy(ABC):
    mode: str

    @abstractmethod
    def build(self, events: pd.DataFrame) -> list[pd.DataFrame]:
        raise NotImplementedError


@dataclass(frozen=True)
class ExactBundleStrategy(BundleStrategy):
    mode: str = "exact"

    def build(self, events: pd.DataFrame) -> list[pd.DataFrame]:
        if events.empty:
            return []
        fe = events.sort_values(by=["start_s", "end_s"]).copy()
        return [bg.copy() for _, bg in fe.groupby(["start_s", "end_s"], sort=False)]


@dataclass(frozen=True)
class OverlapBundleStrategy(BundleStrategy):
    mode: str = "overlap"

    def build(self, events: pd.DataFrame) -> list[pd.DataFrame]:
        if events.empty:
            return []

        fe = events.sort_values(by=["start_s", "end_s"]).copy()
        bundles: list[pd.DataFrame] = []
        current_rows: list[int] = []
        current_start: float | None = None
        current_end: float | None = None

        for idx, row in fe.iterrows():
            start_s = float(row["start_s"])
            end_s = float(row["end_s"])

            if not current_rows:
                current_rows = [idx]
                current_start = start_s
                current_end = end_s
                continue

            overlaps_current = (
                current_start is not None
                and current_end is not None
                and start_s < current_end
                and end_s > current_start
            )
            if overlaps_current:
                current_rows.append(idx)
                current_start = min(current_start, start_s)
                current_end = max(current_end, end_s)
            else:
                bundles.append(fe.loc[current_rows].copy())
                current_rows = [idx]
                current_start = start_s
                current_end = end_s

        if current_rows:
            bundles.append(fe.loc[current_rows].copy())

        return bundles


@dataclass(frozen=True)
class KeineBundleStrategy(BundleStrategy):
    mode: str = "keine"

    def build(self, events: pd.DataFrame) -> list[pd.DataFrame]:
        if events.empty:
            return []
        fe = events.sort_values(by=["start_s", "end_s"]).copy()
        # No combo-time bundling: each event stays isolated.
        return [bg.copy() for _, bg in fe.groupby(fe.index, sort=False)]


def make_bundle_strategy(mode: Literal["keine", "exact", "overlap"]) -> BundleStrategy:
    if mode == "keine":
        return KeineBundleStrategy()
    if mode == "exact":
        return ExactBundleStrategy()
    if mode == "overlap":
        return OverlapBundleStrategy()
    raise ValueError(f"Invalid mode '{mode}'. Use 'keine', 'exact' or 'overlap'.")
