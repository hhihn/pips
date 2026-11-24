import argparse
import csv
import os
import re
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd


SRC_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT = SRC_DIR.parent / "data/transformed/analysis_results/sequence_analysis.csv"
PHASE_DURATION_COLUMNS = {
    "6.1.2": "6.1.2_Transition_Before_Duration",
    "6.1.3": "6.1.3_Action_Duration",
    "6.1.4": "6.1.4_Transition_After_Duration",
}
SPEECH_COLUMN = "5_3_1_Duration_Talking_PK"
WITHIN_COLUMNS = {
    f"6.1.{phase}": f"{SPEECH_COLUMN}_within_6_1_{phase}"
    for phase in range(1, 5)
}
TIMING_COLUMNS = [*PHASE_DURATION_COLUMNS.values(), SPEECH_COLUMN, *WITHIN_COLUMNS.values()]


def code_prefix(value):
    """Extract the complete numeric code, without matching e.g. 5.5.1 to 5.5.10."""
    match = re.match(r"^\s*(\d+(?:\.\d+)+)(?=\s|$)", str(value))
    return match.group(1) if match else ""


def time_milliseconds(value):
    """Parse seconds, mm:ss or hh:mm:ss exactly, accepting comma decimals."""
    try:
        parts = [Decimal(part) for part in str(value).strip().replace(",", ".").split(":")]
        if not 1 <= len(parts) <= 3 or any(not part.is_finite() or part < 0 for part in parts):
            raise ValueError
        if any(part != part.to_integral_value() for part in parts[:-1]):
            raise ValueError
        if len(parts) > 1 and parts[-1] >= 60:
            raise ValueError
        if len(parts) == 3 and parts[-2] >= 60:
            raise ValueError
        milliseconds = sum((part * 60 ** i for i, part in enumerate(reversed(parts))), Decimal(0)) * 1000
        if milliseconds != milliseconds.to_integral_value():
            raise ValueError
        return int(milliseconds)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid timestamp (millisecond precision required): {value!r}") from error


def merge_intervals(intervals):
    """Return the union of intervals; duplicates and overlaps count once."""
    merged = []
    for start, end in sorted(set(intervals)):
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def intersect_intervals(left, right):
    return merge_intervals(
        (max(a, c), min(b, d))
        for a, b in left for c, d in right if max(a, c) < min(b, d)
    )


def interval_duration(intervals):
    return sum(end - start for start, end in merge_intervals(intervals))


def event_context(row):
    return (f"{row.get('Filename', '<unknown file>')} "
            f"({row.get('Child_Start', '?')} – {row.get('Child_End', '?')})")


def event_intervals(row):
    """Normalize all intervals needed for care identity and duration calculation."""
    intervals = defaultdict(list)
    relevant = {*WITHIN_COLUMNS, "5.3.1", *(f"5.5.{child}" for child in range(1, 11))}
    for sequence in row["Sequences"]:
        code = code_prefix(sequence.get("Sequence_Code", ""))
        if code not in relevant:
            continue
        try:
            start = time_milliseconds(sequence.get("Sequence_Start", ""))
            end = time_milliseconds(sequence.get("Sequence_End", ""))
            # A reversed interval for another child cannot identify the care
            # child or match valid speech. Keep it for diagnostics; validate
            # the selected child's intervals below.
            if end < start and not code.startswith("5.5."):
                raise ValueError(f"End before start for {code}: {start}, {end}")
        except ValueError as error:
            raise ValueError(f"{event_context(row)}: {error}") from error
        intervals[code].append((start, end))
    return intervals


def pflegekind_for_event(row, intervals):
    """Require one care window and exactly one distinct child with that window."""
    care_windows = set(intervals.get("6.1.1", []))
    if len(care_windows) != 1:
        raise ValueError(f"{event_context(row)}: Expected one 6.1.1 interval, found {len(care_windows)}.")
    care_window = next(iter(care_windows))
    if row.get("Child_Start") is not None and row.get("Child_End") is not None:
        try:
            child_window = (time_milliseconds(row["Child_Start"]), time_milliseconds(row["Child_End"]))
        except ValueError as error:
            raise ValueError(f"{event_context(row)}: {error}") from error
        if care_window != child_window:
            raise ValueError(f"{event_context(row)}: 6.1.1 interval differs from the care event.")
    children = {code for code, windows in intervals.items()
                if code.startswith("5.5.") and care_window in windows}
    if len(children) != 1:
        raise ValueError(f"{event_context(row)}: Missing or ambiguous Pflegekind: {sorted(children)}.")
    return next(iter(children))


def pflegekind_speech_intervals(row, intervals, pflegekind_col="Pflegekind"):
    """Select speech by exact child/time correspondence, then union its intervals."""
    child = pflegekind_for_event(row, intervals)
    if pflegekind_col in row and code_prefix(row[pflegekind_col]) != child:
        raise ValueError(f"{event_context(row)}: {pflegekind_col} disagrees with the care interval.")
    if any(end < start for start, end in intervals[child]):
        raise ValueError(f"{event_context(row)}: End before start for Pflegekind {child}.")
    child_windows = set(intervals[child])
    return merge_intervals(window for window in intervals.get("5.3.1", []) if window in child_windows)


def calculate_event_timing(row):
    """One calculation for all overview durations and coding diagnostics, in ms."""
    intervals = event_intervals(row)
    speech = pflegekind_speech_intervals(row, intervals)
    care = merge_intervals(intervals["6.1.1"])
    phases = {code: merge_intervals(intervals.get(code, [])) for code in PHASE_DURATION_COLUMNS}
    for code, windows in phases.items():
        if interval_duration(intersect_intervals(windows, care)) != interval_duration(windows):
            raise ValueError(f"{event_context(row)}: {code} extends outside 6.1.1.")
    values = {column: interval_duration(phases[code]) for code, column in PHASE_DURATION_COLUMNS.items()}
    values[SPEECH_COLUMN] = interval_duration(speech)
    for code, column in WITHIN_COLUMNS.items():
        windows = care if code == "6.1.1" else phases[code]
        values[column] = interval_duration(intersect_intervals(speech, windows))
    diagnostics = []
    for code, windows in intervals.items():
        if code.startswith("5.5.") and any(end < start for start, end in windows):
            diagnostics.append(f"ignored non-matching recipient {code}: end before start")
    codes = list(phases)
    for i, code in enumerate(codes):
        for other in codes[i + 1:]:
            duration = interval_duration(intersect_intervals(phases[code], phases[other]))
            if duration:
                diagnostics.append(f"overlap {code}/{other}: {duration} ms")
    covered = [window for windows in phases.values() for window in windows]
    gap = interval_duration(care) - interval_duration(intersect_intervals(care, covered))
    if gap:
        diagnostics.append(f"phase gaps: {gap} ms")
    return values, diagnostics


def add_event_timing(events_df):
    """Use the shared calculation for the normal overview generator."""
    values = [calculate_event_timing(row)[0] for _, row in events_df.iterrows()]
    for column in TIMING_COLUMNS:
        events_df[column] = [value[column] for value in values]
    return events_df

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
    """Identify the care child by an exact normalized 6.1.1 time match."""
    events_df[output_column] = events_df.apply(
        lambda row: pflegekind_for_event(row, event_intervals(row)), axis=1
    )
    return events_df


def parse_time(t):
    """Use the common validated parser when a caller needs seconds."""
    return time_milliseconds(t) / 1000


def sum_531_for_matching_pflegekind(
    events_df, pflegekind_col="Pflegekind", output_col="Sum_531_for_Pflegekind"
):
    """Measure the union of exactly child-matched speech intervals, in ms."""
    events_df[output_col] = events_df.apply(
        lambda row: interval_duration(pflegekind_speech_intervals(row, event_intervals(row), pflegekind_col)),
        axis=1,
    )
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
    grouped = df.groupby(EVENT_COLUMNS, dropna=False)

    sequences_per_event = {}
    for group_keys, group_df in grouped:
        sequences = group_df[SEQUENCE_COLUMNS].to_dict(orient="records")
        # Key is tuple of event fields
        key = tuple(None if pd.isna(value) else value for value in group_keys)
        sequences_per_event[key] = sequences

    return sequences_per_event


def add_sequences_to_events(events_df, df):
    """
    For each event in events_df, add a column 'Sequences' with all relevant sequences
    from the original df.
    """
    sequences_per_event = collect_sequences(df)

    def get_sequences(row):
        key = tuple(None if pd.isna(row[col]) else row[col] for col in EVENT_COLUMNS)
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

    if target_code in PHASE_DURATION_COLUMNS:
        events_df[target_code + "_" + output_column] = events_df.apply(
            lambda row: interval_duration(event_intervals(row).get(target_code, [])), axis=1
        )
        return events_df

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
    """Measure child-matched speech intersections with all main-code windows."""
    if main_code not in WITHIN_COLUMNS:
        raise ValueError(f"Unknown phase code: {main_code!r}")
    events_df[output_col] = events_df.apply(
        lambda row: calculate_event_timing(row)[0][WITHIN_COLUMNS[main_code]], axis=1
    )
    return events_df


def decimal_milliseconds(value):
    """Validate millisecond durations used as overview match keys or values."""
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number != number.to_integral_value():
            raise ValueError
        return int(number)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"Invalid millisecond duration: {value!r}") from error


def refresh_overview(input_path, overview_path, dry_run=False):
    """Recalculate a curated overview, retaining its rows, order and other cells.

    Candidates sharing filename, situation and duration must have identical new
    values. The complete result is validated before any output is replaced.
    """
    input_path, overview_path = Path(input_path), Path(overview_path)
    if input_path.resolve() == overview_path.resolve():
        raise ValueError("Overview must not overwrite the sequence input.")
    original = overview_path.read_bytes()
    encoding = "utf-8-sig" if original.startswith(b"\xef\xbb\xbf") else "utf-8"
    with overview_path.open(encoding=encoding, newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        overview = list(reader)
    required = {"Filename", "Situation", "Situation_Duration", *TIMING_COLUMNS}
    if len(fields) != len(set(fields)) or required - set(fields):
        raise ValueError(f"Invalid overview columns; missing {sorted(required - set(fields))}.")
    if not overview:
        raise ValueError("Overview is empty.")
    if any(None in row or None in row.values() for row in overview):
        raise ValueError("Malformed overview CSV row.")

    # Group CSV strings directly: this retains events with missing parent fields
    # and avoids NaN tuple keys while preserving the original event identity.
    groups = defaultdict(list)
    with input_path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required_input = {*EVENT_COLUMNS, *SEQUENCE_COLUMNS}
        if required_input - set(reader.fieldnames or []):
            raise ValueError(f"Sequence input is missing {sorted(required_input - set(reader.fieldnames or []))}.")
        for row in reader:
            if None in row or None in row.values():
                raise ValueError("Malformed sequence CSV row.")
            groups[tuple(row[column] for column in EVENT_COLUMNS)].append(row)
    requested = {(row["Filename"], code_prefix(row["Situation"]), decimal_milliseconds(row["Situation_Duration"]))
                 for row in overview}
    candidates = defaultdict(list)
    for rows in groups.values():
        first = rows[0]
        key = (first["Filename"], code_prefix(first["Matched_Code"]),
               decimal_milliseconds(first["Matched Duration"]))
        if key not in requested:
            continue
        event = {**first, "Sequences": rows}
        if time_milliseconds(first["Matched_End"]) - time_milliseconds(first["Matched_Start"]) != key[2]:
            raise ValueError(f"{event_context(event)}: Situation duration differs from its timestamps.")
        candidates[key].append(calculate_event_timing(event))

    report = {"rows": len(overview), "changed_rows": 0, "changes_by_column": Counter(), "details": []}
    updated = []
    for index, row in enumerate(overview, 1):
        key = (row["Filename"], code_prefix(row["Situation"]), decimal_milliseconds(row["Situation_Duration"]))
        matches = candidates.get(key, [])
        if not matches:
            raise ValueError(f"No sequence pair for overview row {index}: {key}.")
        values, _ = matches[0]
        if any(candidate_values != values for candidate_values, _ in matches[1:]):
            raise ValueError(f"Ambiguous sequence pair for overview row {index}: {key}.")
        total = values[WITHIN_COLUMNS["6.1.1"]]
        if total > key[2] or total > values[SPEECH_COLUMN]:
            raise ValueError(f"Speech exceeds its containing interval for {key}.")
        for code, duration_column in PHASE_DURATION_COLUMNS.items():
            if (values[duration_column] > key[2] or
                    values[WITHIN_COLUMNS[code]] > min(total, values[duration_column])):
                raise ValueError(f"Invalid duration for {code}, {key}.")
        changed = {column: (row[column], str(values[column])) for column in TIMING_COLUMNS
                   if decimal_milliseconds(row[column]) != values[column]}
        combined = dict(row)
        # Keep numerically unchanged cell spellings, enabling byte-level idempotence.
        combined.update({column: new for column, (_, new) in changed.items()})
        updated.append(combined)
        diagnostics = sorted({message for _, messages in matches for message in messages})
        if changed:
            report["changed_rows"] += 1
            report["changes_by_column"].update(changed.keys())
        if changed or diagnostics:
            report["details"].append({"row": index, "key": key, "changes": changed, "diagnostics": diagnostics})
    if not dry_run and report["changed_rows"]:
        # Preserve the existing newline convention as well as its BOM policy.
        newline = "\r\n" if b"\r\n" in original else "\n"
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding=encoding, newline="", dir=overview_path.parent,
                                             prefix=f".{overview_path.name}.", delete=False) as handle:
                temporary_path = Path(handle.name)
                writer = csv.DictWriter(handle, fieldnames=fields, lineterminator=newline)
                writer.writeheader()
                writer.writerows(updated)
            os.chmod(temporary_path, overview_path.stat().st_mode & 0o777)
            os.replace(temporary_path, overview_path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
    return report


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
    # Insert phase columns here to retain the established overview column order.
    for code, column in PHASE_DURATION_COLUMNS.items():
        events_df = sum_code_durations_in_events(events_df, code, column.removeprefix(code + "_"))
    events_df = find_subcodes_within_main_in_order(
        events_df=events_df,
        main_code="6.1.1",
        sub_codes=["1.2.0.5", "1.2.0.6"],
        output_column="Eye_Transition_Total",
    )
    events_df = find_pflegekind_with_same_time(
        events_df=events_df, output_column="Pflegekind"
    )
    events_df = add_event_timing(events_df)
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
    events_df.to_excel(Path(output_path).with_suffix(".xlsx"), index=False)
    print(f"Extracted {len(events_df)} events to {output_path}")


def cli():
    parser = argparse.ArgumentParser(description="Generate an overview or refresh its care-child speech durations.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=SRC_DIR / "übersicht_situationen_länge_pro_datei.csv")
    parser.add_argument("--refresh-overview", type=Path, help="Update the existing curated CSV, retaining its rows and other cells")
    parser.add_argument("--dry-run", action="store_true", help="Report overview corrections without writing")
    args = parser.parse_args()
    if args.dry_run and not args.refresh_overview:
        parser.error("--dry-run requires --refresh-overview")
    try:
        if not args.refresh_overview:
            main(args.input, args.output)
            return
        report = refresh_overview(args.input, args.refresh_overview, args.dry_run)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    for detail in report["details"]:
        print(f"Row {detail['row']}: {detail['key']}")
        for column, (old, new) in detail["changes"].items():
            print(f"  {column}: {old} -> {new} ms")
        for diagnostic in detail["diagnostics"]:
            print(f"  {diagnostic}")
    print(f"{'Dry run' if args.dry_run else 'Refresh'}: {report['changed_rows']}/{report['rows']} rows changed")
    for column, count in report["changes_by_column"].items():
        print(f"  {column}: {count} rows")


if __name__ == "__main__":
    cli()
