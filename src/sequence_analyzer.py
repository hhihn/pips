import pandas as pd
from typing import List

from data_classes import TimeFrame, SequenceEvent
from time_converter import TimeConverter


class SequenceAnalyzer:
    """Analyzes temporal sequences of codes within specific timeframes."""

    # Target code ranges and individual codes to track
    TARGET_INDIVIDUAL_CODES = [
        "2.1.1.1",
        "2.1.1.2",
        "2.1.1.3",
        "2.1.1.4",
        "2.1.2.1",
        "2.1.2.2",
        "2.1.2.3",
        "2.1.2.5",
        "2.1.2.6",
        "2.1.2.7",
        "2.1.2.8",
        "2.1.2.9",
        "2.1.2.10",
        "2.1.2.11",
        "2.1.3.1",
        "2.1.3.2",
        "2.1.3.3",
        "2.1.3.4",
        "2.1.3.5",
        "2.1.3.6",
        "6.1.2",
        "6.1.3",
        "6.1.4",
        "6.4.1",
        "6.4.2",
        "6.4.3",
        "6.4.4",
        "6.4.5"
        "6.5.1",
        "6.5.2",
        "6.5.3",
        "6.5.4",
        "5.2.1",
        "5.2.2",
        "1.2.0.1",
        "1.2.0.2",
        "1.2.0.3",
        "1.2.0.4",
        "1.2.0.5",
        "1.2.0.6",
        "5.3.1",  # Talking
        "5.3.2",
        "5.3.3",
    ]

    # Specific code groups to analyze ordering
    VALENCE_CODES = ["1.1.1.1", "1.1.1.2", "1.1.1.3", "1.1.1.4"]
    AROUSAL_CODES = ["1.1.2.1", "1.1.2.2", "1.1.2.3"]
    BODY_ORIENTATION = [
        "1.2.0.1",
        "1.2.0.2",
        "1.2.0.3",
        "1.2.0.4",
    ]
    TALKING = ["5.3.1", "5.3.2", "5.3.3"]

    @classmethod
    def is_target_code(cls, code: str, search_type="targets") -> bool:
        """
        Check if a code belongs to target ranges or individual codes.

        Args:
            code (str): Code to check

        Returns:
            bool: True if code is a target code
        """
        # Check individual codes
        if search_type == "valence":
            target_list = cls.VALENCE_CODES
        elif search_type == "arousal":
            target_list = cls.AROUSAL_CODES
        elif search_type == "body":
            target_list = cls.BODY_ORIENTATION
        elif search_type == "talking":
            target_list = cls.TALKING
        else:
            target_list = cls.TARGET_INDIVIDUAL_CODES

        for target_code in target_list:
            if code.startswith(target_code):
                return True

        return False

    @staticmethod
    def _is_in_range(code: str, start_range: str, end_range: str) -> bool:
        """
        Check if a code falls within a numeric range.

        Args:
            code (str): Code to check
            start_range (str): Start of range (inclusive)
            end_range (str): End of range (inclusive)

        Returns:
            bool: True if code is in range
        """
        try:
            if not code.startswith(start_range[:4]):  # Same prefix check
                return False

            # Extract numeric parts and compare
            code_parts = code.split(".")
            start_parts = start_range.split(".")
            end_parts = end_range.split(".")

            if len(code_parts) < 3 or len(start_parts) < 3 or len(end_parts) < 3:
                return False

            # Compare major.minor.patch style numbering
            code_num = tuple(
                int(part) if part.isdigit() else 0 for part in code_parts[:3]
            )
            start_num = tuple(
                int(part) if part.isdigit() else 0 for part in start_parts[:3]
            )
            end_num = tuple(
                int(part) if part.isdigit() else 0 for part in end_parts[:3]
            )

            return start_num <= code_num <= end_num
        except (ValueError, IndexError):
            return False

    @classmethod
    def get_sequence_events(
        cls, df: pd.DataFrame, timeframe: TimeFrame | None, search_type: str = "targets"
    ) -> List[SequenceEvent]:
        """
        Extract sequence of target codes within a timeframe, ordered by start time.

        Args:
            df (pd.DataFrame): Full dataset
            timeframe (TimeFrame): Timeframe to analyze

        Returns:
            List[SequenceEvent]: Ordered list of sequence events
        """
        sequence_events = []

        converter = TimeConverter()

        for _, row in df.iterrows():
            code = str(row.get("Code", ""))
            start_str = str(row.get("Anfang", ""))
            end_str = str(row.get("Ende", ""))

            # Check if this is a target code
            if search_type != "all" and not cls.is_target_code(
                code, search_type=search_type
            ):
                continue

            # Convert times
            start_time = converter.time_string_to_milliseconds(start_str)
            end_time = converter.time_string_to_milliseconds(end_str)

            if start_time is None or end_time is None:
                continue

            # Check if event is within the timeframe
            if (
                not timeframe
                or start_time >= timeframe.start
                and end_time <= timeframe.end
            ):
                sequence_events.append(
                    SequenceEvent(
                        code=code,
                        start_time=start_time,
                        end_time=end_time,
                        original_start=start_str,
                        original_end=end_str,
                    )
                )

        # Sort by start time
        sequence_events.sort(key=lambda x: x.start_time)
        return sequence_events
