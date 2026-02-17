#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Zeitmuster-Check + Sunburst aus Pfad-CSV

NEU (Signatur-Ansatz):
- Pro Pfad wird die Sequenz in 4 Teile gepresst: innen -> mitte -> außen -> außenring
- Für jeden Teil: suche innerhalb der ersten N Events, ob ein Code dieser Gruppe vorkommt
  - wenn ja: nimm den frühesten (tie-break über Priorität)
  - wenn nein: "Andere"
- Ignoriere alle Codes außerhalb der PRIO_GROUPS
"""

import argparse
from typing import Dict, List, Tuple, Any

import pandas as pd

from src.sunburst.cooccurrrence import (
    create_cooccurrence_summary,
    analyze_code_cooccurrences,
)
from src.sunburst.helper import (
    normalize_code,
    parse_time_to_seconds,
    pick_group_token_from_first_n,
    label_for_token,
    customwrap,
    wide_to_sunburst_nodes,
    sequences_to_sunburst_wide,
)
from src.sunburst.postprocessing import postprocess_sequence
from src.sunburst.util import (
    ALLOWED_CODES,
    CODE_TO_PRIO,
    PLACEHOLDER_OTHER,
    GROUP_NAME_TO_CODES,
)

try:
    import plotly.express as px
except Exception:
    px = None


def build_sequences_from_paths_csv(
    df: pd.DataFrame,
    start_lookahead_n: int = 12,
) -> Tuple[List[List[str]], pd.DataFrame]:
    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    d = d[d["code"].isin(ALLOWED_CODES)].copy()

    sequences_labels: List[List[str]] = []
    per_path_rows: List[Dict[str, Any]] = []
    group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]

    for key, g in d.groupby(group_cols, sort=True):
        if isinstance(key, tuple):
            filename, pid = key
        else:
            filename, pid = key, ""

        # Sort by time
        g_sorted = g.copy()
        g_sorted["code_priority"] = g_sorted["code"].map(
            lambda c: CODE_TO_PRIO.get(c, (999, 999))
        )
        g_sorted = g_sorted.sort_values(by=["start_s", "end_s", "code_priority"]).drop(
            "code_priority", axis=1
        )

        print(f"es gibt {len(g_sorted)} atoms:", g_sorted)

        bundles = []
        for (bs, be), bundle_group in g_sorted.groupby(
            ["start_s", "end_s"], sort=False
        ):
            bundles.append(
                {
                    "start_s": float(bs),
                    "end_s": float(be),
                    "codes": bundle_group["code"].tolist(),
                    "data": bundle_group.copy(),
                }
            )

        # Sort bundles by start time, then end time
        bundles.sort(key=lambda b: (b["start_s"], b["end_s"]))

        print(f"Found {len(bundles)} unique temporal bundles")
        for i, b in enumerate(bundles):
            print(f"  Bundle {i}: ({b['start_s']}, {b['end_s']}) -> {b['codes']}")

        n_bundles = len(bundles)
        if n_bundles == 0:
            innen_tok = PLACEHOLDER_OTHER
            mitte_tok = PLACEHOLDER_OTHER
            aussen_tok = PLACEHOLDER_OTHER
            aussenring_tok = PLACEHOLDER_OTHER
        else:
            # Limit to start_lookahead_n bundles
            bundles = bundles[: max(4, start_lookahead_n)]
            n_bundles = len(bundles)

            # Split bundles into 4 temporal phases (not event count)
            base = n_bundles // 4
            rem = n_bundles % 4
            sizes = [base + (1 if i < rem else 0) for i in range(4)]

            parts_bundles = []
            idx0 = 0
            for sz in sizes:
                bundle_subset = bundles[idx0 : idx0 + sz]
                # Combine all rows from these bundles into a DataFrame
                dfs = [b["data"] for b in bundle_subset]
                combined_df = (
                    pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
                )
                parts_bundles.append(combined_df)
                idx0 += sz

            innen_df, mitte_df, aussen_df, aussenring_df = parts_bundles

            print("PARTS (by temporal bundles)")
            print("INNEN:", innen_df)
            print("MITTE:", mitte_df)
            print("AUSSEN:", aussen_df)
            print("AUSSENRING:", aussenring_df)

            # Original helper function (unchanged)
            def pick_with_adjacent(parts_list, idx, allowed_codes):
                n_parts = len(parts_list)
                for dist in range(n_parts):
                    candidates = []
                    if dist == 0:
                        candidates = [idx]
                    else:
                        if idx - dist >= 0:
                            candidates.append(idx - dist)
                        if idx + dist < n_parts:
                            candidates.append(idx + dist)
                    for j in candidates:
                        tok = pick_group_token_from_first_n(
                            parts_list[j], allowed_codes
                        )
                        if tok != [PLACEHOLDER_OTHER]:
                            return tok
                return [PLACEHOLDER_OTHER]

            parts_list = [innen_df, mitte_df, aussen_df, aussenring_df]
            innen_tok = pick_with_adjacent(parts_list, 0, GROUP_NAME_TO_CODES["innen"])
            mitte_tok = pick_with_adjacent(parts_list, 1, GROUP_NAME_TO_CODES["mitte"])
            aussen_tok = pick_with_adjacent(
                parts_list, 2, GROUP_NAME_TO_CODES["aussen"]
            )
            aussenring_tok = pick_with_adjacent(
                parts_list, 3, GROUP_NAME_TO_CODES["aussenring"]
            )

        seq_tokens = innen_tok + mitte_tok + aussen_tok + aussenring_tok
        seq_tokens = postprocess_sequence(seq_tokens)
        seq_labels = [label_for_token(t) for t in seq_tokens]
        sequences_labels.append(seq_labels)

        per_path_rows.append(
            {
                "Filename": filename,
                "id": pid,
                "start_group": label_for_token(
                    innen_tok[0] if innen_tok else PLACEHOLDER_OTHER
                ),
                "sequence_tokens": " -> ".join(seq_tokens),
                "sequence_labels": " -> ".join(seq_labels),
                "innen_token": str(innen_tok),
                "mitte_token": str(mitte_tok),
                "aussen_token": str(aussen_tok),
                "aussenring_token": str(aussenring_tok),
                "n_bundles": len(bundles),
                "bundle_sizes": "|".join(
                    map(
                        str,
                        [
                            len(df)
                            for df in (innen_df, mitte_df, aussen_df, aussenring_df)
                        ],
                    )
                )
                if len(parts_bundles) > 0
                else "0|0|0|0",
            }
        )

    per_path_table = pd.DataFrame(per_path_rows)
    return sequences_labels, per_path_table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="../extracted_sequences.csv", help="Input CSV")
    ap.add_argument(
        "--out_prefix", default="out_paths", help="Prefix für Output-Dateien"
    )
    ap.add_argument("--max_depth", type=int, default=4, help="Max Tiefe für Sunburst")
    ap.add_argument(
        "--start_lookahead_n", type=int, default=5, help="Lookahead N Events pro Pfad"
    )
    ap.add_argument(
        "--cooccurrence_csv",
        default="out_paths_cooccurrence_summary.csv",
        help="Path to cooccurrence_summary.csv to load data-driven rules",
    )
    ap.add_argument(
        "--min_window_count",
        type=int,
        default=5,
        help="Min Same_Window_Count to create data-driven rule",
    )
    ap.add_argument("--no_sunburst", action="store_true", help="Kein Sunburst erzeugen")
    args = ap.parse_args()

    # === Load data-driven rules if provided ===
    if args.cooccurrence_csv:
        from src.sunburst.util import load_data_driven_rules

        load_data_driven_rules(
            args.cooccurrence_csv, min_window_count=args.min_window_count
        )

    df = pd.read_csv(args.csv)

    # === Sequence Analysis ===
    seqs_labels, per_path = build_sequences_from_paths_csv(
        df, start_lookahead_n=args.start_lookahead_n
    )
    per_path.to_csv(f"{args.out_prefix}_per_path_sequences.csv", index=False)
    counts = (
        per_path.groupby(["start_group", "sequence_labels"])
        .size()
        .reset_index(name="count")
        .sort_values(["start_group", "count"], ascending=[True, False])
    )
    counts.to_csv(f"{args.out_prefix}_path_counts.csv", index=False)

    # === Co-occurrence Analysis ===
    print("\n[*] Analyzing code co-occurrences...")
    same_start_counts, same_window_counts = analyze_code_cooccurrences(df)
    same_start_counts.to_csv(
        f"{args.out_prefix}_cooccurrence_same_start.csv", index=False
    )
    same_window_counts.to_csv(
        f"{args.out_prefix}_cooccurrence_same_window.csv", index=False
    )
    summary = create_cooccurrence_summary(same_start_counts, same_window_counts)
    summary.to_csv(f"{args.out_prefix}_cooccurrence_summary.csv", index=False)

    # === NEW: "Andere" Analysis ===
    print("\n[*] Analyzing 'Andere' occurrences by ring...")
    from src.sunburst.andere_analysis import (
        analyze_andere_by_ring,
        analyze_codes_causing_andere,
        create_andere_summary,
        print_andere_report,
    )

    andere_by_ring = analyze_andere_by_ring(per_path)
    codes_causing_andere = analyze_codes_causing_andere(df, per_path)

    andere_by_ring.to_csv(f"{args.out_prefix}_andere_by_ring.csv", index=False)
    codes_causing_andere.to_csv(
        f"{args.out_prefix}_codes_in_andere_cases.csv", index=False
    )

    andere_summary = create_andere_summary(andere_by_ring, codes_causing_andere)
    print_andere_report(andere_summary)

    print(
        f"[OK] Wrote:\n"
        f" - {args.out_prefix}_per_path_sequences.csv\n"
        f" - {args.out_prefix}_path_counts.csv\n"
        f" - {args.out_prefix}_cooccurrence_same_start.csv\n"
        f" - {args.out_prefix}_cooccurrence_same_window.csv\n"
        f" - {args.out_prefix}_cooccurrence_summary.csv\n"
        f" - {args.out_prefix}_andere_by_ring.csv\n"
        f" - {args.out_prefix}_codes_in_andere_cases.csv"
    )

    # === Sunburst ===
    if args.no_sunburst:
        return
    if px is None:
        print(
            "[WARN] plotly not installed; skipping sunburst. Install: pip install plotly"
        )
        return

    wide = sequences_to_sunburst_wide(seqs_labels, max_depth=args.max_depth)
    nodes = wide_to_sunburst_nodes(wide, max_depth=args.max_depth)
    nodes["label"] = nodes["label"].map(lambda x: customwrap(x, width=20))

    fig = px.sunburst(
        nodes,
        ids="id",
        parents="parent_id",
        names="label",
        values="value",
    )
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>"
        "count=%{value}<br>"
        "p(child|parent)=%{customdata:.3f}<extra></extra>",
        customdata=nodes["p_child_given_parent"],
    )
    html_path = f"{args.out_prefix}_sunburst.html"
    fig.write_html(html_path)
    print(f"[OK] Wrote: {html_path}")


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
