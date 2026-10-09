"""Join CSV sources on nonempty IDs shared by every source.

Run with no arguments for the clustering/situation export, or extend it with:
    python src/consolidate_csv.py --add extra=path/to/extra.csv

The complete result, including overview columns, is consolidated_data.csv.
The intermediate ID join is saved separately as consolidated_first_round.csv.

Replace the default sources using repeated --source name=path arguments.
Original column names are preserved. Observation rows are
reshaped into one row per ID, with separate columns for each target code.
Measurement columns use a target-code suffix, e.g. duration_s__5.3.1.
Columns shared by sources are kept once and must have matching values.
Additional sources must have one row per ID, or specify --wide name=column.
"""

import argparse
import csv
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path


SRC_DIR = Path(__file__).resolve().parent
DEFAULT_SOURCES = [
    ("situations", SRC_DIR / "count_analysis_situation_counts.csv"),
    ("observations", SRC_DIR / "oma/oma_output/cluster_code_duration_observations.csv"),
]

# Set to a list of output column names to retain only those columns, in order.
# None retains all columns. The matching key (normally "id") is always retained.
# Example: RETAIN_COLUMNS = ["id", "Filename", "cluster", "Situation_Duration"]
RETAIN_COLUMNS: list[str] | None = ["id", "cluster", "Filename", "Situation_Code", "Situation_Duration", "Orientierung FK: von vorn" ,
                                    "Orientierung FK: seitlich",
                                    "Orientierung FK: von hinten",
                                    "Art des Kontakts: Halten und Berührung durch Pflegegegenstand",
                                    "Art des Kontakts: Berührung durch Pflegegegenstand ohne Halten",]

OVERVIEW_PATH = SRC_DIR.parent / "data/sauber_übersicht_situationen_länge_pro_datei.csv"
# Separate policy for columns added in the second merge; None adds all non-key
# overview columns. Durations from the overview are converted from ms to seconds.
OVERVIEW_RETAIN_COLUMNS: list[str] | None = [
    "6.1.2_Transition_Before_Duration",
    "6.1.3_Action_Duration",
    "6.1.4_Transition_After_Duration",
    "5_3_1_Duration_Talking_PK",
    "5_3_1_Duration_Talking_PK_within_6_1_1",
    "5_3_1_Duration_Talking_PK_within_6_1_2",
    "5_3_1_Duration_Talking_PK_within_6_1_3",
    "5_3_1_Duration_Talking_PK_within_6_1_4",
]

# Output name -> (talking-duration column, encasing-sequence duration column).
# Ratios are fractions (0.4 = 40%); zero-length sequences yield an empty cell.
PROPORTION_COLUMNS = {
    f"5_3_1_Proportion_Talking_PK_within_6_1_{phase}": (
        f"5_3_1_Duration_Talking_PK_within_6_1_{phase}",
        denominator,
    )
    for phase, denominator in enumerate([
        "Situation_Duration",
        "6.1.2_Transition_Before_Duration",
        "6.1.3_Action_Duration",
        "6.1.4_Transition_After_Duration",
    ], start=1)
}

# Source column -> final export name, in the requested display order.
EXPORT_COLUMNS = {
    "id": "ID",
    "Filename": "Filename",
    "Situation_Code": "Situation_Type",
    "cluster": "Cluster",
    "Situation_Duration": "Total_Duration",
    "6.1.2_Transition_Before_Duration": "Pre-Action_Duration",
    "6.1.3_Action_Duration": "Action_Duration",
    "6.1.4_Transition_After_Duration": "Post_Action_Duration",
    "5_3_1_Duration_Talking_PK_within_6_1_1": "Total_Educator-Speech-Duration",
    "5_3_1_Duration_Talking_PK_within_6_1_2": "Pre-Action_Educator-Speech_Duration",
    "5_3_1_Duration_Talking_PK_within_6_1_3": "Action_Educator-Speech_Duration",
    "5_3_1_Duration_Talking_PK_within_6_1_4": "Post-Action_Educator-Speech_Duration",
    "5_3_1_Proportion_Talking_PK_within_6_1_1": "Total_Educator-Speech_Proportion",
    "5_3_1_Proportion_Talking_PK_within_6_1_2": "Pre-Action_Educator-Speech_Proportion",
    "5_3_1_Proportion_Talking_PK_within_6_1_3": "Action_Educator-Speech_Proportion",
    "5_3_1_Proportion_Talking_PK_within_6_1_4": "Post-Action_Educator-Speech_Proportion",
    "Orientierung FK: von vorn": "Position_Front",
    "Orientierung FK: seitlich": "Position_Side",
    "Orientierung FK: von hinten": "Position_Behind",
    "Art des Kontakts: Halten und Berührung durch Pflegegegenstand": "PhysContact_with_Holding",
    "Art des Kontakts: Berührung durch Pflegegegenstand ohne Halten": "PhysContact_without_Holding",
}
SITUATION_TYPES = {"6.2.1": "Nose Blowing", "6.2.2": "Face Cleaning"}


def add_proportions(rows: list[dict], fields: list[str]) -> list[str]:
    """Add configured ratios before writing the final overview merge."""
    for output_column, (numerator, denominator) in PROPORTION_COLUMNS.items():
        missing = {numerator, denominator} - set(fields)
        if missing:
            raise ValueError(f"Cannot compute {output_column}: retain columns "
                             f"{', '.join(sorted(missing))}.")
        if output_column in fields:
            raise ValueError(f"Proportion column already exists: {output_column}.")
        for row in rows:
            if not row[numerator] or not row[denominator]:
                row[output_column] = ""
                continue
            talking = Decimal(row[numerator])
            window = Decimal(row[denominator])
            if not talking.is_finite() or not window.is_finite() or talking < 0 or window < 0:
                raise ValueError(f"Invalid duration for ID {row['id']!r} in {output_column}.")
            row[output_column] = format(talking / window, "f") if window else ""
        fields.append(output_column)
    return fields


def merge_overview(merged_path: Path, overview_path: Path, output: Path,
                   retain_columns: list[str] | None = None) -> int:
    """Add overview columns using filename, situation code and duration.

    The overview has no IDs. Ambiguous matches with differing data fail rather
    than assigning values by row order. Every row must have a valid pair.
    """
    if output.resolve() in {merged_path.resolve(), overview_path.resolve()}:
        raise ValueError("Second-merge output must not overwrite an input.")
    with merged_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        merged = list(reader)
    with overview_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        overview_fields = reader.fieldnames or []
        overview = list(reader)
    for column in ["Filename", "Situation_Code", "Situation_Duration"]:
        if column not in fields:
            raise ValueError(f"First merge must retain {column!r} to match the overview.")
    for column in ["Filename", "Situation", "Situation_Duration"]:
        if column not in overview_fields:
            raise ValueError(f"Overview is missing {column!r}.")
    match_columns = {"Filename", "Situation", "Situation_Duration"}
    selected = (retain_columns if retain_columns is not None else
                [column for column in overview_fields if column not in match_columns])
    unknown = set(selected) - set(overview_fields)
    if unknown:
        raise ValueError(f"Unknown overview columns: {', '.join(sorted(unknown))}.")
    selected = list(dict.fromkeys(column for column in selected if column not in match_columns))
    groups = defaultdict(list)
    for row in overview:
        key = (row["Filename"], row["Situation"].split()[0],
               Decimal(row["Situation_Duration"]) / 1000)
        values = {}
        for column in selected:
            cell = row[column]
            if cell and (column.endswith("_Duration") or column.startswith("5_3_1_Duration")):
                cell = str(Decimal(cell) / 1000)
            values[column] = cell
        groups[key].append(values)
    for key, values in groups.items():
        if any(value != values[0] for value in values[1:]):
            raise ValueError(f"Ambiguous overview match for {key}; start/end or IDs are needed.")
    result = []
    for row in merged:
        key = (row["Filename"], row["Situation_Code"], Decimal(row["Situation_Duration"]))
        if not groups.get(key):
            raise ValueError(f"No overview pair for ID {row['id']!r}, key {key}.")
        combined = dict(row)
        for column, cell in groups[key].pop().items():
            if column in combined and combined[column] != cell:
                raise ValueError(f"Conflicting overview column {column!r} for ID {row['id']!r}.")
            combined[column] = cell
        result.append(combined)
    if any(groups.values()):
        raise ValueError("Some overview rows have no pair in the first merge.")
    fields = fields + [column for column in selected if column not in fields]
    fields = add_proportions(result, fields)
    export_rows = []
    for row in result:
        if row["Situation_Code"] not in SITUATION_TYPES:
            raise ValueError(f"Unknown situation code: {row['Situation_Code']!r}.")
        exported = {target: row[source] for source, target in EXPORT_COLUMNS.items()}
        exported["Situation_Type"] = SITUATION_TYPES[row["Situation_Code"]]
        export_rows.append(exported)
    # Preserve columns supplied by additional sources after the standard export.
    extra_fields = [column for column in fields
                    if column not in EXPORT_COLUMNS and column != "5_3_1_Duration_Talking_PK"]
    fields = list(EXPORT_COLUMNS.values()) + extra_fields
    for row, exported in zip(result, export_rows):
        exported.update({column: row[column] for column in extra_fields})
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(export_rows)
    return len(result)


def time_seconds(value: str) -> Decimal:
    """Parse h:mm:ss or mm:ss timestamps, accepting decimal commas."""
    try:
        parts = [Decimal(part) for part in value.strip().replace(",", ".").split(":")]
    except InvalidOperation as error:
        raise ValueError(f"Invalid situation timestamp: {value!r}") from error
    if not 1 <= len(parts) <= 3 or any(not part.is_finite() or part < 0 for part in parts):
        raise ValueError(f"Invalid situation timestamp: {value!r}")
    return sum((part * Decimal(60) ** index for index, part in enumerate(reversed(parts))), Decimal(0))


def parse_source(value: str) -> tuple[str, Path]:
    name, separator, path = value.partition("=")
    if not separator or not name.strip() or not path:
        raise argparse.ArgumentTypeError("Expected source_name=path/to/file.csv")
    return name.strip(), Path(path)


def consolidate(sources: list[tuple[str, Path]], output: Path, key: str = "id",
                wide: dict[str, str] | None = None,
                retain_columns: list[str] | None = None) -> dict:
    """Write an inner join and return row counts and unmatched IDs per source.

    The first source determines the output rows. Other sources add columns,
    never row combinations. ``wide`` maps source names to pivot columns.
    The output must have at least as many rows as the smallest input. This is
    a row-count check; the report separately identifies dropped input rows.
    Validation completes before writing the output.
    ``retain_columns`` selects output columns after matching and validation;
    the key is always included. None retains every column.
    """
    if len(sources) < 2 or len({name for name, _ in sources}) != len(sources):
        raise ValueError("Provide at least two sources with distinct names.")
    if output.resolve() in {Path(path).resolve() for _, path in sources}:
        raise ValueError("Output must not overwrite an input file.")
    wide = {"observations": "target_code"} if wide is None else wide
    tables = []
    fields = [key]
    for name, path in sources:
        with Path(path).open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            columns = reader.fieldnames or []
            if key not in columns or len(set(columns)) != len(columns):
                raise ValueError(f"{path}: missing {key!r} or duplicate column names.")
            rows = list(reader)
        if not rows:
            raise ValueError(f"{path}: empty input.")
        groups = defaultdict(list)
        for row in rows:
            if None in row or any(value is None for value in row.values()):
                raise ValueError(f"{path}: malformed CSV row.")
            value = row[key].strip()
            if value:
                groups[value].append(row)
        source_fields = [column for column in columns if column != key]
        if name in wide:
            pivot = wide[name]
            if pivot not in columns or pivot == key:
                raise ValueError(f"{path}: invalid pivot column {pivot!r}.")
            # Keep ID-level metadata once; measurements become code columns.
            shared = [column for column in source_fields if column != pivot
                      and column not in {"duration_s", "has_code", "matched_code"}
                      and all(len({row[column] for row in group}) == 1
                              for group in groups.values())]
            measurements = [column for column in source_fields
                            if column not in shared and column != pivot]
            codes = list(dict.fromkeys(row[pivot] for row in rows))
            source_fields = shared + [f"{column}__{code}" for code in codes
                                      for column in measurements]
            reshaped = {}
            for value, group in groups.items():
                if any(not row[pivot].strip() for row in group) or len(
                    {row[pivot] for row in group}
                ) != len(group):
                    raise ValueError(f"{path}: blank or duplicate {pivot} for ID {value}.")
                result = {column: group[0][column] for column in shared}
                for row in group:
                    result.update({f"{column}__{row[pivot]}": row[column]
                                   for column in measurements})
                reshaped[value] = [result]
            groups = reshaped
        elif tables and any(len(group) > 1 for group in groups.values()):
            raise ValueError(f"{path}: repeated IDs; use --wide {name}=column to add columns.")
        groups = {value: [{column: row.get(column, "")
                          for column in source_fields} for row in group]
                  for value, group in groups.items()}
        if len(source_fields) != len(set(source_fields)):
            raise ValueError(f"{path}: reshaping produces duplicate column names.")
        fields.extend(column for column in source_fields if column not in fields)
        tables.append((name, rows, groups))
    shared_ids = set.intersection(*(set(groups) for _, _, groups in tables))
    # Keep the first source's ID order, and each source's original row order.
    ordered_ids = [value for value in tables[0][2] if value in shared_ids]
    merged = []
    for value in ordered_ids:
        for base_row in tables[0][2][value]:
            row = {key: value, **base_row}
            for name, _, groups in tables[1:]:
                for column, cell in groups[value][0].items():
                    if column in row and row[column] != cell:
                        raise ValueError(f"Conflicting {column!r} for ID {value!r} "
                                         f"in source {name!r}. No output written.")
                    row[column] = cell
            merged.append(row)
    if "Situation_Start" in fields and "Situation_End" in fields:
        if "Situation_Duration" not in fields:
            fields.append("Situation_Duration")
        for row in merged:
            duration = time_seconds(row["Situation_End"]) - time_seconds(row["Situation_Start"])
            if duration < 0:
                raise ValueError(f"Situation ends before it starts for ID {row[key]!r}.")
            row["Situation_Duration"] = str(duration)
    minimum = min(len(rows) for _, rows, _ in tables)
    if len(merged) < minimum:
        raise ValueError(f"Only {len(merged)} joined rows; required at least {minimum}. "
                         "No output written. Check missing or unmatched IDs.")
    report = {"output_rows": len(merged), "matched_ids": len(shared_ids), "sources": {}}
    for name, rows, groups in tables:
        retained = sum(row[key].strip() in shared_ids for row in rows)
        report["sources"][name] = {
            "input_rows": len(rows), "matched_input_rows": retained,
            "dropped_rows": len(rows) - retained,
            "unmatched_ids": sorted(set(groups) - shared_ids),
        }
    output = Path(output)
    if retain_columns is not None:
        unknown = set(retain_columns) - set(fields)
        if unknown:
            raise ValueError(f"Unknown retained columns: {', '.join(sorted(unknown))}. "
                             "No output written.")
        fields = list(dict.fromkeys([key, *retain_columns]))
        merged = [{column: row[column] for column in fields} for row in merged]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(merged)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="append", type=parse_source,
                        help="Replace defaults; repeat for each name=path source")
    parser.add_argument("--add", action="append", type=parse_source, default=[],
                        help="Add another name=path source to the join")
    parser.add_argument("--key", default="id")
    parser.add_argument("--wide", action="append", type=parse_source, default=[],
                        help="Reshape a source to columns: name=pivot_column")
    parser.add_argument("--output", type=Path, default=SRC_DIR / "consolidated_data.csv",
                        help="Complete merged CSV, including overview columns")
    parser.add_argument("--first-round-output", type=Path,
                        default=SRC_DIR / "consolidated_first_round.csv",
                        help="Intermediate ID join before adding overview columns")
    parser.add_argument("--overview", type=Path, default=OVERVIEW_PATH)
    parser.add_argument("--overview-output", type=Path,
                        help="Optional override for the complete output path")
    parser.add_argument("--skip-overview", action="store_true",
                        help="Run only the first merge")
    args = parser.parse_args()
    try:
        first_output = args.output if args.skip_overview else args.first_round_output
        final_output = args.overview_output or args.output
        if not args.skip_overview and first_output.resolve() == final_output.resolve():
            raise ValueError("First-round and complete output paths must differ.")
        wide = {"observations": "target_code"}
        wide.update({name: str(column) for name, column in args.wide})
        report = consolidate((args.source or DEFAULT_SOURCES) + args.add, first_output,
                             args.key, wide, retain_columns=RETAIN_COLUMNS)
        if not args.skip_overview:
            overview_rows = merge_overview(first_output, args.overview, final_output,
                                          OVERVIEW_RETAIN_COLUMNS)
    except ValueError as error:
        parser.error(str(error))
    print(f"First merge: {report['output_rows']} rows for {report['matched_ids']} IDs "
          f"in {first_output}")
    for name, details in report["sources"].items():
        print(f"{name}: {details['matched_input_rows']}/{details['input_rows']} input rows "
              f"matched; {details['dropped_rows']} dropped")
        if details["unmatched_ids"]:
            print(f"  Unmatched IDs: {', '.join(details['unmatched_ids'])}")
    if not args.skip_overview:
        print(f"Complete output: {overview_rows} rows including overview columns in {final_output} "
              "(durations in seconds)")


if __name__ == "__main__":
    main()
