import re
import pandas as pd

# 1. Define columns that together describe an event
EVENT_COLUMNS = [
    "Filename",
    "Parent_Code",
    "Parent_Start",
    "Parent_End",
    "Child_Code",
    "Child_Start",
    "Child_End",
    "Child Duration",
    "Matched_Code",
    "Matched_Start",
    "Matched_End",
    "Matched Duration",
]

SEQUENCE_COLUMNS = [
    "Sequence_Order",
    "Sequence_Code",
    "Sequence_Start",
    "Sequence_End",
    "Sequence Duration",
]


def find_pflegekind_with_same_time(
    events_df, output_column="Pflegekind_Matching_6_1_1"
):
    """
    For each event's Sequences, finds the pflegekind code (5.5.1–5.5.10) whose
    Sequence_Start and Sequence_End exactly match the 6.1.1 code.
    Stores the found code (string) or None in output_column.
    """
    # Pattern for 6.1.1 code:
    re_611 = re.compile(r"^6\.1\.1(\b|$)")
    # Pattern for 5.5.1 … 5.5.10 pflegekind subcodes:
    re_55x = re.compile(r"^5\.5\.(10|[1-9])(\b|$)")

    def find_pflegekind(sequences):
        # Find all 6.1.1s (there may be more than one)
        match_611 = [
            seq for seq in sequences if re_611.match(seq.get("Sequence_Code", ""))
        ]
        for seq_611 in match_611:
            start_611 = seq_611.get("Sequence_Start", "")
            end_611 = seq_611.get("Sequence_End", "")
            # Now look for 5.5.N code with same start/end:
            for seq in sequences:
                code = seq.get("Sequence_Code", "")
                if re_55x.match(code):
                    if (
                        seq.get("Sequence_Start", "") == start_611
                        and seq.get("Sequence_End", "") == end_611
                    ):
                        return code  # Return the first found
        return None

    events_df[output_column] = events_df["Sequences"].apply(find_pflegekind)
    return events_df


def parse_time(t):
    """Parse a time string (hh:mm:ss,x or mm:ss,x) into seconds as float."""
    if isinstance(t, float) or isinstance(t, int):
        return float(t)
    t = str(t).replace(",", ".")  # Replace comma with dot for decimals
    parts = t.split(":")
    try:
        if len(parts) == 2:
            minutes, seconds = parts
            return int(minutes) * 60 + float(seconds)
        elif len(parts) == 3:
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        return 0.0
    return 0.0


def sum_531_for_matching_pflegekind(
    events_df, pflegekind_col="Pflegekind", output_col="Sum_531_for_Pflegekind"
):
    """
    For each event, sum durations of all 5.3.1 codes that have an EXACT matching
    pflegekind code (5.5.1–5.5.10) whose code is equal to the event's Pflegekind column,
    and has the same Sequence_Start and Sequence_End as the 5.3.1.
    Stores the total sum in output_col.
    """
    re_531 = re.compile(r"^5\.3\.1(\b|$)")

    def sum_for_event(row):
        sequences = row["Sequences"]
        pflegekind_code = row.get(pflegekind_col)
        if not pflegekind_code or not sequences:
            return 0.0
        # Find all pflegekind windows for the Pflegekind code only
        pflegekind_windows = set(
            (seq.get("Sequence_Start", ""), seq.get("Sequence_End", ""))
            for seq in sequences
            if seq.get("Sequence_Code", "") == pflegekind_code
        )
        # For all 5.3.1s in those windows, sum duration
        total = 0.0
        for seq in sequences:
            code = seq.get("Sequence_Code", "")
            if re_531.match(code):
                window = (seq.get("Sequence_Start", ""), seq.get("Sequence_End", ""))
                if window in pflegekind_windows:
                    try:
                        total += float(seq.get("Sequence Duration", 0))
                    except Exception:
                        pass
        return total

    events_df[output_col] = events_df.apply(sum_for_event, axis=1)
    return events_df


def find_subcodes_within_main_in_order(events_df, main_code, sub_codes, output_column):
    """
    For each event, find the first main_code in Sequences, get its time frame,
    then collect (in order of appearance) all sub_codes occurring within that time frame.
    Result is list of those Sequence_Code strings, stored in output_column.
    """
    main_code_pattern = re.compile(r"^{}(\b|$)".format(re.escape(main_code)))
    sub_code_patterns = [
        re.compile(r"^{}(\b|$)".format(re.escape(code))) for code in sub_codes
    ]

    def get_ordered_subcodes(sequences):
        # Find main_code occurrence and time window
        for seq in sequences:
            code = seq.get("Sequence_Code", "")
            if main_code_pattern.match(code):
                start = parse_time(seq.get("Sequence_Start", 0))
                end = parse_time(seq.get("Sequence_End", 0))

                # Collect codes in time window and matching any sub_code pattern
                result = []
                for sub_seq in sequences:
                    sub_code = sub_seq.get("Sequence_Code", "")
                    sub_start = parse_time(sub_seq.get("Sequence_Start", 0))
                    sub_end = parse_time(sub_seq.get("Sequence_End", 0))
                    # Only include if in window and matches any sub_code
                    if any(p.match(sub_code) for p in sub_code_patterns):
                        print(f"matched {sub_code}: {sub_start} to {sub_end}")
                        print(f"main: {start} to {end}")
                        if start <= sub_start <= end:
                            print("matched timeframe")
                            result.append(sub_code)
                result = "; ".join(result)
                return result  # only first main_code considered
        return []

    events_df[main_code + "_" + output_column] = events_df["Sequences"].apply(
        get_ordered_subcodes
    )
    return events_df


def find_codes_in_sequence_and_add_column(events_df, codes_to_find, target_column):
    """
    For each event's 'Sequences', find all sequence codes that match ANY of codes_to_find
    at the start of the Sequence_Code string (exact subcode matches, no partial overlap).
    Writes result to target_column.
    """

    # Compile regex patterns for all codes to find (match at start, followed by word boundary or end)
    patterns = [
        re.compile(r"^{}(\b|$)".format(re.escape(code))) for code in codes_to_find
    ]

    def extract_and_order_codes(sequences):
        found = []
        for seq in sequences:
            seq_code = seq.get("Sequence_Code", "")
            for pat in patterns:
                if pat.match(seq_code):
                    found.append(seq_code)
                    break  # stop at first code match for this sequence
        found = "; ".join(found)
        return found

    events_df[target_column] = events_df["Sequences"].apply(extract_and_order_codes)
    return events_df


def collect_sequences(df):
    """For each event, collect sequence info from matching rows."""
    grouped = df.groupby(EVENT_COLUMNS)

    sequences_per_event = {}
    for group_keys, group_df in grouped:
        sequences = group_df[SEQUENCE_COLUMNS].to_dict(orient="records")
        # Key is tuple of event fields
        sequences_per_event[group_keys] = sequences

    return sequences_per_event


def add_sequences_to_events(events_df, df):
    """
    For each event in events_df, add a column 'Sequences' with all relevant sequences
    from the original df.
    """
    sequences_per_event = collect_sequences(df)

    def get_sequences(row):
        key = tuple(row[col] for col in EVENT_COLUMNS)
        return sequences_per_event.get(key, [])

    events_df["Sequences"] = events_df.apply(get_sequences, axis=1)
    return events_df


def load_data(input_path):
    """Loads the CSV into a DataFrame."""
    df = pd.read_csv(input_path)
    return df


def get_events(df):
    """Groups by event columns and identifies unique events."""
    events_df = df.drop_duplicates(subset=EVENT_COLUMNS)
    return events_df.reset_index(drop=True)


def sum_code_durations_in_events(events_df, target_code, output_column):
    """
    For each row in events_df, sum the durations for sequences where Sequence_Code starts with target_code.
    The duration is taken from 'Sequence Duration' for each sequence. Result is saved to output_column.
    """

    # Regex for the exact code prefix, e.g. '2.2.3.1' matches '2.2.3.1 antippen', not '2.2.3.11'
    pattern = re.compile(r"^{}(\b|$)".format(re.escape(target_code)))

    def sum_durations(sequences):
        total = 0.0
        for seq in sequences:
            code = seq.get("Sequence_Code", "")
            duration = seq.get("Sequence Duration", 0)
            # Defensive: allow duration as string
            try:
                duration = float(duration)
            except (ValueError, TypeError):
                duration = 0
            if pattern.match(code):
                total += duration
        return total

    events_df[target_code + "_" + output_column] = events_df["Sequences"].apply(
        sum_durations
    )
    return events_df


def sum_531_within_main_window(events_df, main_code, output_col="Sum_531_within_main"):
    """
    For each event, finds the first main_code in Sequences, gets its time window,
    sums durations of all 5.3.1 codes occurring entirely within this window (inclusive).
    Stores the total sum in output_col.
    """
    re_main = re.compile(r"^{}(\b|$)".format(re.escape(main_code)))
    re_531 = re.compile(r"^5\.3\.1(\b|$)")

    def parse_time(t):
        """Parse time string (hh:mm:ss,x or mm:ss,x) into seconds."""
        if isinstance(t, float) or isinstance(t, int):
            return float(t)
        t = str(t).replace(",", ".").replace(" ", "")  # Make sure format is consistent
        parts = t.split(":")
        try:
            if len(parts) == 2:
                minutes, seconds = parts
                return int(minutes) * 60 + float(seconds)
            elif len(parts) == 3:
                hours, minutes, seconds = parts
                return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except Exception:
            return 0.0
        return 0.0

    def sum_for_event(sequences):
        # Find main code occurrence and its time window
        main_start, main_end = None, None
        for seq in sequences:
            code = seq.get("Sequence_Code", "")
            if re_main.match(code):
                main_start = parse_time(seq.get("Sequence_Start", ""))
                main_end = parse_time(seq.get("Sequence_End", ""))
                break  # Only consider the first occurrence
        if main_start is None or main_end is None:
            return 0.0

        # Sum all 5.3.1 durations occurring within main code's time window
        total = 0.0
        for seq in sequences:
            code = seq.get("Sequence_Code", "")
            if re_531.match(code):
                seq_start = parse_time(seq.get("Sequence_Start", ""))
                seq_end = parse_time(seq.get("Sequence_End", ""))
                if main_start <= seq_start and seq_end <= main_end:
                    try:
                        total += float(seq.get("Sequence Duration", 0))
                    except Exception:
                        pass
        return total

    events_df[output_col] = events_df["Sequences"].apply(sum_for_event)
    return events_df


def main(input_path, output_path):
    df = load_data(input_path)
    events_df = get_events(df)
    events_df = add_sequences_to_events(events_df, df)
    events_df = find_codes_in_sequence_and_add_column(
        events_df=events_df,
        codes_to_find=["1.1.1.1", "1.1.1.2", "1.1.1.3", "1.1.1.4"],
        target_column="Valence",
    )
    events_df = find_codes_in_sequence_and_add_column(
        events_df=events_df,
        codes_to_find=["1.1.2.1", "1.1.2.2", "1.1.2.3"],
        target_column="Arousal",
    )
    events_df = find_codes_in_sequence_and_add_column(
        events_df=events_df,
        codes_to_find=["1.2.0.1", "1.2.0.2", "1.2.0.3", "1.2.0.4"],
        target_column="Body_Orientation",
    )
    events_df = sum_code_durations_in_events(
        events_df=events_df,
        target_code="6.1.2",
        output_column="Transition_Before_Duration",
    )
    events_df = sum_code_durations_in_events(
        events_df=events_df, target_code="6.1.3", output_column="Action_Duration"
    )
    events_df = sum_code_durations_in_events(
        events_df=events_df,
        target_code="6.1.4",
        output_column="Transition_After_Duration",
    )
    events_df = find_subcodes_within_main_in_order(
        events_df=events_df,
        main_code="6.1.1",
        sub_codes=["1.2.0.5", "1.2.0.6"],
        output_column="Eye_Transition_Total",
    )
    events_df = find_pflegekind_with_same_time(
        events_df=events_df, output_column="Pflegekind"
    )
    events_df = sum_531_for_matching_pflegekind(
        events_df=events_df, output_col="5_3_1_Duration_Talking_PK"
    )
    events_df = sum_531_within_main_window(
        events_df=events_df,
        main_code="6.1.1",
        output_col="5_3_1_Duration_Talking_PK_within_6_1_1",
    )
    events_df = sum_531_within_main_window(
        events_df=events_df,
        main_code="6.1.2",
        output_col="5_3_1_Duration_Talking_PK_within_6_1_2",
    )
    events_df = sum_531_within_main_window(
        events_df=events_df,
        main_code="6.1.3",
        output_col="5_3_1_Duration_Talking_PK_within_6_1_3",
    )
    events_df = sum_531_within_main_window(
        events_df=events_df,
        main_code="6.1.4",
        output_col="5_3_1_Duration_Talking_PK_within_6_1_4",
    )
    events_df.drop(
        [
            "Sequences",
            "Child_Code",
            "Child_Start",
            "Child_End",
            "Has_Matching_6_2",
            "Has_Matching_5_5",
            "Matched_Code_Type",
            "Additional_Info",
            "Sequence_Order",
            "Sequence_Code",
            "Sequence_Start",
            "Sequence_End",
            "Sequence Duration",
            "Pflegekind",
            "Parent_Start",
            "Parent_End",
            "Matched_Start",
            "Matched_End",
        ],
        axis=1,
        inplace=True,
    )
    events_df.rename(
        columns={
            "Parent_Code": "Setting",
            "Matched_Code": "Situation",
            "Matched Duration": "Situation_Duration",
            "Child Duration": "Total_Duration",
        },
        inplace=True,
    )
    events_df.to_csv(output_path, index=False)
    events_df.to_excel(output_path.replace("csv", "xlsx"), index=False)
    print(f"Extracted {len(events_df)} events to {output_path}")


if __name__ == "__main__":
    input_path = "../data/transformed/analysis_results/sequence_analysis.csv"
    output_path = "übersicht_situationen_länge_pro_datei.csv"
    main(input_path, output_path)
