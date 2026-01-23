import pandas as pd
from pathlib import Path
from typing import List

from data_classes import PatternResult
from pattern_detector import PatternDetector
from result_exporter import ResultExporter


class PatternAnalyzer:
    """Main analyzer class that orchestrates the entire analysis pipeline."""

    def __init__(
        self, input_dir: str, output_dir: str = None, time_tolerance: float = 0.1
    ):
        """
        Initialize the pattern analyzer.

        Args:
            input_dir (str): Directory containing input Excel files
            output_dir (str, optional): Directory for output files
            time_tolerance (float): Time matching tolerance in seconds
        """
        self.input_dir = Path(input_dir)
        self.output_dir = (
            Path(output_dir) if output_dir else self.input_dir / "analysis_results"
        )
        self.detector = PatternDetector(time_tolerance=time_tolerance)
        self.exporter = ResultExporter(self.output_dir)

        # Validate input directory
        if not self.input_dir.exists():
            raise FileNotFoundError(f"Input directory '{input_dir}' does not exist.")

    def get_excel_files(self) -> List[Path]:
        """
        Get list of Excel files in input directory.

        Returns:
            List[Path]: List of Excel file paths
        """
        excel_extensions = [".xlsx", ".xls"]
        return [
            f
            for f in self.input_dir.iterdir()
            if (
                f.is_file()
                and f.suffix.lower() in excel_extensions
                and "analysis_results" not in str(f)
            )
        ]

    def analyze_file(self, file_path: Path) -> List[PatternResult]:
        """
        Analyze a single Excel file.

        Args:
            file_path (Path): Path to the Excel file

        Returns:
            List[PatternResult]: Detected patterns
        """
        try:
            df = pd.read_excel(file_path)
            return self.detector.detect_patterns(df, file_path.name)
        except Exception as e:
            print(f"Error analyzing {file_path.name}: {str(e)}")
            return []

    def run_analysis(self) -> List[PatternResult]:
        """
        Run complete analysis on all Excel files in the input directory.

        Returns:
            List[PatternResult]: All detected patterns across all files
        """
        print("Starting pattern analysis with extended matching...")

        excel_files = self.get_excel_files()
        if not excel_files:
            print(f"No Excel files found in {self.input_dir}")
            return []

        print(f"Found {len(excel_files)} Excel file(s) to process...")

        all_results = []

        for file_path in excel_files:
            print(f"\nProcessing: {file_path.name}")

            results = self.analyze_file(file_path)
            all_results.extend(results)

            if results:
                child_codes = [[c for c in r.child_codes] for r in results]
                count_6_1_1 = sum(len(l) for l in child_codes)
                codes = [
                    [
                        c
                        for c in r.child_codes
                        if "matching_6_2_codes" in c and c["matching_6_2_codes"]
                    ]
                for r in results]

                count_6_2_matches = sum(
                    len(
                        [
                            c
                            for c in r.child_codes
                            if "matching_6_2_codes" in c and c["matching_6_2_codes"]
                        ]
                    )
                    for r in results
                )
                count_5_5_matches = sum(
                    len(
                        [
                            c
                            for c in r.child_codes
                            if "matching_5_5_codes" in c and c["matching_5_5_codes"]
                        ]
                    )
                    for r in results
                )
                print(
                    f"  Found {len(results)} parent codes with {count_6_1_1} child codes "
                    f"({count_6_2_matches} with 6.2.*, {count_5_5_matches} with 5.5.*)"
                )
            else:
                print("  No patterns detected")

        # Export results
        if all_results:
            print(f"\nExporting {len(all_results)} detected patterns...")
            self.export_results(all_results)
            print(f"Analysis complete! Results exported to: {self.output_dir}")
        else:
            print("\nNo patterns detected in any files.")

        return all_results

    def export_results(self, results: List[PatternResult]) -> None:
        """
        Export all results using the configured exporter.

        Args:
            results (List[PatternResult]): Results to export
        """
        self.exporter.export_to_csv(results, "summary_results.csv")
        self.exporter.export_detailed_results(results)
        self.exporter.export_summary_report(results)
