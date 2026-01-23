from typing import List, Dict
from dataclasses import dataclass


@dataclass
class TimeFrame:
    """Represents a time interval with start and end times."""

    start: int
    end: int
    original_start: str
    original_end: str


@dataclass
class PatternResult:
    """Represents a detected pattern instance."""

    filename: str
    parent_code: str
    parent_timeframe: TimeFrame
    child_codes: List[Dict]  # List of 6.1.1 codes with their matching codes


@dataclass
class SequenceEvent:
    """Represents a single event in a temporal sequence."""

    code: str
    start_time: float
    end_time: float
    original_start: str
    original_end: str
