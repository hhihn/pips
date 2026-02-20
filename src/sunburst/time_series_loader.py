from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from src.sunburst.time_series_model import (
    TemporalEvent,
    TimeSeriesDataset,
    TimeSeriesSchema,
    parse_temporal_value,
)


@dataclass
class TimeSeriesLoader:
    schema: TimeSeriesSchema = TimeSeriesSchema()

    def from_csv(self, csv_path: str | Path) -> TimeSeriesDataset:
        df = pd.read_csv(csv_path)
        return self.from_dataframe(df)

    def from_dataframe(self, df: pd.DataFrame) -> TimeSeriesDataset:
        self._validate_columns(df)

        events: list[TemporalEvent] = []
        for idx, row in df.iterrows():
            code = str(row[self.schema.code_col]).strip()
            if not code:
                raise ValueError(f"Row {idx}: empty event code.")

            source = str(row.get(self.schema.source_col, "")).strip() or "unknown_source"
            case_id = str(row.get(self.schema.case_id_col, "")).strip() or ""

            start_s, end_s = self._resolve_times(row, idx)
            if end_s < start_s:
                raise ValueError(
                    f"Row {idx}: end time ({end_s}) is smaller than start time ({start_s})."
                )

            events.append(
                TemporalEvent(
                    event_code=code,
                    source_id=source,
                    case_id=case_id,
                    start_seconds=start_s,
                    end_seconds=end_s,
                )
            )

        return TimeSeriesDataset(events=events)

    def load_analysis_dataframe(self, csv_path: str | Path) -> pd.DataFrame:
        dataset = self.from_csv(csv_path)
        return dataset.to_legacy_dataframe()

    def _validate_columns(self, df: pd.DataFrame) -> None:
        required = {self.schema.code_col, self.schema.source_col}

        has_interval = self.schema.start_col in df.columns and self.schema.end_col in df.columns
        has_point = self.schema.timestamp_col is not None and self.schema.timestamp_col in df.columns

        if not has_interval and not has_point:
            raise ValueError(
                "No valid time columns found. Expected either "
                f"('{self.schema.start_col}', '{self.schema.end_col}') "
                f"or timestamp column '{self.schema.timestamp_col}'."
            )

        missing = [col for col in required if col not in df.columns]
        if missing:
            raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    def _resolve_times(self, row: pd.Series, idx: int) -> tuple[float, float]:
        if self.schema.start_col in row and self.schema.end_col in row:
            try:
                start_s = parse_temporal_value(row[self.schema.start_col])
                end_s = parse_temporal_value(row[self.schema.end_col])
                return start_s, end_s
            except Exception as exc:
                raise ValueError(f"Row {idx}: invalid interval values: {exc}") from exc

        if self.schema.timestamp_col is not None and self.schema.timestamp_col in row:
            try:
                ts = parse_temporal_value(row[self.schema.timestamp_col])
                return ts, ts
            except Exception as exc:
                raise ValueError(f"Row {idx}: invalid timestamp value: {exc}") from exc

        raise ValueError(
            f"Row {idx}: missing temporal values. "
            f"Expected start/end or timestamp column '{self.schema.timestamp_col}'."
        )
