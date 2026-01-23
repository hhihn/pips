#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Option B: Ein Bundle (gleicher Start UND Ende) kann mehrere Schritte erzeugen.

- Pfadfenster = 6.1.1-Intervall(e) pro Filename (jeder 6.1.1-Eintrag = eigener Pfad)
- Parallelität = exakt gleiche Start- UND Endzeit (Bundles)
- Abfolge = Bundles nach Startzeit sortiert
- Bundle -> MULTI-Step (synthetische Reihenfolge innerhalb eines Bundles)
- Mapping auf Textlabels
- Outputs:
  * per-path Sequenzen (Labels)
  * per-path Sequenzen roh (Codes pro Schritt)
  * Transition edge list (counts + probabilities) global + per-path
  * optional Sunburst (global) mit p(child|parent) im Hover

Hinweis:
Die Reihenfolge "innerhalb eines Bundles" ist eine REGEL (nicht beobachtbar),
weil die Codes exakt gleichzeitig sind.

Install (falls Sunburst gewünscht):
  pip install pandas plotly
"""

import argparse
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Any

import pandas as pd

try:
    import plotly.express as px
except Exception:
    px = None


# -----------------------------
# 1) Labeling
# -----------------------------
LABEL_MAP: Dict[str, str] = {
    # innen / Auslöser
    "2.1.2.3": "FK benennt Ziel",
    "6.5.1": "Kindliches Signal",

    # mitte
    "6.4.2": "Aufforderung Vorb.",
    "6.5.4": "Verbale Begleitung",
    "2.1.3.1": "FK führt Hdlg. aus",

    # außen
    "6.5.3": "K führt Hdlg aus",
    "6.4.3": "FK von vorn",
    "6.4.4": "FK von der Seite",
    "6.4.5": "FK von hinten",

    # außenring
    "2.1.3.5": "Unterstützung nur verbal",
    "2.2.3.14": "KK Objektbezug",
    "2.2.3.4": "KK Halten",
    "2.1.3.1 & 6.4.3": "FK führt Hdlg. von vorn aus",
    "2.1.3.1 & 6.4.4": "FK führt Hdlg. von der Seite aus",
    "2.1.3.1 & 6.4.5": "FK führt Hdlg. von Hinten aus",
    "2.1.3.1 & 2.2.3.4": "FK führt Hdlg. und hält Kind fest",
    "2.2.3.4 & 2.2.3.14": "KK Halten + Objektbezug",

    # neue Kombis für Option B (Handlung + Objektbezug etc.)
    "2.1.3.1 & 2.2.3.14": "FK führt Hdlg. aus + Objektbezug",
}

# Codes, die "Rahmen" sind und normalerweise NICHT in die Event-Sequenz sollen
DEFAULT_IGNORE_CODES = {"6.1.1", "6.1.2", "6.2.1", "6.2.2", "6.1.3", "6.1.4"}


# -----------------------------
# 2) Hilfsfunktionen
# -----------------------------
def parse_time_to_seconds(s: str) -> float:
    """
    "0:00:36,3" -> 36.3
    """
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
        ms = int(ms_str)
        frac = ms / (10 ** len(ms_str))
    else:
        sec = int(sec_ms)
        frac = 0.0
    return h * 3600 + m * 60 + sec + frac


def normalize_code(code: str) -> str:
    """
    "6.4.5 PK" -> "6.4.5"
    """
    code = str(code).strip()
    return code.split()[0]


def bundle_key_exact(start_raw: str, end_raw: str) -> Tuple[str, str]:
    """
    Parallelität: exakt gleiche Start- UND Endzeit.
    """
    return (str(start_raw).strip().strip('"'), str(end_raw).strip().strip('"'))


def label_for_code(code: str) -> str:
    return LABEL_MAP.get(code, code)


# -----------------------------
# 3) OPTION B: Bundle -> Multi-Step
# -----------------------------
def bundle_steps(codes_in_bundle: List[str]) -> List[Dict[str, Any]]:
    """
    Erzeugt mehrere "Steps" aus einem Bundle.
    Jeder Step ist dict:
      {
        "label": <Textlabel>,
        "codes": [<codes die diesen Step auslösen>]
      }

    Reihenfolge innerhalb eines Bundles (synthetisch):
      1) Auslöser: 2.1.2.3 / 6.5.1 (falls vorhanden)
      2) Vorbereitung/Verbale Begleitung (6.4.2, 6.5.4) (falls vorhanden)
      3) Richtung (6.4.3/6.4.4/6.4.5) (falls vorhanden)
      4) Handlung (6.5.3 oder 2.1.3.1) ggf. mit Objektbezug (2.2.3.14)
      5) Halten (2.2.3.4) als separater Step, auch wenn gleichzeitig
         (und optional: wenn 2.2.3.4+2.2.3.14 ohne Handlung -> Kombistep)
    """
    s = set(codes_in_bundle)
    steps: List[Dict[str, Any]] = []

    # 1) Auslöser
    for trig in ["2.1.2.3", "6.5.1"]:
        if trig in s:
            steps.append({"label": label_for_code(trig), "codes": [trig]})

    # 2) Mitte
    for mid in ["6.4.2", "6.5.4"]:
        if mid in s:
            steps.append({"label": label_for_code(mid), "codes": [mid]})

    # 3) Richtung (genau eine, falls mehrere -> sortiert alle nacheinander)
    dir_codes = [c for c in ["6.4.3", "6.4.4", "6.4.5"] if c in s]
    for dc in dir_codes:
        steps.append({"label": label_for_code(dc), "codes": [dc]})

    # 4) Handlung / Aktion
    # Fall A: FK-Handlung + Objektbezug gemeinsam
    if "2.1.3.1" in s and "2.2.3.14" in s:
        steps.append(
            {"label": LABEL_MAP["2.1.3.1 & 2.2.3.14"], "codes": ["2.1.3.1", "2.2.3.14"]}
        )
    if "2.1.3.1" in s and "6.4.3" in s:
        steps.append(
            {"label": LABEL_MAP["2.1.3.1 & 6.4.3"], "codes": ["2.1.3.1", "6.4.3"]}
        )
    if "2.1.3.1" in s and "6.4.4" in s:
        steps.append(
            {"label": LABEL_MAP["2.1.3.1 & 6.4.4"], "codes": ["2.1.3.1", "6.4.4"]}
        )
    if "2.1.3.1" in s and "6.4.5" in s:
        steps.append(
            {"label": LABEL_MAP["2.1.3.1 & 6.4.5"], "codes": ["2.1.3.1", "6.4.5"]}
        )
    else:
        # FK Handlung allein
        if "2.1.3.1" in s:
            steps.append({"label": label_for_code("2.1.3.1"), "codes": ["2.1.3.1"]})
        # K Handlung allein
        if "6.5.3" in s:
            steps.append({"label": label_for_code("6.5.3"), "codes": ["6.5.3"]})
        # Objektbezug allein (wenn nicht schon mit Handlung kombiniert)
        if "2.2.3.14" in s:
            steps.append({"label": label_for_code("2.2.3.14"), "codes": ["2.2.3.14"]})

    # 5) Halten als eigener Step (auch wenn gleichzeitig)
    # Sonderfall: wenn es NUR haptische Kombi ist (Halten+Objektbezug) und keine FK-Handlung,
    # kann man stattdessen den Kombistep nehmen und Halten nicht extra ausgeben.
    if "2.2.3.4" in s and "2.2.3.14" in s and "2.1.3.1" not in s:
        steps.append(
            {"label": LABEL_MAP["2.2.3.4 & 2.2.3.14"], "codes": ["2.2.3.4", "2.2.3.14"]}
        )
    elif "2.2.3.4" in s:
        steps.append({"label": label_for_code("2.2.3.4"), "codes": ["2.2.3.4"]})

    # optional: Unterstützung nur verbal
    if "2.1.3.5" in s:
        steps.append({"label": label_for_code("2.1.3.5"), "codes": ["2.1.3.5"]})

    # Falls Bundle sonst gar nichts liefert (selten), fallback auf "irgendein code"
    if not steps and s:
        c = sorted(s)[0]
        steps.append({"label": label_for_code(c), "codes": [c]})

    # dedupe gleiche Labels direkt hintereinander innerhalb des Bundles
    cleaned: List[Dict[str, Any]] = []
    for st in steps:
        if not cleaned or cleaned[-1]["label"] != st["label"]:
            cleaned.append(st)
    return cleaned


@dataclass
class PathInstance:
    filename: str
    path_index: int
    start: float
    end: float
    sequence_labels: List[str]
    sequence_steps_raw: List[Dict[str, Any]]  # pro Step: label, codes, bundle_start/end
    bundle_rows: pd.DataFrame


# -----------------------------
# 4) Pfade bauen
# -----------------------------
def build_paths_from_df(
    df: pd.DataFrame,
    ignore_codes: Optional[set] = None,
    window_code: str = "6.1.1",
    collapse_consecutive_duplicates: bool = False,
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

        windows = g[g["code"] == window_code][["start_s", "end_s", "start_raw", "end_raw"]].copy()
        if len(windows) == 0:
            continue
        windows = windows.reset_index(drop=True)

        for idx, w in windows.iterrows():
            w_start = float(w["start_s"])
            w_end = float(w["end_s"])

            in_win = g[(g["start_s"] < w_end) & (g["end_s"] > w_start)].copy()
            in_seq = in_win[~in_win["code"].isin(ignore_codes)].copy()

            # bundle by exact (start_raw, end_raw)
            in_seq["bundle_key"] = in_seq.apply(
                lambda r: bundle_key_exact(r["start_raw"], r["end_raw"]), axis=1
            )

            bundles = []
            sequence_steps_raw: List[Dict[str, Any]] = []
            sequence_labels: List[str] = []

            for bk, bg in in_seq.groupby("bundle_key", sort=False):
                b_start = bg["start_s"].min()
                b_end = bg["end_s"].max()
                codes = sorted(set(bg["code"].tolist()))
                bundles.append((b_start, b_end, bk[0], bk[1], codes))

            # sort bundles by start time
            bundles.sort(key=lambda x: (x[0], x[1], ",".join(x[4])))

            # expand bundles into multi-steps
            for (b_start, b_end, b_start_raw, b_end_raw, codes) in bundles:
                steps = bundle_steps(codes)
                for st in steps:
                    sequence_labels.append(st["label"])
                    sequence_steps_raw.append(
                        {
                            "Filename": filename,
                            "path_index": idx,
                            "bundle_start_s": b_start,
                            "bundle_end_s": b_end,
                            "bundle_start_raw": b_start_raw,
                            "bundle_end_raw": b_end_raw,
                            "step_label": st["label"],
                            "step_codes": " & ".join(st["codes"]),
                        }
                    )

            # optional: collapse consecutive duplicates (meist aus!)
            if collapse_consecutive_duplicates:
                collapsed = []
                collapsed_raw = []
                for lab, raw in zip(sequence_labels, sequence_steps_raw):
                    if not collapsed or collapsed[-1] != lab:
                        collapsed.append(lab)
                        collapsed_raw.append(raw)
                sequence_labels = collapsed
                sequence_steps_raw = collapsed_raw

            # debug table
            bundle_debug = pd.DataFrame(
                bundles,
                columns=["bundle_start_s", "bundle_end_s", "bundle_start_raw", "bundle_end_raw", "bundle_codes"],
            )

            paths.append(
                PathInstance(
                    filename=filename,
                    path_index=idx,
                    start=w_start,
                    end=w_end,
                    sequence_labels=sequence_labels,
                    sequence_steps_raw=sequence_steps_raw,
                    bundle_rows=bundle_debug,
                )
            )

    return paths


# -----------------------------
# 5) Transitions + Sunburst helper
# -----------------------------
def transitions_from_sequences(seqs: List[List[str]]) -> pd.DataFrame:
    edges: Dict[Tuple[str, str], int] = {}
    out_counts: Dict[str, int] = {}

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


def sequences_to_sunburst_df(seqs: List[List[str]], max_depth: int = 12) -> pd.DataFrame:
    counts: Dict[Tuple[str, ...], int] = {}
    for seq in seqs:
        if not seq:
            continue
        truncated = tuple(seq[:max_depth])
        counts[truncated] = counts.get(truncated, 0) + 1

    rows = []
    for path, c in counts.items():
        row = {f"step{i+1}": (path[i] if i < len(path) else None) for i in range(max_depth)}
        row["value"] = c
        rows.append(row)
    return pd.DataFrame(rows)


def add_conditional_probs_for_sunburst(df_wide: pd.DataFrame, max_depth: int) -> pd.DataFrame:
    nodes: Dict[Tuple[str, str], int] = {}

    for _, r in df_wide.iterrows():
        value = int(r["value"])
        steps = [r.get(f"step{i+1}") for i in range(max_depth)]
        steps = [s for s in steps if s is not None and str(s).strip() != ""]
        parent = "ROOT"
        for s in steps:
            node_id = (parent, s)
            nodes[node_id] = nodes.get(node_id, 0) + value
            parent = f"{parent}||{s}"

    parent_sums: Dict[str, int] = {}
    for (parent, _label), v in nodes.items():
        parent_sums[parent] = parent_sums.get(parent, 0) + v

    long_rows = []
    for (parent, label), v in nodes.items():
        denom = parent_sums.get(parent, 0)
        p = v / denom if denom > 0 else math.nan
        long_rows.append({"parent": parent, "label": label, "value": v, "p_child_given_parent": p})

    return pd.DataFrame(long_rows)


# -----------------------------
# 6) Main
# -----------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="extracted_sequences.csv", help="Input CSV")
    ap.add_argument("--out_prefix", default="out_transitions", help="Prefix für Output-Dateien")
    ap.add_argument("--max_depth", type=int, default=30, help="Max Tiefe für Sunburst-Sequenzen")
    ap.add_argument("--no_sunburst", action="store_true", help="Kein Sunburst erzeugen (falls plotly fehlt)")
    ap.add_argument("--debug_one", default=None, help="Filename für Debug-Ausgabe")
    ap.add_argument("--collapse", action="store_true", help="Consecutive duplicate labels collapsen (default: AUS)")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)

    paths = build_paths_from_df(df, collapse_consecutive_duplicates=args.collapse)
    all_seqs = [p.sequence_labels for p in paths]

    # Global transitions
    global_edges = transitions_from_sequences(all_seqs)
    global_edges.to_csv(f"{args.out_prefix}_global_edges.csv", index=False)

    # Per-path edges
    per_path_rows = []
    for p in paths:
        seq = p.sequence_labels
        for a, b in zip(seq[:-1], seq[1:]):
            per_path_rows.append({"Filename": p.filename, "path_index": p.path_index, "from": a, "to": b})
    pd.DataFrame(per_path_rows).to_csv(f"{args.out_prefix}_per_path_edges.csv", index=False)

    # Per-path sequences (labels)
    seq_rows = []
    for p in paths:
        seq_rows.append({"Filename": p.filename, "path_index": p.path_index, "sequence": " -> ".join(p.sequence_labels)})
    pd.DataFrame(seq_rows).to_csv(f"{args.out_prefix}_per_path_sequences.csv", index=False)

    # Per-path sequences RAW (Step-level with codes and bundle times)
    raw_rows = []
    for p in paths:
        raw_rows.extend(p.sequence_steps_raw)
    pd.DataFrame(raw_rows).to_csv(f"{args.out_prefix}_per_path_steps_raw.csv", index=False)

    # Debug print
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
                print("\nBundles (exact start/end groups):")
                print(p.bundle_rows.to_string(index=False))
                print("\nExpanded steps (raw):")
                print(pd.DataFrame(p.sequence_steps_raw).to_string(index=False))

    print(
        f"[OK] Wrote:\n"
        f" - {args.out_prefix}_global_edges.csv\n"
        f" - {args.out_prefix}_per_path_edges.csv\n"
        f" - {args.out_prefix}_per_path_sequences.csv\n"
        f" - {args.out_prefix}_per_path_steps_raw.csv"
    )

    # Sunburst (global)
    if args.no_sunburst:
        return
    if px is None:
        print("[WARN] plotly not available; skipping sunburst.")
        return

    wide = sequences_to_sunburst_df(all_seqs, max_depth=args.max_depth)
    long_nodes = add_conditional_probs_for_sunburst(wide, max_depth=args.max_depth)

    # unique ids
    long_nodes["id"] = long_nodes.apply(lambda r: f"{r['parent']}||{r['label']}", axis=1)
    long_nodes["parent_id"] = long_nodes["parent"].map(lambda p: "" if p == "ROOT" else p)

    fig = px.sunburst(
        long_nodes,
        ids="id",
        parents="parent_id",
        names="label",
        values="value",
    )
    fig.update_traces(
        hovertemplate="<b>%{label}</b><br>"
        "count=%{value}<br>"
        "p(child|parent)=%{customdata:.3f}<extra></extra>",
        customdata=long_nodes["p_child_given_parent"],
    )

    html_path = f"{args.out_prefix}_sunburst_global.html"
    fig.write_html(html_path)
    print(f"[OK] Wrote: {html_path}")


if __name__ == "__main__":
    main()
