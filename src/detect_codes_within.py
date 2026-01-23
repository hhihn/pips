"""
Pattern Detection Tool for Educational Video Analysis

This script analyzes Excel files containing timestamped educational coding data
to identify specific temporal relationships between coded events.

"""

from pattern_analyzer import PatternAnalyzer


def main():
    """Main function to run the pattern analysis."""

    # Configuration
    input_directory = "../data/transformed"  # Change to your input directory

    try:
        # Initialize analyzer
        analyzer = PatternAnalyzer(input_dir=input_directory)

        # Run analysis
        results = analyzer.run_analysis()

        # Print final summary
        if results:
            total_6_1_1 = sum(len(r.child_codes) for r in results)
            matched_6_2_stats = sum(
                len(
                    [
                        c
                        for c in r.child_codes
                        if "matching_6_2_codes" in c and c["matching_6_2_codes"]
                    ]
                )
                for r in results
            )
            matched_5_5_stats = sum(
                len(
                    [
                        c
                        for c in r.child_codes
                        if "matching_5_5_codes" in c and c["matching_5_5_codes"]
                    ]
                )
                for r in results
            )

            # Count sequences
            total_sequences = 0
            for result in results:
                for child_code in result.child_codes:
                    for match_6_2 in child_code.get("matching_6_2_codes", []):
                        total_sequences += match_6_2.get("sequence_count", 0)

            print("\nFINAL SUMMARY:")
            print(f"Files processed: {len(set(r.filename for r in results))}")
            print(f"Patterns detected: {len(results)}")
            print(f"6.1.1 codes analyzed: {total_6_1_1}")
            print(f"6.2.* Matches: {matched_6_2_stats}")
            print(f"5.5.* Matches: {matched_5_5_stats}")
            print(f"Sequence events: {total_sequences}")
        else:
            print("No patterns were detected.")

    except Exception as e:
        print(f"Error running analysis: {str(e)}")


if __name__ == "__main__":
    main()
