import pandas as pd
import re
from typing import List


def parse_time_to_seconds(t: str) -> float:
    """Convert '0:00:29,6' → seconds (float)."""
    if pd.isna(t) or not isinstance(t, str):
        return 0.0
    t = t.replace(",", ".").strip()
    parts = t.split(":")
    try:
        if len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
        return float(parts[0])
    except ValueError:
        return 0.0


def extract_base(code: str) -> str:
    """Return numeric prefix (e.g. '6.1.1' from '6.1.1 Pflegesituation')."""
    if not isinstance(code, str):
        return ""
    m = re.match(r"^\d+(?:\.\d+)*", code)
    return m.group(0) if m else ""


def unique_id(filename: str, matched_code: str, counter: int = 0) -> str:
    """Produce a reproducible short unique ID over all files."""
    base = f"{filename}_{matched_code}_{counter}"
    return base


def extract_sequence_windows(
    csv_path: str,
    main_code: str,
    event_codes: List[str],
    output_csv: str = "sequence_output.csv",
) -> pd.DataFrame:
    """
    Find time windows of `main_code` and inside each window
    include rows whose Sequence_Code belongs to `event_codes`.
    Output flat table (Filename, Sequence_Code, Sequence_Start, Sequence_End, id)
    """

    df = pd.read_csv(csv_path)

    required = [
        "Filename",
        "Matched_Code",
        "Sequence_Code",
        "Sequence_Start",
        "Sequence_End",
    ]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")

    # Convert time columns
    for c in ["Sequence_Start", "Sequence_End"]:
        df[c + "_sec"] = df[c].apply(parse_time_to_seconds)

    # Extract code prefixes
    df["Sequence_Base"] = df["Sequence_Code"].apply(extract_base)
    df["Matched_Base"] = df["Matched_Code"].apply(extract_base)

    main_prefix = extract_base(main_code)
    event_prefixes = [extract_base(c) for c in event_codes]

    out_rows = []

    for n, ((fname, matched), sub) in enumerate(
        df.groupby(["Filename", "Matched_Code"], dropna=False)
    ):
        # find all main-code intervals in group
        mains = sub[sub["Sequence_Base"] == main_prefix]
        if mains.empty:
            continue

        # unique id for this File + Matched_Code
        uid = unique_id(fname, n)

        for _, mrow in mains.iterrows():
            start = mrow["Sequence_Start_sec"]
            end = mrow["Sequence_End_sec"]
            if end <= start:
                continue

            in_window = sub[
                (sub["Sequence_Start_sec"] >= start)
                & (sub["Sequence_End_sec"] <= end)
                & (sub["Sequence_Base"].isin(event_prefixes))
            ].copy()

            if in_window.empty:
                continue

            temp = in_window[
                ["Filename", "Sequence_Code", "Sequence_Start", "Sequence_End"]
            ].copy()
            temp["id"] = uid
            out_rows.append(temp)

            # also include the main-code itself in the same window
            end_sec = parse_time_to_seconds(mrow["Sequence_End"])
            start_sec = parse_time_to_seconds(mrow["Sequence_Start"])
            print(f"{start_sec}, {end_sec}")
            main_row = pd.DataFrame(
                [
                    {
                        "Filename": fname,
                        "Sequence_Code": mrow["Sequence_Code"],
                        "Sequence_Start": mrow["Sequence_Start"],
                        "Sequence_End": mrow["Sequence_End"],
                        "Length": end_sec - start_sec,
                        "id": uid,
                    }
                ]
            )
            out_rows.append(main_row)

    if not out_rows:
        print("No events found inside windows.")
        return pd.DataFrame(
            columns=[
                "Filename",
                "Sequence_Code",
                "Sequence_Start",
                "Sequence_End",
                "id",
            ]
        )

    result = pd.concat(out_rows, ignore_index=True)

    # Sort by filename and start time numeric order
    result["start_sec"] = result["Sequence_Start"].apply(parse_time_to_seconds)
    result.sort_values(["Filename", "start_sec"], inplace=True)
    result.drop(columns="start_sec", inplace=True)

    result.to_csv(output_csv, index=False)
    print(f"✅ Saved {len(result)} rows to {output_csv}")
    return result


# ---------------- Example usage ----------------
if __name__ == "__main__":
    csv_file = "../data/transformed/analysis_results/sequence_analysis.csv"

    main_code = "6.1.1"  # the code defining the analysis window
    codes_of_interest = [
        "2.1.2.1",
        "2.1.2.2",
        "2.1.2.3",
        "2.1.2.4",
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
        "5.2.1",
        "5.2.2",
    ]

    result_df = extract_sequence_windows(
        csv_file,
        main_code,
        codes_of_interest,
        output_csv="selected_events_by_main_code.csv",
    )

    print(result_df.head())
