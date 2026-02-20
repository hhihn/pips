from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from src.sunburst.helper import parse_time_to_seconds


class EventTimeType(str, Enum):
    POINT = "point"
    INTERVAL = "interval"


@dataclass(frozen=True)
class TimeSeriesSchema:
    code_col: str = "Sequence_Code"
    source_col: str = "Filename"
    case_id_col: str = "id"
    start_col: str = "Sequence_Start"
    end_col: str = "Sequence_End"
    timestamp_col: str | None = None


@dataclass(frozen=True)
class TemporalEvent:
    event_code: str
    source_id: str
    case_id: str
    start_seconds: float
    end_seconds: float

    @property
    def event_time_type(self) -> EventTimeType:
        if self.start_seconds == self.end_seconds:
            return EventTimeType.POINT
        return EventTimeType.INTERVAL


@dataclass(frozen=True)
class TimeSeriesDataset:
    events: list[TemporalEvent]

    def to_dataframe(self) -> pd.DataFrame:
        rows = []
        for event in self.events:
            rows.append(
                {
                    "event_code": event.event_code,
                    "source_id": event.source_id,
                    "case_id": event.case_id,
                    "start_seconds": event.start_seconds,
                    "end_seconds": event.end_seconds,
                    "event_time_type": event.event_time_type.value,
                }
            )
        return pd.DataFrame(rows)

    def to_legacy_dataframe(self) -> pd.DataFrame:
        rows = []
        for event in self.events:
            rows.append(
                {
                    "Sequence_Code": event.event_code,
                    "Filename": event.source_id,
                    "id": event.case_id,
                    "Sequence_Start": _seconds_to_legacy_time(event.start_seconds),
                    "Sequence_End": _seconds_to_legacy_time(event.end_seconds),
                }
            )
        return pd.DataFrame(rows)


def parse_temporal_value(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        raise ValueError("Missing temporal value.")

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)

    if isinstance(value, pd.Timestamp):
        return float(value.timestamp())

    if isinstance(value, pd.Timedelta):
        return float(value.total_seconds())

    s = str(value).strip()
    if not s:
        raise ValueError("Empty temporal value.")

    try:
        return float(s.replace(",", "."))
    except Exception:
        pass

    try:
        return parse_time_to_seconds(s)
    except Exception:
        pass

    td = pd.to_timedelta(s, errors="coerce")
    if pd.notna(td):
        return float(td.total_seconds())

    ts = pd.to_datetime(s, errors="coerce")
    if pd.notna(ts):
        return float(ts.timestamp())

    raise ValueError(f"Unsupported temporal format: {value!r}")


def _seconds_to_legacy_time(value: float) -> str:
    seconds = float(value)
    if seconds < 0:
        raise ValueError("Negative timestamps are not supported in legacy output.")

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    sec = seconds - (hours * 3600) - (minutes * 60)
    return f"{hours:02d}:{minutes:02d}:{sec:06.3f}"
