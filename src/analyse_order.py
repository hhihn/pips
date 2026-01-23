import json

import pandas as pd


import re


def time_to_seconds(time_str: str) -> float:
    """
    Convert a time string like "0:00:29,6" or "00:29,6" into seconds.
    Handles commas as decimal points.
    """
    if not isinstance(time_str, str) or not time_str.strip():
        return 0.0
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    try:
        if len(parts) == 3:  # H:M:S
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:  # M:S
            m, s = map(float, parts)
            return m * 60 + s
        elif len(parts) == 1:
            return float(parts[0])
    except ValueError:
        return 0.0
    return 0.0


def find_6_1_1_index_within(six_one_one_dict, start_time, end_time):
    """
    Find the index of the 6.1.1 entry whose time range fully contains
    the given start and end timestamps.

    Args:
        six_one_one_dict (dict): Dict with "six_one_one_codes" key = list of [code, start, end]
        start_time (str): Start time of the target interval
        end_time (str): End time of the target interval

    Returns:
        int: Index of matching entry, or -1 if not found
    """
    # Get the list of 6.1.1 codes
    if "six_one_one_codes" not in six_one_one_dict:
        return -1

    six_one_one_codes = six_one_one_dict["six_one_one_codes"]

    # Convert input times once
    target_start = time_to_seconds(start_time)
    target_end = time_to_seconds(end_time)

    for index, entry in enumerate(six_one_one_codes):
        if len(entry) >= 3:
            _, entry_start, entry_end = entry[:3]
            entry_start_sec = time_to_seconds(entry_start)
            entry_end_sec = time_to_seconds(entry_end)

            # Check if target interval lies within this 6.1.1 interval
            if entry_start_sec <= target_start and entry_end_sec >= target_end:
                return index

    return -1  # Not found


# Functions to identify codes
def is_5_5_x_code(code):
    if pd.isna(code) or not isinstance(code, str):
        return False
    match = re.match(r"^(\d+(?:\.\d+)*)", code.strip())
    if match:
        numeric_part = match.group(1)
        parts = numeric_part.split(".")
        if (
            len(parts) == 3
            and parts[0] == "5"
            and parts[1] == "5"
            and parts[2].isdigit()
            and 1 <= int(parts[2]) <= 10
        ):
            return True
    return False


def is_6_1_1_code(code):
    if pd.isna(code) or not isinstance(code, str):
        return False
    match = re.match(r"^(\d+(?:\.\d+)*)", code.strip())
    if match:
        return match.group(1) == "6.1.1"
    return False


def find_matching_5_5_x_code(rows, current_row, child_per_file, filename, situation_number):
    """
    Find the 5.5.x code that overlaps with the current row's time range.
    """
    current_start = time_to_seconds(current_row["Sequence_Start"])
    current_end = time_to_seconds(current_row["Sequence_End"])

    # Suche nach 5.5.x Codes mit überlappender Zeit
    for _, row in rows.iterrows():
        seq_code = row["Sequence_Code"]
        if pd.notna(seq_code) and is_5_5_x_code(seq_code):
            row_start = time_to_seconds(row["Sequence_Start"])
            row_end = time_to_seconds(row["Sequence_End"])

            # Prüfe auf Zeitüberlappung
            if row_start <= current_end and row_end >= current_start:
                # Extrahiere den 5.5.x Code
                match = re.match(r"^(\d+(?:\.\d+)*)", seq_code.strip())
                if match:
                    return match.group(1)

    return None


def extract_and_save_sequences(input_csv_path, output_csv_path):
    """
    Fixed version that properly finds overlapping 5.5.x codes.
    """
    # target_codes = {
    #     "6.1.1", "6.1.2", "6.1.3", "6.1.4", "6.2.1", "6.2.2",
    #     "6.4.2", "6.4.3", "6.4.4", "6.4.5", "6.5.1", "2.1.2.3", "2.1.3.1", "6.5.3",
    #     "2.2.3.14", "2.2.3.4", "2.2.4.2", "2.2.4.3", "6.5.1", "6.5.4"
    # }
    target_codes = {
        "6.1.1",
        "6.4.2", "6.4.3", "6.4.4", "6.4.5", "6.5.1", "2.1.2.3", "2.1.3.1", "6.5.3",
        "2.2.3.14", "2.2.3.4", "6.5.4", "6.2.1", "6.2.2"
    }
    try:
        df = pd.read_csv(input_csv_path)
    except Exception as e:
        print(f"Error loading CSV file: {e}")
        return

    results_data = []
    child_per_file = find_5_5_x_for_6_1_1_codes(df=df)

    grouped = df.groupby("Filename")

    for file_i, (filename, group) in enumerate(grouped):
        rows = group.reset_index(drop=True)

        for i, row in rows.iterrows():
            seq_code = row["Sequence_Code"]

            if pd.notna(seq_code) and isinstance(seq_code, str):
                match = re.match(r"^(\d+(?:\.\d+)*)", seq_code.strip())

                if match:
                    numeric_part = match.group(1)

                    if numeric_part in target_codes:
                        # Finde die Situation
                        situation_number = find_6_1_1_index_within(
                            six_one_one_dict=child_per_file.get(filename, {}),
                            start_time=row["Sequence_Start"],
                            end_time=row["Sequence_End"],
                        )

                        if situation_number == -1:
                            continue

                        try:
                            child_situation = child_per_file[filename]["matching_children"][situation_number]
                        except (KeyError, IndexError):
                            print(f"No matching children for situation {situation_number} in {filename}")
                            continue

                        # NEUE LOGIK: Suche überlappenden 5.5.x Code
                        found_5_5_x = find_matching_5_5_x_code(
                            rows, row, child_per_file, filename, situation_number
                        )

                        if found_5_5_x:
                            child_code = " PK" if found_5_5_x == child_situation else " AK"
                        else:
                            child_code = " NA"

                        results_data.append({
                            "Filename": filename,
                            "Sequence_Code": numeric_part + child_code,
                            "Sequence_Start": row["Sequence_Start"],
                            "Sequence_End": row["Sequence_End"],
                            "id": f"{file_i}_{situation_number}",
                        })

    results_df = pd.DataFrame(results_data)
    results_df.to_csv(output_csv_path, index=False)
    print(f"Results saved to: {output_csv_path}")
    print(f"Total matching sequences found: {len(results_data)}")

    return results_df

def find_5_5_x_for_6_1_1_codes(df):
    results = {}

    # Group by filename
    grouped = df.groupby("Filename")
    print(f"found {len(grouped)} sequences by Filename")
    for filename, group in grouped:
        # Lists to store 6.1.1 codes and 5.5.x codes with their timing info
        six_one_one_codes = []  # [(code, start, end), ...]
        five_five_x_codes = []  # [(code, start, end), ...]

        # Separate 6.1.1 codes and 5.5.x codes
        for index, row in group.iterrows():
            seq_code = row["Sequence_Code"]
            start_time = row["Sequence_Start"]
            end_time = row["Sequence_End"]

            if is_6_1_1_code(seq_code):
                # Extract the numeric part
                match = re.match(r"^(\d+(?:\.\d+)*)", seq_code.strip())
                if match:
                    numeric_part = match.group(1)
                    six_one_one_codes.append((numeric_part, start_time, end_time))

            elif is_5_5_x_code(seq_code):
                # Extract the numeric part
                match = re.match(r"^(\d+(?:\.\d+)*)", seq_code.strip())
                if match:
                    numeric_part = match.group(1)
                    five_five_x_codes.append((numeric_part, start_time, end_time))

        # Find matching 5.5.x codes for each 6.1.1 code
        matching_codes = []
        for six_code, six_start, six_end in six_one_one_codes:
            # Look for 5.5.x code with exact same start and end times
            for five_code, five_start, five_end in five_five_x_codes:
                # Compare times (handle potential string formatting differences)
                if (
                    str(six_start).strip() == str(five_start).strip()
                    and str(six_end).strip() == str(five_end).strip()
                ):
                    matching_codes.append(five_code)
                    break  # Take first match (in case of multiple)

        # Store results for this filename
        if matching_codes:
            results[filename] = {
                "matching_children": matching_codes,
                "six_one_one_codes": six_one_one_codes,
            }
        else:
            results[filename] = []

    # Print summary
    print("5.5.x codes matching 6.1.1 codes by timing:")
    print("=" * 50)

    total_matches = 0
    for filename, codes in results.items():
        print(f"\n{filename}:")
        if codes:
            print(f"  Matching 5.5.x codes: {codes}")
            print(f"  Count: {len(codes)}")
            total_matches += len(codes)
        else:
            print("  No matching 5.5.x codes found")

    print("\nOverall Summary:")
    print(f"Total files processed: {len(results)}")
    print(f"Total matching pairs found: {total_matches}")

    return results


# Example usage
if __name__ == "__main__":
    input_csv = "../data/transformed/analysis_results/sequence_analysis.csv"
    output_csv = "extracted_sequences.csv"

    extract_and_save_sequences(input_csv, output_csv)
