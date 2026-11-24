"""Complete care-window extraction, independent of setting/type associations."""

import csv
from pathlib import Path

from create_row_view import code_prefix, time_milliseconds
from data_classes import PatternResult, TimeFrame


SEQUENCE_FIELDS = [
    "Filename", "Parent_Code", "Parent_Start", "Parent_End", "Child_Code",
    "Child_Start", "Child_End", "Child Duration", "Has_Matching_6_2",
    "Has_Matching_5_5", "Matched_Code_Type", "Matched_Code", "Matched_Start",
    "Matched_End", "Matched Duration", "Additional_Info", "Sequence_Order",
    "Sequence_Code", "Sequence_Start", "Sequence_End", "Sequence Duration",
    "Situation_ID",
]


def overlap(left, right):
    return max(0, min(left.end, right.end) - max(left.start, right.start))


def extract_care_patterns(df, filename, strict_codes=None, exclusions=None):
    """Retain every care situation and all positively overlapping annotations.

    Source times are retained, without clipping or shifting. Duplicate copies
    of an annotation are identified by numeric code and millisecond boundaries.
    """
    missing = {"Code", "Anfang", "Ende"} - set(df.columns)
    if missing:
        raise ValueError(f"{filename}: missing columns {sorted(missing)}")
    events = {}
    for number, row in enumerate(df.to_dict("records"), 2):
        label = str(row["Code"]).rsplit(">", 1)[-1].strip()
        code = code_prefix(label)
        try:
            if not code:
                raise ValueError(f"Invalid code {row['Code']!r}")
            start = time_milliseconds(row["Anfang"])
            end = time_milliseconds(row["Ende"])
            if end < start or (code == "6.1.1" and end == start):
                raise ValueError(f"Invalid interval for {code}: {start}–{end}")
        except ValueError as error:
            if strict_codes is None or not code or code in strict_codes or code == "6.1.1":
                raise ValueError(f"{filename}, Excel row {number}: {error}") from error
            if exclusions is None:
                raise ValueError("An exclusion audit is required to skip unselected invalid annotations") from error
            exclusions.append({"Filename": filename, "Excel_Row": number, "Code": code,
                               "Start": str(row["Anfang"]), "End": str(row["Ende"]),
                               "Reason": str(error)})
            continue
        events.setdefault((code, start, end), {
            "code": label, "id": code,
            "start": str(row["Anfang"]), "end": str(row["Ende"]),
            "timeframe": TimeFrame(start, end, str(row["Anfang"]), str(row["Ende"])),
        })
    ordered = sorted(events.values(), key=lambda e: (
        e["timeframe"].start, e["timeframe"].end, e["id"]))
    situations = [e for e in ordered if e["id"] == "6.1.1"]
    if not situations:
        raise ValueError(f"{filename}: no 6.1.1 care situations")
    results = []
    for index, situation in enumerate(situations, 1):
        tf = situation["timeframe"]
        contained = [e for e in ordered if overlap(tf, e["timeframe"]) > 0]
        settings = [e for e in contained if e["id"].startswith("5.4.")]
        parent = max(settings, key=lambda e: overlap(tf, e["timeframe"])) if settings else None
        child = dict(situation)
        child.update({
            "situation_id": f"s{index:03d}", "sequence_scope": "care-overlap",
            "sequence_events": [{k: e[k] for k in ("code", "start", "end")} for e in contained],
            "matching_6_2_codes": [e for e in contained if e["id"].startswith("6.2.")],
            "matching_5_5_codes": [e for e in contained if e["id"].startswith("5.5.")],
        })
        results.append(PatternResult(
            filename=filename,
            parent_code=parent["code"] if parent else "6.1.1 (no 5.4 parent found)",
            parent_timeframe=parent["timeframe"] if parent else tf,
            child_codes=[child],
        ))
    return results


def export_care_sequences(results, path):
    """Write the existing sequence CSV columns plus a stable Situation_ID.

    Multiple care types produce metadata blocks, as in the legacy export.
    Consumers must deduplicate events rather than counting these blocks twice.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SEQUENCE_FIELDS)
        writer.writeheader()
        for result in results:
            for child in result.child_codes:
                for care_type in child["matching_6_2_codes"] or [None]:
                    base = {
                        "Filename": result.filename,
                        "Parent_Code": result.parent_code,
                        "Parent_Start": result.parent_timeframe.original_start,
                        "Parent_End": result.parent_timeframe.original_end,
                        "Child_Code": child["code"], "Child_Start": child["start"],
                        "Child_End": child["end"], "Child Duration": child["timeframe"].end - child["timeframe"].start,
                        "Has_Matching_6_2": bool(child["matching_6_2_codes"]),
                        "Has_Matching_5_5": bool(child["matching_5_5_codes"]),
                        "Matched_Code_Type": "6.2.*", "Situation_ID": child["situation_id"],
                        "Additional_Info": "care-overlap; original timestamps; durations in ms",
                    }
                    if care_type:
                        base.update({
                            "Matched_Code": care_type["code"], "Matched_Start": care_type["start"],
                            "Matched_End": care_type["end"],
                            "Matched Duration": care_type["timeframe"].end - care_type["timeframe"].start,
                        })
                    for order, event in enumerate(child["sequence_events"], 1):
                        writer.writerow({**base, "Sequence_Order": order,
                            "Sequence_Code": event["code"], "Sequence_Start": event["start"],
                            "Sequence_End": event["end"], "Sequence Duration":
                            time_milliseconds(event["end"]) - time_milliseconds(event["start"])})
