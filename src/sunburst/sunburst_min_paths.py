#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Zeitmuster-Check + Sunburst aus Pfad-CSV
Neu: Toggle zwischen zwei Ansätzen:
1. "Parts Approach" (Standard): Sequenz in 4 Teile (innen/mitte/aussen/aussenring)
2. "All Codes Together": Alle Codes zusammen betrachten
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
from src.sunburst.andere_analysis import (
    analyze_andere_by_ring,
    analyze_codes_causing_andere,
    create_andere_summary,
    print_andere_report,
)
from src.sunburst.postprocessing import postprocess_sequence
from src.sunburst.code_util import CodeUtil

try:
    import plotly.express as px
except Exception:
    px = None


def build_sequences_parts_approach(
        df: pd.DataFrame,
        start_lookahead_n: int = 12,
) -> Tuple[List[List[str]], pd.DataFrame]:
    """Original approach: split sequence into 4 temporal parts (innen/mitte/aussen/aussenring)"""
    code_util = CodeUtil()
    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    d = d[d["code"].isin(code_util.ALLOWED_CODES)].copy()
    sequences_labels: List[List[str]] = []
    per_path_rows: List[Dict[str, Any]] = []
    group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]

    for key, g in d.groupby(group_cols, sort=True):
        if isinstance(key, tuple):
            filename, pid = key
        else:
            filename, pid = key, ""

        g_sorted = g.copy()
        g_sorted["code_priority"] = g_sorted["code"].map(
            lambda c: code_util.CODE_TO_PRIO.get(c, (999, 999))
        )
        g_sorted = g_sorted.sort_values(by=["start_s", "end_s", "code_priority"]).drop(
            "code_priority", axis=1
        )

        bundles = []
        for (bs, be), bundle_group in g_sorted.groupby(["start_s", "end_s"], sort=False):
            bundles.append({
                "start_s": float(bs),
                "end_s": float(be),
                "codes": bundle_group["code"].tolist(),
                "data": bundle_group.copy(),
            })

        bundles.sort(key=lambda b: (b["start_s"], b["end_s"]))

        n_bundles = len(bundles)
        if n_bundles == 0:
            innen_tok = code_util.PLACEHOLDER_OTHER
            mitte_tok = code_util.PLACEHOLDER_OTHER
            aussen_tok = code_util.PLACEHOLDER_OTHER
            aussenring_tok = code_util.PLACEHOLDER_OTHER
            parts_bundles = []
        else:
            bundles = bundles[:max(4, start_lookahead_n)]
            n_bundles = len(bundles)
            base = n_bundles // 4
            rem = n_bundles % 4
            sizes = [base + (1 if i < rem else 0) for i in range(4)]

            parts_bundles = []
            idx0 = 0
            for sz in sizes:
                bundle_subset = bundles[idx0:idx0 + sz]
                dfs = [b["data"] for b in bundle_subset]
                combined_df = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
                parts_bundles.append(combined_df)
                idx0 += sz

            innen_df, mitte_df, aussen_df, aussenring_df = parts_bundles

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
                        tok = pick_group_token_from_first_n(parts_list[j], allowed_codes)
                        if tok != [code_util.PLACEHOLDER_OTHER]:
                            return tok
                return [code_util.PLACEHOLDER_OTHER]

            parts_list = [innen_df, mitte_df, aussen_df, aussenring_df]
            innen_tok = pick_with_adjacent(parts_list, 0, code_util.GROUP_NAME_TO_CODES["innen"])
            mitte_tok = pick_with_adjacent(parts_list, 1, code_util.GROUP_NAME_TO_CODES["mitte"])
            aussen_tok = pick_with_adjacent(parts_list, 2, code_util.GROUP_NAME_TO_CODES["aussen"])
            aussenring_tok = pick_with_adjacent(parts_list, 3, code_util.GROUP_NAME_TO_CODES["aussenring"])

        seq_tokens = innen_tok + mitte_tok + aussen_tok + aussenring_tok
        seq_tokens = postprocess_sequence(seq_tokens)
        seq_labels = [label_for_token(t) for t in seq_tokens]
        sequences_labels.append(seq_labels)

        per_path_rows.append({
            "Filename": filename,
            "id": pid,
            "start_group": label_for_token(innen_tok[0] if innen_tok else code_util.PLACEHOLDER_OTHER),
            "sequence_tokens": " -> ".join(seq_tokens),
            "sequence_labels": " -> ".join(seq_labels),
            "innen_token": str(innen_tok),
            "mitte_token": str(mitte_tok),
            "aussen_token": str(aussen_tok),
            "aussenring_token": str(aussenring_tok),
            "n_bundles": len(bundles) if n_bundles > 0 else 0,
            "bundle_sizes": "|".join(
                map(str, [len(df) for df in parts_bundles])
            ) if parts_bundles else "0|0|0|0",
        })

    per_path_table = pd.DataFrame(per_path_rows)
    return sequences_labels, per_path_table


def build_sequences_all_together(
        df: pd.DataFrame,
        start_lookahead_n: int = 12,
) -> Tuple[List[List[str]], pd.DataFrame]:
    """Alternative approach: consider all codes together without parts division"""
    code_util = CodeUtil()
    d = df.copy()
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
    d = d[d["code"].isin(code_util.ALLOWED_CODES)].copy()
    sequences_labels: List[List[str]] = []
    per_path_rows: List[Dict[str, Any]] = []
    group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]

    for key, g in d.groupby(group_cols, sort=True):
        if isinstance(key, tuple):
            filename, pid = key
        else:
            filename, pid = key, ""

        g_sorted = g.copy()
        g_sorted["code_priority"] = g_sorted["code"].map(
            lambda c: code_util.CODE_TO_PRIO.get(c, (999, 999))
        )
        g_sorted = g_sorted.sort_values(by=["start_s", "end_s", "code_priority"]).drop(
            "code_priority", axis=1
        )

        # Limit to first N events
        first_n = g_sorted.head(max(4, start_lookahead_n)).copy()

        if first_n.empty:
            seq_tokens = [code_util.PLACEHOLDER_OTHER]
        else:
            # Get all unique codes (without parts division)
            all_codes = sorted(first_n["code"].unique().tolist())
            seq_tokens = all_codes if all_codes else [code_util.PLACEHOLDER_OTHER]

        seq_tokens = postprocess_sequence(seq_tokens)
        seq_labels = [label_for_token(t) for t in seq_tokens]
        sequences_labels.append(seq_labels)

        per_path_rows.append({
            "Filename": filename,
            "id": pid,
            "start_group": "All Codes Together",
            "sequence_tokens": " -> ".join(seq_tokens),
            "sequence_labels": " -> ".join(seq_labels),
            "all_codes_token": str(seq_tokens),
            "n_events": len(first_n),
        })

    per_path_table = pd.DataFrame(per_path_rows)
    return sequences_labels, per_path_table


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="../extracted_sequences.csv", help="Input CSV")
    ap.add_argument("--out_prefix", default="out_paths", help="Prefix für Output-Dateien")
    ap.add_argument("--max_depth", type=int, default=4, help="Max Tiefe für Sunburst")
    ap.add_argument("--start_lookahead_n", type=int, default=5, help="Lookahead N Events pro Pfad")
    ap.add_argument(
        "--cooccurrence_csv",
        default="out_paths_cooccurrence_same_window.csv",
        help="Path to cooccurrence CSV",
    )
    ap.add_argument("--min_window_count", type=int, default=5)
    ap.add_argument("--refresh_data_driven_rules", action="store_true", default=False)
    ap.add_argument("--no_sunburst", action="store_true")

    # === FEATURE TOGGLE: Choose analysis approach ===
    ap.add_argument(
        "--all_codes_together",
        action="store_true",
        default=False,
        help="Use all-codes-together approach. Overrides --use_parts_approach"
    )

    args = ap.parse_args()

    # === Load data-driven rules ===
    if args.cooccurrence_csv:
        code_util = CodeUtil()
        code_util.load_data_driven_rules(
            args.cooccurrence_csv,
            min_window_count=args.min_window_count,
            refresh=False
        )

    df = pd.read_csv(args.csv)

    # === FEATURE TOGGLE: Select analysis approach ===
    if args.all_codes_together:
        print("[*] Using ALL_CODES_TOGETHER approach")
        seqs_labels, per_path = build_sequences_all_together(
            df, start_lookahead_n=args.start_lookahead_n
        )
    else:
        print("[*] Using PARTS_APPROACH (4 rings: innen/mitte/aussen/aussenring)")
        seqs_labels, per_path = build_sequences_parts_approach(
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
    same_start_counts.to_csv(f"{args.out_prefix}_cooccurrence_same_start.csv", index=False)
    same_window_counts.to_csv(f"{args.out_prefix}_cooccurrence_same_window.csv", index=False)
    summary = create_cooccurrence_summary(same_start_counts, same_window_counts)
    summary.to_csv(f"{args.out_prefix}_cooccurrence_summary.csv", index=False)

    # === "Andere" Analysis ===
    if not args.all_codes_together:
        print("\n[*] Analyzing 'Andere' occurrences...")
        andere_by_ring = analyze_andere_by_ring(per_path)
        codes_causing_andere = analyze_codes_causing_andere(df, per_path)
        andere_by_ring.to_csv(f"{args.out_prefix}_andere_by_ring.csv", index=False)
        codes_causing_andere.to_csv(f"{args.out_prefix}_codes_in_andere_cases.csv", index=False)
        andere_summary = create_andere_summary(andere_by_ring, codes_causing_andere)
        print_andere_report(andere_summary)

    print(f"[OK] Wrote output files with prefix: {args.out_prefix}")

    # === Sunburst ===
    if args.no_sunburst or px is None:
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
        hovertemplate="<b>%{label}</b><br>count=%{value}<br>p(child|parent)=%{customdata:.3f}<extra></extra>",
        customdata=nodes["p_child_given_parent"],
    )
    html_path = f"{args.out_prefix}_sunburst.html"
    fig.write_html(html_path)
    print(f"[OK] Wrote: {html_path}")


if __name__ == "__main__":
    main()