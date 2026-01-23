#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Transitions aus Sequenz-Codes mit:
- Pfadfenster = 6.1.1-Intervall(e) pro Filename
- Parallelität = exakt gleiche Startzeit (Sequence_Start)
- Abfolge = Bundles nach Startzeit sortiert
- Bundle -> 1 Label (Prioritäten + Kombiregel)
- Outputs: Sequenzen + Transition-Edges (+ optional Sunburst)
"""

import argparse
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

import pandas as pd

try:
    import plotly.express as px
except Exception:
    px = None


# -----------------------------
# 1) Labeling / Regeln
# -----------------------------
LABEL_MAP = {
    # innen
    "2.1.2.3": "FK benennt Ziel",
    "6.5.1": "Kindliches Signal",
    "OTHER": "kein Auslöser",

    # mitte
    "6.4.2": "Aufforderung Vorb.",
    "6.5.4": "Verbale Begleitung",
    "2.1.3.1": "FK führt Hdlg. aus",
    "NONE": "keine Aktion",

    # außen
    "6.5.3": "K führt Hdlg aus",
    "6.4.3": "FK von vorn",
    "6.4.4": "FK von der Seite",
    "6.4.5": "FK von hinten",

    # außenring
    "2.1.3.5": "nur verbal",
    "2.2.3.14": "Objektbezug",
    "2.2.3.4": "Halten",
    "2.2.3.4 & 2.2.3.14": "Halten + Objektbezug",
}

BUNDLE_PRIORITY = [
    "2.2.3.4 & 2.2.3.14",
    "2.2.3.14",
    "2.1.3.5",
    "6.4.5",
    "6.4.4",
    "6.4.3",
    "6.5.3",
    "6.5.4",
    "6.4.2",
    "2.1.3.1",
    "2.1.2.3",
    "6.5.1",
]

DEFAULT_IGNORE_CODES = {"6.1.1", "6.1.2", "6.2.1", "6.2.2", "6.1.3", "6.1.4"}


# -----------------------------
# 2) Hilfsfunktionen
# -----------------------------
def parse_time_to_seconds(s: str) -> float:
    s = str(s).strip().strip('"')
    parts = s.split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected time format: {s}")
    h = int(parts[0])
    m = int(parts[1])
    sec_ms = parts[2]
    if "," in sec_ms:
        sec_str, ms_str = sec_ms.split(",", 1)
        sec = int(sec_str)
        ms_str = ms_str.strip()
        ms = int(ms_str)
        frac = ms / (10 ** len(ms_str))
    else:
        sec = int(sec_ms)
        frac = 0.0
    return h * 3600 + m * 60 + sec + frac


def normalize_code(code: str) -> str:
    code = str(code).strip()
    return code.split()[0]


def bundle_key_start_only(start_raw: str) -> str:
    """
    Parallelität: exakt gleiche Startzeit (als String, damit wirklich exakt).
    """
    return str(start_raw).strip().strip('"')


def bundle_label(codes_in_bundle: List[str]) -> str:
    s = set(codes_in_bundle)

    if "2.2.3.4" in s and "2.2.3.14" in s:
        return LABEL_MAP["2.2.3.4 & 2.2.3.14"]

    for k in BUNDLE_PRIORITY:
        if k == "2.2.3.4 & 2.2.3.14":
            continue
        if k in s:
            return LABEL_MAP.get(k, k)

    if len(s) > 0:
        c = sorted(s)[0]
        return LABEL_MAP.get(c, c)

    return LABEL_MAP["NONE"]


@dataclass
class PathInstance:
    filename: str
    path_index: int
    start: float
    end: float
    sequence_labels: List[str]
    bundle_rows: pd.DataFrame


# -----------------------------
# 3) Kernlogik
# -----------------------------
def build_paths_from_df(
    df: pd.DataFrame,
    ignore_codes: Optional[set] = None,
    window_code: str = "6.1.1",
) -> List[PathInstance]:
    if ignore_codes is None:
        ignore_codes = set(DEFAULT_IGNORE_CODES)

    d = df.copy()
    d["code_raw"] = d["Sequence_Code"]
    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_raw"] = d["Sequence_Start"].astype(str)
    d["end_raw"] = d["Sequence_End"].astype(str)
    d["start_s"] = d["start_raw"].map(parse_time_to_seconds)
    d["end_s"] = d["end_raw"].map(parse_time_to_seconds)

    bad = d[d["start_s"] > d["end_s"]]
    if len(bad) > 0:
        raise ValueError(f"Found {len(bad)} rows with start > end. Example:\n{bad.head(3)}")

    paths: List[PathInstance] = []

    for filename, g in d.groupby("Filename", sort=True):
        g = g.sort_values(["start_s", "end_s", "code"])

        windows = g[g["code"] == window_code][["start_s", "end_s"]].copy()
        if len(windows) == 0:
            continue
        windows = windows.reset_index(drop=True)

        for idx, w in windows.iterrows():
            w_start = float(w["start_s"])
            w_end = float(w["end_s"])

            in_win = g[(g["start_s"] < w_end) & (g["end_s"] > w_start)].copy()
            in_seq = in_win[~in_win["code"].isin(ignore_codes)].copy()

            # === BUNDLING: gleiche Startzeit ===
            in_seq["bundle_key"] = in_seq["start_raw"].map(bundle_key_start_only)

            bundles = []
            for bk, bg in in_seq.groupby("bundle_key", sort=False):
                b_start = bg["start_s"].min()
                b_end = bg["end_s"].max()  # nur Info
                codes = bg["code"].tolist()
                label = bundle_label(codes)
                bundles.append((b_start, b_end, bk, label, sorted(set(codes))))

            bundles.sort(key=lambda x: (x[0], x[1], x[3]))

            seq_labels = [b[3] for b in bundles]

            # Consecutive duplicates entfernen
            seq_collapsed = []
            for lab in seq_labels:
                if not seq_collapsed or seq_collapsed[-1] != lab:
                    seq_collapsed.append(lab)

            bundle_debug = pd.DataFrame(
                bundles,
                columns=["bundle_start_s", "bundle_end_s", "bundle_start_raw", "bundle_label", "bundle_codes"],
            )

            paths.append(
                PathInstance(
                    filename=filename,
                    path_index=idx,
                    start=w_start,
                    end=w_end,
                    sequence_labels=seq_collapsed,
                    bundle_rows=bundle_debug,
                )
            )

    return paths


def transitions_from_sequences(seqs: List[List[str]]) -> pd.DataFrame:
    edges = {}
    out_counts = {}

    for seq in seqs:
        if not seq or len(seq) < 2:
            continue
        for a, b in zip(seq[:-1], seq[1:]):
            edges[(a, b)] = edges.get((a, b), 0) + 1
            out_counts[a] = out_counts.get(a, 0) + 1

    rows = []
    for (a, b), c in edges.items():
        denom = out_counts.get(a, 0)
        p = (c / denom) if denom > 0 else math.nan
        rows.append({"from": a, "to": b, "count": c, "p_to_given_from": p})

    return pd.DataFrame(rows).sort_values(["from", "count"], ascending=[True, False]).reset_index(drop=True)


def sequences_to_sunburst_df(seqs: List[List[str]], max_depth: int = 6) -> pd.DataFrame:
    """
    Wichtig: px.sunburst(path=..., values=...) erwartet Leaf-Zeilen.
    Daher füllen wir kürzere Sequenzen mit 'END' auf, damit sie niemals
    ein Präfix längerer Sequenzen sind.
    """
    END = "END"  # optional: "Ende" o.ä.

    counts = {}
    for seq in seqs:
        if not seq:
            continue

        # auf max_depth begrenzen
        seq = seq[:max_depth]

        # auffüllen bis max_depth mit END
        padded = tuple(seq + [END] * (max_depth - len(seq)))
        counts[padded] = counts.get(padded, 0) + 1

    rows = []
    for path, c in counts.items():
        row = {f"step{i+1}": path[i] for i in range(max_depth)}
        row["value"] = c
        rows.append(row)

    return pd.DataFrame(rows)



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out_prefix", default="out_transitions")
    ap.add_argument("--max_depth", type=int, default=6)
    ap.add_argument("--no_sunburst", action="store_true")
    ap.add_argument("--debug_one", default=None, help="Filename für Debug-Ausgabe")
    args = ap.parse_args()

    df = pd.read_csv("extracted_sequences.csv")

    paths = build_paths_from_df(df)
    all_seqs = [p.sequence_labels for p in paths]

    global_edges = transitions_from_sequences(all_seqs)
    global_edges.to_csv(f"{args.out_prefix}_global_edges.csv", index=False)

    # per-path sequences
    seq_rows = []
    for p in paths:
        seq_rows.append({
            "Filename": p.filename,
            "path_index": p.path_index,
            "sequence": " -> ".join(p.sequence_labels),
        })
    pd.DataFrame(seq_rows).to_csv(f"{args.out_prefix}_per_path_sequences.csv", index=False)

    # debug one
    if args.debug_one:
        subset = [p for p in paths if p.filename == args.debug_one]
        if not subset:
            print(f"[DEBUG] No paths found for Filename={args.debug_one}")
        else:
            for p in subset:
                print("\n" + "=" * 80)
                print(f"[DEBUG] Filename={p.filename} path_index={p.path_index}")
                print("Sequence:")
                print("  " + " -> ".join(p.sequence_labels))
                print("\nBundles (grouped by EXACT same start):")
                print(p.bundle_rows.to_string(index=False))

    print(f"[OK] Wrote:\n"
          f" - {args.out_prefix}_global_edges.csv\n"
          f" - {args.out_prefix}_per_path_sequences.csv")

    # sunburst
    if not args.no_sunburst:
        if px is None:
            print("[WARN] plotly not available; skipping sunburst.")
            return
        wide = sequences_to_sunburst_df(all_seqs, max_depth=args.max_depth)
        fig = px.sunburst(wide, path=[f"step{i+1}" for i in range(args.max_depth)], values="value")
        html_path = f"{args.out_prefix}_sunburst_global.html"
        fig.write_html(html_path)
        print(f"[OK] Wrote: {html_path}")


if __name__ == "__main__":
    main()
