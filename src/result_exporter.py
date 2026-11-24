import pandas as pd
from pathlib import Path
from typing import List
from datetime import datetime

from data_classes import PatternResult
from time_converter import TimeConverter


class ResultExporter:
    """Handles exporting detection results to various formats."""

    def __init__(self, output_dir: Path):
        """
        Initialize the result exporter.

        Args:
            output_dir (Path): Directory for output files
        """
        self.output_dir = output_dir
        self.output_dir.mkdir(exist_ok=True)
        self.time_converter = TimeConverter()

    def export_to_csv(self, results: List[PatternResult], filename: str) -> None:
        """
        Export results to CSV format.

        Args:
            results (List[PatternResult]): Detection results
            filename (str): Output filename
        """
        if not results:
            return

        # Flatten results for CSV export
        flattened_data = []

        for result in results:
            parent_info = {
                "Filename": result.filename,
                "Parent_Code": result.parent_code,
                "Parent_Start": result.parent_timeframe.original_start,
                "Parent_End": result.parent_timeframe.original_end,
            }

            for child_code in result.child_codes:
                entry = parent_info.copy()
                entry.update(
                    {
                        "Child_Code": child_code["code"],
                        "Child_Start": child_code["start"],
                        "Child_End": child_code["end"],
                        "Child Duration": self.time_converter.time_string_to_milliseconds(
                            child_code["end"]
                        )
                        - self.time_converter.time_string_to_milliseconds(
                            child_code["start"]
                        ),
                        "Has_Matching_6_2": "matching_6_2_codes" in child_code
                        and len(child_code["matching_6_2_codes"]) > 0,
                        "Matching_6_2_Count": "matching_6_2_codes" in child_code
                        and len(child_code["matching_6_2_codes"]),
                        "Has_Matching_5_5": "matching_5_5_codes" in child_code
                        and len(child_code["matching_5_5_codes"]) > 0,
                        "Matching_5_5_Count": "matching_5_5_codes" in child_code
                        and len(child_code["matching_5_5_codes"]),
                    }
                )
                flattened_data.append(entry)

        if flattened_data:
            df_export = pd.DataFrame(flattened_data)
            output_path = self.output_dir / filename
            df_export.to_csv(output_path, index=False, encoding="utf-8")

    def export_detailed_results(self, results: List[PatternResult]) -> None:
        """
        Export detailed results including all matched codes and sequence analysis.

        Args:
            results (List[PatternResult]): Detection results
        """
        if not results:
            return

        detailed_data = []
        matched_pairs_data = []
        sequence_analysis_data = []
        five_five_analysis_data = []

        for result in results:
            base_info = {
                "Filename": result.filename,
                "Parent_Code": result.parent_code,
                "Parent_Start": result.parent_timeframe.original_start,
                "Parent_End": result.parent_timeframe.original_end,
            }

            for child_code in result.child_codes:
                # Basic entry
                entry = base_info.copy()
                entry.update(
                    {
                        "Child_Code": child_code["code"],
                        "Child_Start": child_code["start"],
                        "Child_End": child_code["end"],
                        "Child Duration": self.time_converter.time_string_to_milliseconds(
                            child_code["end"]
                        )
                        - self.time_converter.time_string_to_milliseconds(
                            child_code["start"]
                        ),
                        "Has_Matching_6_2": "matching_6_2_codes" in child_code
                        and len(child_code["matching_6_2_codes"]) > 0,
                        "Has_Matching_5_5": "matching_5_5_codes" in child_code
                        and len(child_code["matching_5_5_codes"]) > 0,
                    }
                )

                # Handle 6.2.* matching codes
                if (
                    "matching_6_2_codes" in child_code
                    and child_code["matching_6_2_codes"]
                ):
                    for match_6_2 in child_code["matching_6_2_codes"]:
                        detailed_entry = entry.copy()
                        detailed_entry.update(
                            {
                                "Matched_Code_Type": "6.2.*",
                                "Matched_Code": match_6_2["code"],
                                "Matched_Start": match_6_2["start"],
                                "Matched_End": match_6_2["end"],
                                "Matched Duration": self.time_converter.time_string_to_milliseconds(
                                    match_6_2["end"]
                                )
                                - self.time_converter.time_string_to_milliseconds(
                                    match_6_2["start"]
                                ),
                                "Additional_Info": f"Sequence Events: {match_6_2['sequence_count']}",
                            }
                        )
                        detailed_data.append(detailed_entry)
                        matched_pairs_data.append(detailed_entry)

                        # Add sequence analysis records
                        if match_6_2["sequence_events"]:
                            for i, seq_event in enumerate(
                                match_6_2["sequence_events"], 1
                            ):
                                sequence_record = detailed_entry.copy()
                                sequence_record.update(
                                    {
                                        "Sequence_Order": i,
                                        "Sequence_Code": seq_event["code"],
                                        "Sequence_Start": seq_event["start"],
                                        "Sequence_End": seq_event["end"],
                                        "Sequence Duration": self.time_converter.time_string_to_milliseconds(
                                            seq_event["end"]
                                        )
                                        - self.time_converter.time_string_to_milliseconds(
                                            seq_event["start"]
                                        ),
                                    }
                                )
                                sequence_analysis_data.append(sequence_record)
                        else:
                            # Record for no sequence events
                            sequence_record = detailed_entry.copy()
                            sequence_record.update(
                                {
                                    "Sequence_Order": 0,
                                    "Sequence_Code": None,
                                    "Sequence_Start": None,
                                    "Sequence_End": None,
                                }
                            )
                            sequence_analysis_data.append(sequence_record)
                else:
                    # No matching 6.2 codes
                    entry.update(
                        {
                            "Matched_Code_Type": "6.2.*",
                            "Matched_Code": None,
                            "Matched_Start": None,
                            "Matched_End": None,
                            "Matched Duration": None,
                            "Additional_Info": "No matching 6.2.* found",
                        }
                    )
                    detailed_data.append(entry)

                # Handle 5.5.* matching codes
                if (
                    "matching_5_5_codes" in child_code
                    and child_code["matching_5_5_codes"]
                ):
                    for match_5_5 in child_code["matching_5_5_codes"]:
                        detailed_entry = entry.copy()
                        detailed_entry.update(
                            {
                                "Matched_Code_Type": "5.5.*",
                                "Matched_Code": match_5_5["code"],
                                "Matched_Start": match_5_5["start"],
                                "Matched_End": match_5_5["end"],
                                "Additional_Info": "Exact timeframe match with 6.1.1",
                            }
                        )
                        detailed_data.append(detailed_entry)
                        five_five_analysis_data.append(detailed_entry)
                else:
                    # No matching 5.5 codes
                    entry.update(
                        {
                            "Matched_Code_Type": "5.5.*",
                            "Matched_Code": None,
                            "Matched_Start": None,
                            "Matched_End": None,
                            "Additional_Info": "No matching 5.5.* found",
                        }
                    )
                    if (
                        "matching_6_2_codes" not in child_code
                        or not child_code["matching_6_2_codes"]
                    ):  # Only add once if no 6.2 either
                        detailed_data.append(entry)

        # Export files
        if detailed_data:
            df_detailed = pd.DataFrame(detailed_data)
            df_detailed.to_csv(
                self.output_dir / "detailed_analysis.csv", index=False, encoding="utf-8"
            )
        print("No Detailed Data")

        if matched_pairs_data:
            df_matched_6_2 = pd.DataFrame(matched_pairs_data)
            df_matched_6_2.to_csv(
                self.output_dir / "matched_6_2_pairs.csv", index=False, encoding="utf-8"
            )
        else:
            print("No Matched Pairs Data")

        if five_five_analysis_data:
            df_matched_5_5 = pd.DataFrame(five_five_analysis_data)
            df_matched_5_5.to_csv(
                self.output_dir / "matched_5_5_pairs.csv", index=False, encoding="utf-8"
            )
        else:
            print("No Five Analysis Data")

        if sequence_analysis_data:
            df_sequence = pd.DataFrame(sequence_analysis_data)
            df_sequence.to_csv(
                self.output_dir / "sequence_analysis.csv", index=False, encoding="utf-8"
            )
        else:
            print("No Sequence Analysis Data")

    def export_externa_code_results(self, f, child_code: dict) -> None:
        """
        Export matched valence and arousal results.

        :param f: open file
        :param child_code: dict with data
        :return: None
        """
        if (
            "matching_valence_codes" in child_code
            and child_code["matching_valence_codes"]
        ):
            f.write(
                f"      ↔ 1.1.1.* Matches ({len(child_code['matching_valence_codes'])}):\n"
            )
            for match in child_code["matching_valence_codes"]:
                f.write(
                    f"          {match['code']} ({match['start']} - {match['end']})\n"
                )

        if (
            "matching_arousal_codes" in child_code
            and child_code["matching_arousal_codes"]
        ):
            f.write(
                f"      ↔ 1.1.2.* Matches ({len(child_code['matching_arousal_codes'])}):\n"
            )
            for match in child_code["matching_arousal_codes"]:
                f.write(
                    f"          {match['code']} ({match['start']} - {match['end']})\n"
                )

        if "matching_body_codes" in child_code and child_code["matching_body_codes"]:
            f.write(
                f"      ↔ 1.0.2.* Matches ({len(child_code['matching_body_codes'])}):\n"
            )
            for match in child_code["matching_body_codes"]:
                f.write(
                    f"          {match['code']} ({match['start']} - {match['end']})\n"
                )

        if (
            "matching_talking_codes" in child_code
            and child_code["matching_talking_codes"]
        ):
            f.write(
                f"      ↔ 5.3.2 Matches ({len(child_code['matching_talking_codes'])}):\n"
            )
            for match in child_code["matching_talking_codes"]:
                f.write(
                    f"          {match['code']} ({match['start']} - {match['end']})\n"
                )

    def export_summary_report(self, results: List[PatternResult]) -> None:
        """
        Export human-readable summary report including all matched codes and sequences.

        Args:
            results (List[PatternResult]): Detection results
        """
        if not results:
            return

        summary_path = self.output_dir / "analysis_summary.txt"

        # Calculate statistics
        total_6_1_1 = sum(len(result.child_codes) for result in results)

        matched_6_2_stats = sum(
            len(
                [
                    c
                    for c in result.child_codes
                    if "matching_6_2_codes" in c and c["matching_6_2_codes"]
                ]
            )
            for result in results
        )

        matched_5_5_stats = sum(
            len(
                [
                    c
                    for c in result.child_codes
                    if "matching_5_5_codes" in c and c["matching_5_5_codes"]
                ]
            )
            for result in results
        )

        # Calculate sequence statistics
        total_sequences = 0
        files_with_sequences = set()

        for result in results:
            for child_code in result.child_codes:
                for match_6_2 in child_code.get("matching_6_2_codes", []):
                    sequence_count = match_6_2.get("sequence_count", 0)
                    if sequence_count > 0:
                        total_sequences += sequence_count
                        files_with_sequences.add(result.filename)

        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("Educational Coding Pattern Analysis Report\n")
            f.write("=" * 50 + "\n")
            f.write(
                f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            )

            f.write("SUMMARY STATISTICS\n")
            f.write("-" * 20 + "\n")
            f.write(
                f"Files with detected patterns: {len(set(r.filename for r in results))}\n"
            )
            f.write(f"Files with sequences: {len(files_with_sequences)}\n")
            f.write(f"Total parent codes (5.4.*) with children: {len(results)}\n")
            f.write(f"Total child codes (6.1.1): {total_6_1_1}\n")
            f.write(f"With matching 6.2.* codes: {matched_6_2_stats}\n")
            f.write(f"With matching 5.5.* codes: {matched_5_5_stats}\n")
            f.write(
                f"Without matching 6.2.* codes: {total_6_1_1 - matched_6_2_stats}\n"
            )
            f.write(
                f"Without matching 5.5.* codes: {total_6_1_1 - matched_5_5_stats}\n"
            )
            f.write(f"Total sequence events found: {total_sequences}\n\n")

            f.write("ANALYZED CODE PATTERNS\n")
            f.write("-" * 25 + "\n")
            f.write("Parent Pattern: 5.4.* codes (contexts)\n")
            f.write("Child Pattern: 6.1.1 codes (within parent timeframe)\n")
            f.write("Matched Patterns:\n")
            f.write("  • 6.2.* codes (same timeframe as 6.1.1)\n")
            f.write("  • 5.5.* codes (same timeframe as 6.1.1)\n\n")

            f.write("SEQUENCE ANALYSIS TARGET CODES (within 6.2.* timeframes)\n")
            f.write("-" * 55 + "\n")
            f.write("Ranges:\n")
            f.write("  • 6.1.2 - 6.1.4\n")
            f.write("  • 6.5.1 - 6.5.4\n")
            f.write("Individual codes:\n")
            f.write("  • 5.2.1\n")
            f.write("  • 5.2.2\n\n")

            f.write("DETAILED FINDINGS\n")
            f.write("-" * 20 + "\n")
            for result in results:
                f.write(f"\nFile: {result.filename}\n")
                f.write(
                    f"  Parent: {result.parent_code} "
                    f"({result.parent_timeframe.original_start} - {result.parent_timeframe.original_end})\n"
                )

                for child_code in result.child_codes:
                    f.write(
                        f"    Child: {child_code['code']} "
                        f"({child_code['start']} - {child_code['end']})\n"
                    )
                    if (
                        "Arousal" not in result.parent_code
                        and "Valence" not in result.parent_code
                        and "Body" not in result.parent_code
                        and "Talking" not in result.parent_code
                    ):
                        # Show matching 6.2 codes and sequences
                        if (
                            "matching_6_2_codes" in child_code
                            and child_code["matching_6_2_codes"]
                        ):
                            for match_6_2 in child_code["matching_6_2_codes"]:
                                f.write(
                                    f"      ↔ 6.2.* Match: {match_6_2['code']} "
                                    f"({match_6_2['start']} - {match_6_2['end']})\n"
                                )

                                # Show sequence analysis
                                if match_6_2["sequence_events"]:
                                    f.write(
                                        f"      ↳ Sequence ({len(match_6_2['sequence_events'])} events):\n"
                                    )
                                    for i, seq_event in enumerate(
                                        match_6_2["sequence_events"], 1
                                    ):
                                        f.write(
                                            f"          {i}. {seq_event['code']} "
                                            f"({seq_event['start']} - {seq_event['end']})\n"
                                        )
                                else:
                                    f.write("      ↳ No sequence events found\n")
                        else:
                            f.write("      ↔ No matching 6.2.* code found\n")

                        # Show matching 5.5 codes
                        if (
                            "matching_5_5_codes" in child_code
                            and child_code["matching_5_5_codes"]
                        ):
                            f.write(
                                f"      ↔ 5.5.* Matches ({len(child_code['matching_5_5_codes'])}):\n"
                            )
                            for match_5_5 in child_code["matching_5_5_codes"]:
                                f.write(
                                    f"          {match_5_5['code']} "
                                    f"({match_5_5['start']} - {match_5_5['end']})\n"
                                )
                        else:
                            f.write("      ↔ No matching 5.5.* code found\n")
                    else:
                        self.export_externa_code_results(f=f, child_code=child_code)
