import pandas as pd
from typing import List, Any

from data_classes import TimeFrame, PatternResult
from time_converter import TimeConverter
from sequence_analyzer import SequenceAnalyzer

pd.set_option("display.max_columns", None)


class PatternDetector:
    """Main class for detecting temporal patterns in coded educational data."""

    def __init__(self, time_tolerance: float = 0.1, sequence_scope: str = "legacy",
                 strict_codes=None, extraction_exclusions=None):
        """
        Initialize the pattern detector.

        Args:
            time_tolerance (float): Tolerance in seconds for timeframe matching
        """
        self.time_converter = TimeConverter()
        self.time_tolerance = time_tolerance
        self.sequence_analyzer = SequenceAnalyzer()
        if sequence_scope not in {"legacy", "care-overlap"}:
            raise ValueError(f"Unknown sequence scope: {sequence_scope}")
        self.sequence_scope = sequence_scope
        self.strict_codes = strict_codes
        self.extraction_exclusions = extraction_exclusions

    def _are_timeframes_equal(self, tf1: TimeFrame, tf2: TimeFrame) -> bool:
        """
        Check if two timeframes are equal within tolerance.

        Args:
            tf1 (TimeFrame): First timeframe
            tf2 (TimeFrame): Second timeframe

        Returns:
            bool: True if timeframes are equal within tolerance
        """
        if tf1.start is None or tf1.end is None or tf2.start is None or tf2.end is None:
            return False
        return tf1.start <= tf2.start and tf1.end >= tf2.end

    def _is_contained(
        self, container: TimeFrame, contained: TimeFrame, tolerance_ms: int = 100
    ) -> bool:
        """
        Check if one timeframe is contained within another (with tolerance).

        Args:
            container: The outer timeframe
            contained: The inner timeframe
            tolerance_ms: Allow contained to extend this many ms outside container
        """
        return (container.start <= contained.start + tolerance_ms) and (
            container.end >= contained.end - tolerance_ms
        )

    def _filter_codes_by_pattern(self, df: pd.DataFrame, pattern: str) -> pd.DataFrame:
        """
        Filter dataframe rows by code pattern.

        Args:
            df (pd.DataFrame): Input dataframe
            pattern (str): Code pattern to filter (e.g., '5.4.')

        Returns:
            pd.DataFrame: Filtered dataframe with added timeframe column
        """
        filtered_df = df[df["Code"].str.startswith(pattern, na=False)].copy()
        if not filtered_df.empty:
            filtered_df["timeframe"] = filtered_df.apply(
                lambda row: TimeFrame(
                    start=self.time_converter.time_string_to_milliseconds(
                        row["Anfang"]
                    ),
                    end=self.time_converter.time_string_to_milliseconds(row["Ende"]),
                    original_start=row["Anfang"],
                    original_end=row["Ende"],
                ),
                axis=1,
            )
        else:
            print("Could not find any matching pattern: " + pattern)
        if pattern == "6.2." and len(filtered_df) > 1:
            print("Found more than one matching patterns: " + pattern)
            print(filtered_df)
        return filtered_df

    def detect_external_pattern(
        self, df: pd.DataFrame, part_df: pd.DataFrame, search_type: str
    ) -> list[dict[str, str | TimeFrame | list[Any] | None]]:
        codes = []
        for _, row in part_df.iterrows():
            sequence_events = self.sequence_analyzer.get_sequence_events(
                df, None, search_type=search_type
            )
            # Format sequence for output
            sequence_list = [
                {
                    "code": event.code,
                    "start": event.original_start,
                    "end": event.original_end,
                }
                for event in sequence_events
            ]
            codes.append(
                {
                    "code": row["Code"],
                    "start": row["Anfang"],
                    "end": row["Ende"],
                    "sequence_events": sequence_list,
                    "sequence_count": len(sequence_list),
                }
            )
        if len(codes):
            return [
                {
                    "code": search_type.capitalize(),
                    "start": codes[0]["start"],
                    "end": codes[-1]["end"],
                    "timeframe": TimeFrame(
                        start=self.time_converter.time_string_to_milliseconds(
                            codes[0]["start"]
                        ),
                        end=self.time_converter.time_string_to_milliseconds(
                            codes[-1]["end"]
                        ),
                        original_end=codes[0]["start"],
                        original_start=codes[-1]["end"],
                    ),
                    f"matching_{search_type}_codes": codes,
                }
            ]
        return []

    def detect_patterns(self, df: pd.DataFrame, filename: str) -> List[PatternResult]:
        """
        Detect patterns where 5.4.* codes contain 6.1.1 codes with matching 6.2.* and 5.5.* codes.

        Pattern: 5.4.* codes contain 6.1.1 codes, which may have:
                 - 6.2.* codes with identical timeframes
                 - 5.5.* codes with identical timeframes
        Additionally, analyze sequence of target codes within 6.2.* timeframes.

        Args:
            df (pd.DataFrame): Dataframe containing coded events
            filename (str): Source filename for reference

        Returns:
            List[PatternResult]: List of detected patterns
        """
        if self.sequence_scope == "care-overlap":
            from care_overlap import extract_care_patterns
            return extract_care_patterns(df, filename, self.strict_codes, self.extraction_exclusions)
        results = []
        # Filter relevant code types
        df_5_4 = self._filter_codes_by_pattern(df, "5.4.")  # setting
        df_6_1_1 = self._filter_codes_by_pattern(df, "6.1.1")  # situation
        df_6_2 = self._filter_codes_by_pattern(df, "6.2.")  # type
        df_5_5 = self._filter_codes_by_pattern(df, "5.5.")  # child
        df_1_1_1 = self._filter_codes_by_pattern(df, "1.1.1")  # valence
        df_1_1_2 = self._filter_codes_by_pattern(df, "1.1.2")  # arousal
        df_5_3 = self._filter_codes_by_pattern(df, "5.3")  # talking
        df_1_2_0 = self._filter_codes_by_pattern(df, "1.2.0")  # body orientation
        talking_codes_list = self.detect_external_pattern(
            df=df, part_df=df_5_3, search_type="talking"
        )
        if len(df_6_2) > 1:
            print(f"extracted more than one 6_2_* codes: {len(df_6_2)}")
            print(df_6_2.head())
            print(f"extracted more than one 6_1_1 codes: {len(df_6_1_1)}")
            print(df_6_1_1.head())
        results.append(
            PatternResult(
                filename=filename,
                parent_code="Talking",
                parent_timeframe=TimeFrame(
                    start=0, end=10, original_end="", original_start=""
                ),
                child_codes=talking_codes_list,
            )
        )

        body_codes_list = self.detect_external_pattern(
            df=df, part_df=df_1_2_0, search_type="body"
        )

        results.append(
            PatternResult(
                filename=filename,
                parent_code="Body Orientation",
                parent_timeframe=TimeFrame(
                    start=0, end=10, original_end="", original_start=""
                ),
                child_codes=body_codes_list,
            )
        )

        valence_codes_list = self.detect_external_pattern(
            df=df, part_df=df_1_1_1, search_type="valence"
        )

        arousal_codes_list = self.detect_external_pattern(
            df=df, part_df=df_1_1_2, search_type="arousal"
        )

        valence_codes_list.extend(arousal_codes_list)

        results.append(
            PatternResult(
                filename=filename,
                parent_code="Valence and Arousal Codes",
                parent_timeframe=TimeFrame(
                    start=0, end=10, original_end="", original_start=""
                ),
                child_codes=valence_codes_list,
            )
        )

        # If there are no 5.4.* codes, we can still match 6.1.1 ↔ 6.2.* (and 5.5.*)
        if df_5_4.empty and not df_6_1_1.empty:
            print("detected special case")
            orphan_6_1_1_list: list[dict[str, Any]] = []

            for _, row_6_1_1 in df_6_1_1.iterrows():
                tf_6_1_1 = row_6_1_1["timeframe"]
                if tf_6_1_1.start is None or tf_6_1_1.end is None:
                    continue

                matching_6_2_codes = self._find_matching_6_2_with_sequences(
                    df, df_6_2, tf_6_1_1
                )
                print(f"matched {len(matching_6_2_codes)} 6_2 codes in special case")
                matching_5_5_codes = self._find_matching_codes_same_timeframe(
                    df_5_5, tf_6_1_1
                )
                print(f"matched {len(matching_5_5_codes)} 5_5 codes in special case")

                orphan_6_1_1_list.append(
                    {
                        "code": row_6_1_1["Code"],
                        "start": row_6_1_1["Anfang"],
                        "end": row_6_1_1["Ende"],
                        "timeframe": tf_6_1_1,
                        "matching_6_2_codes": matching_6_2_codes,
                        "matching_5_5_codes": matching_5_5_codes,
                    }
                )

            results.append(
                PatternResult(
                    filename=filename,
                    parent_code="6.1.1 (no 5.4 parent found)",
                    parent_timeframe=TimeFrame(
                        start=0, end=0, original_start="", original_end=""
                    ),
                    child_codes=orphan_6_1_1_list,
                )
            )

        # Check each 5.4.* code for contained 6.1.1 codes
        print("checking 5.4. for contained 6.1.")
        for _, row_5_4 in df_5_4.iterrows():
            parent_timeframe = row_5_4["timeframe"]
            print(f"looking at {parent_timeframe}")

            if parent_timeframe.start is None or parent_timeframe.end is None:
                continue

            contained_6_1_1_list = []

            # Check all 6.1.1 codes within this 5.4.* timeframe
            for _, row_6_1_1 in df_6_1_1.iterrows():
                child_timeframe = row_6_1_1["timeframe"]
                print(f"looking at child {child_timeframe}")
                if child_timeframe.start is None or child_timeframe.end is None:
                    continue

                if self._is_contained(parent_timeframe, child_timeframe):
                    print(
                        f"found contained 6_1: {child_timeframe} in {parent_timeframe}"
                    )
                    # Look for matching 6.2.* codes with exact same timeframe
                    matching_6_2_codes = []
                    if len(matching_6_2_codes) > 1:
                        print("found more than one matching 6_2 code")
                    for _, row_6_2 in df_6_2.iterrows():
                        match_timeframe = row_6_2["timeframe"]

                        if match_timeframe.start is None or match_timeframe.end is None:
                            continue

                        if self._are_timeframes_equal(child_timeframe, match_timeframe):
                            # Analyze sequence of target codes within this 6.2 timeframe
                            sequence_events = (
                                self.sequence_analyzer.get_sequence_events(
                                    df, match_timeframe, search_type="all"
                                )
                            )

                            # Format sequence for output
                            sequence_list = [
                                {
                                    "code": event.code,
                                    "start": event.original_start,
                                    "end": event.original_end,
                                }
                                for event in sequence_events
                            ]

                            matching_6_2_codes.append(
                                {
                                    "code": row_6_2["Code"],
                                    "start": row_6_2["Anfang"],
                                    "end": row_6_2["Ende"],
                                    "sequence_events": sequence_list,
                                    "sequence_count": len(sequence_list),
                                }
                            )

                    # Look for matching 5.5.* codes with exact same timeframe as 6.1.1
                    matching_5_5_codes = []
                    for _, row_5_5 in df_5_5.iterrows():
                        match_timeframe = row_5_5["timeframe"]

                        if match_timeframe.start is None or match_timeframe.end is None:
                            continue

                        if self._are_timeframes_equal(child_timeframe, match_timeframe):
                            matching_5_5_codes.append(
                                {
                                    "code": row_5_5["Code"],
                                    "start": row_5_5["Anfang"],
                                    "end": row_5_5["Ende"],
                                }
                            )

                    contained_6_1_1_list.append(
                        {
                            "code": row_6_1_1["Code"],
                            "start": row_6_1_1["Anfang"],
                            "end": row_6_1_1["Ende"],
                            "timeframe": child_timeframe,
                            "matching_6_2_codes": matching_6_2_codes,
                            "matching_5_5_codes": matching_5_5_codes,
                        }
                    )
                else:
                    print(f"{child_timeframe} not found in {parent_timeframe}")
            if contained_6_1_1_list:
                results.append(
                    PatternResult(
                        filename=filename,
                        parent_code=row_5_4["Code"],
                        parent_timeframe=parent_timeframe,
                        child_codes=contained_6_1_1_list,
                    )
                )

        return results

    def _find_matching_codes_same_timeframe(
        self,
        df_with_timeframe: pd.DataFrame,
        target_timeframe: TimeFrame,
    ) -> list[dict[str, str]]:
        """Return codes whose timeframe matches target_timeframe within tolerance."""
        matches: list[dict[str, str]] = []
        for _, row in df_with_timeframe.iterrows():
            tf = row["timeframe"]
            if tf.start is None or tf.end is None:
                continue
            if self._are_timeframes_equal(target_timeframe, tf):
                matches.append(
                    {"code": row["Code"], "start": row["Anfang"], "end": row["Ende"]}
                )
        return matches

    def _find_matching_6_2_with_sequences(
        self, df: pd.DataFrame, df_6_2: pd.DataFrame, tf_6_1_1: TimeFrame
    ) -> list[dict[str, Any]]:
        """Return 6.2.* codes matching tf_6_1_1 and include sequence events for each match."""
        matching_6_2_codes: list[dict[str, Any]] = []

        for _, row_6_2 in df_6_2.iterrows():
            match_tf = row_6_2["timeframe"]
            if match_tf.start is None or match_tf.end is None:
                continue

            if self._are_timeframes_equal(tf_6_1_1, match_tf):
                sequence_events = self.sequence_analyzer.get_sequence_events(
                    df, match_tf, search_type="all"
                )
                sequence_list = [
                    {"code": e.code, "start": e.original_start, "end": e.original_end}
                    for e in sequence_events
                ]
                matching_6_2_codes.append(
                    {
                        "code": row_6_2["Code"],
                        "start": row_6_2["Anfang"],
                        "end": row_6_2["Ende"],
                        "sequence_events": sequence_list,
                        "sequence_count": len(sequence_list),
                    }
                )

        return matching_6_2_codes
