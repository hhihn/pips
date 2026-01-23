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
import math
from typing import Dict, List, Tuple, Any, Optional

import pandas as pd

try:
    import plotly.express as px
except Exception:
    px = None


# -------------------------------------------------------------------
# 1) Labeling (dein Mapping)
# -------------------------------------------------------------------
LABEL_MAP: Dict[str, str] = {
    # innen / Auslöser
    "2.1.2.3": "FK benennt Ziel",
    "6.5.1": "Kindliches Signal",

    # mitte
    "6.4.2": "Aufforderung Vorb.",
    "6.5.4": "Verbale Begleitung",

    # außen
    "2.1.3.1": "FK führt Hdlg. aus",
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
    "2.1.3.1 & 2.2.3.14": "FK führt Hdlg. aus + Objektbezug",
}

PLACEHOLDER_OTHER = "Andere"


# -------------------------------------------------------------------
# 2) Prioritätsliste
# -------------------------------------------------------------------
PRIO_GROUPS: List[Tuple[str, List[str]]] = [
    ("innen", ["2.1.2.3", "6.5.1"]),
    ("mitte", ["6.4.2", "6.5.4"]),
    ("aussen", ["2.1.3.1", "6.5.3", "6.4.3", "6.4.4", "6.4.5"]),
    ("aussenring", ["2.1.3.5", "2.2.3.14", "2.2.3.4"]),
]

CODE_TO_PRIO = {}
for gi, (_gname, codes) in enumerate(PRIO_GROUPS):
    for ci, c in enumerate(codes):
        CODE_TO_PRIO[c] = (gi, ci)

ALLOWED_CODES = set(CODE_TO_PRIO.keys())

GROUP_NAME_TO_CODES: Dict[str, set] = {name: set(codes) for name, codes in PRIO_GROUPS}

# Kombi-Regeln (innerhalb exakt gleicher (start,end)-Bundles)
COMBO_RULES: List[Tuple[Tuple[str, str], str]] = [
    (("2.1.3.1", "6.4.3"), "2.1.3.1 & 6.4.3"),
    (("2.1.3.1", "6.4.4"), "2.1.3.1 & 6.4.4"),
    (("2.1.3.1", "6.4.5"), "2.1.3.1 & 6.4.5"),
    (("2.1.3.1", "2.2.3.14"), "2.1.3.1 & 2.2.3.14"),
    (("2.1.3.1", "2.2.3.4"), "2.1.3.1 & 2.2.3.4"),
    (("2.2.3.4", "2.2.3.14"), "2.2.3.4 & 2.2.3.14"),
]

# Welche Tokens zählen als "Action vorhanden?" (sonst Pfad verwerfen)
ACTING_CODES = {
    "2.1.3.1", "6.5.3",
    "2.1.3.1 & 6.4.3",
    "2.1.3.1 & 6.4.4",
    "2.1.3.1 & 6.4.5",
    "2.1.3.1 & 2.2.3.4",
    "2.2.3.4 & 2.2.3.14",
    "2.1.3.1 & 2.2.3.14",
}


# -------------------------------------------------------------------
# 3) Hilfsfunktionen
# -------------------------------------------------------------------
def parse_time_to_seconds(s: Any) -> float:
    s = str(s).strip().strip('"')
    parts = s.split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected time format: {s}")
    h = int(parts[0])
    m = int(parts[1])
    sec_ms = parts[2].replace(".", ",")
    if "," in sec_ms:
        sec_str, ms_str = sec_ms.split(",", 1)
        sec = int(sec_str)
        frac = int(ms_str) / (10 ** len(ms_str))
    else:
        sec = int(sec_ms)
        frac = 0.0
    return h * 3600 + m * 60 + sec + frac


def normalize_code(code: Any) -> str:
    code = str(code).strip()
    return code.split()[0]


def is_combo_token(token: str) -> bool:
    return " & " in token


def atomic_codes(token: str) -> List[str]:
    parts = [p.strip() for p in token.split("&")]
    return [p for p in parts if p]


def normalize_combo_key(codes: List[str]) -> str:
    def _key(c: str):
        return CODE_TO_PRIO.get(c, (999, 999, c))
    codes_sorted = sorted(set(codes), key=_key)
    return " & ".join(codes_sorted)


def label_for_token(token: str) -> str:
    if token in LABEL_MAP:
        return LABEL_MAP[token]
    if not is_combo_token(token):
        return LABEL_MAP.get(token, token)
    atoms = atomic_codes(token)
    atom_labels = [LABEL_MAP.get(a, a) for a in atoms]
    return " + ".join(atom_labels)


def apply_bundle_combos(codes: List[str]) -> List[str]:
    """
    Wendet Kombi-Regeln innerhalb eines Bundles an.
    Input: codes (atomare Codes) innerhalb exakt gleicher (start,end)
    Output: Liste aus Kombi-Tokens und ggf. Rest-atomaren Codes
    """
    s = set(codes)
    out: List[str] = []

    for (a, b), combo in COMBO_RULES:
        if a in s and b in s:
            out.append(combo)
            s.remove(a)
            s.remove(b)

    out.extend(sorted(s, key=lambda c: CODE_TO_PRIO.get(c, (999, 999))))
    return out


def pick_group_token_from_first_n(
    first_n_events: pd.DataFrame,
    group_codes: set,
) -> str:
    """
    Wählt für eine Gruppe (innen/mitte/außen/außenring) das früheste Token
    innerhalb first_n_events.
    - berücksichtigt COMBO_RULES pro Bundle
    - wenn nichts gefunden: PLACEHOLDER_OTHER
    """
    if first_n_events.empty:
        return PLACEHOLDER_OTHER

    # bundles in first_n (exakt start/end)
    fe = first_n_events.copy()
    fe["bundle_key"] = list(zip(fe["start_s"], fe["end_s"]))

    candidates: List[Tuple[float, float, Tuple[int, int, str], str]] = []
    # (start_s, end_s, prio, token)

    for (bs, be), bg in fe.groupby("bundle_key", sort=False):
        atom_codes = sorted(set(bg["code"].tolist()), key=lambda c: CODE_TO_PRIO.get(c, (999, 999)))
        tokens = apply_bundle_combos(atom_codes)

        for tok in tokens:
            atoms = atomic_codes(tok) if is_combo_token(tok) else [tok]
            if any(a in group_codes for a in atoms):
                # Priority for tie-break: min priority of involved atomic codes
                pr = min([CODE_TO_PRIO.get(a, (999, 999)) for a in atoms])
                candidates.append((float(bs), float(be), (pr[0], pr[1], tok), tok))

    if not candidates:
        return PLACEHOLDER_OTHER

    candidates.sort(key=lambda x: (x[0], x[1], x[2][0], x[2][1], x[2][2]))
    return candidates[0][3]


def postprocess_sequence(tokens: List[str]) -> List[str]:
    """
    Optionales Postprocessing, falls du später mehr als 4 Tokens zulässt.
    Für 4-Token-Signaturen macht das i.d.R. nichts kaputt.
    """
    if not tokens:
        return tokens

    # (1) collapse duplicates
    collapsed: List[str] = []
    for t in tokens:
        if not collapsed or collapsed[-1] != t:
            collapsed.append(t)

    # (2) merge runs of combo tokens
    merged: List[str] = []
    i = 0
    while i < len(collapsed):
        t = collapsed[i]
        if is_combo_token(t):
            run_atoms = atomic_codes(t)
            j = i + 1
            while j < len(collapsed) and is_combo_token(collapsed[j]):
                run_atoms.extend(atomic_codes(collapsed[j]))
                j += 1
            merged.append(normalize_combo_key(run_atoms))
            i = j
        else:
            merged.append(t)
            i += 1

    # final collapse
    final: List[str] = []
    for t in merged:
        if not final or final[-1] != t:
            final.append(t)

    # purge: wenn keinerlei Acting-Code enthalten -> leere Sequenz
    has_act = any(
        (t in ACTING_CODES) or (is_combo_token(t) and any(a in ACTING_CODES for a in atomic_codes(t)))
        for t in final
    )
    return final if has_act else []


# -------------------------------------------------------------------
# 4) Pfade bauen: 4-Teil-Signatur
# -------------------------------------------------------------------
def build_sequences_from_paths_csv(
    df: pd.DataFrame,
    start_lookahead_n: int = 12,  # jetzt: wird in 4 gleiche "Chunks" geteilt
) -> Tuple[List[List[str]], pd.DataFrame]:
    d = df.copy()

    d["code"] = d["Sequence_Code"].map(normalize_code)
    d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
    d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)

    # ignore non-allowed
    d = d[d["code"].isin(ALLOWED_CODES)].copy()
    sequences_labels: List[List[str]] = []
    per_path_rows: List[Dict[str, Any]] = []

    group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]
    for key, g in d.groupby(group_cols, sort=True):
        if isinstance(key, tuple):
            filename, pid = key
        else:
            filename, pid = key, ""

        # strikt zeitlich sortieren + code tie-break über Priorität
        g_sorted = g.sort_values(
            by=["start_s", "end_s", "code"],
            key=lambda col: (
                col.map(lambda c: CODE_TO_PRIO.get(c, (999, 999)))
                if col.name == "code"
                else col
            ),
        ).copy()
        print(f"es gibt {len(g_sorted)} atoms:", g_sorted)
        #if len(g_sorted) < 4:
        #    continue
        n = max(4, int(start_lookahead_n))  # mind. 4, sonst keine 4 Teile möglich
        first_n = g_sorted.head(n).copy()

        # in 4 Teile splitten: z.B. bei 12 -> 3/3/3/3
        # bei nicht teilbar: verteilt den Rest auf die vorderen Teile (fair split)
        L = len(first_n)
        if L == 0:
            innen_tok = PLACEHOLDER_OTHER
            mitte_tok = PLACEHOLDER_OTHER
            aussen_tok = PLACEHOLDER_OTHER
            aussenring_tok = PLACEHOLDER_OTHER
        else:
            parts = []
            base = L // 4
            rem = L % 4
            sizes = [base + (1 if i < rem else 0) for i in range(4)]  # fair split
            idx0 = 0
            for sz in sizes:
                parts.append(first_n.iloc[idx0:idx0 + sz].copy())
                idx0 += sz

            innen_df, mitte_df, aussen_df, aussenring_df = parts

            # helper: search in own part first, then expand to adjacent parts
            def pick_with_adjacent(parts_list, idx, allowed_codes):
                # order of search windows (by distance): [idx], then idx±1, then idx±2, ...
                n_parts = len(parts_list)
                for dist in range(n_parts):
                    # check left then right for same dist (except dist=0)
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
                        if tok != PLACEHOLDER_OTHER:
                            return tok
                return PLACEHOLDER_OTHER

            parts_list = [innen_df, mitte_df, aussen_df, aussenring_df]

            innen_tok = pick_with_adjacent(parts_list, 0, GROUP_NAME_TO_CODES["innen"])
            mitte_tok = pick_with_adjacent(parts_list, 1, GROUP_NAME_TO_CODES["mitte"])
            aussen_tok = pick_with_adjacent(parts_list, 2, GROUP_NAME_TO_CODES["aussen"])
            aussenring_tok = pick_with_adjacent(parts_list, 3, GROUP_NAME_TO_CODES["aussenring"])


        seq_tokens = [innen_tok, mitte_tok, aussen_tok, aussenring_tok]
        # seq_tokens = postprocess_sequence(seq_tokens)

        seq_labels = [label_for_token(t) for t in seq_tokens]

        sequences_labels.append(seq_labels)
        per_path_rows.append({
            "Filename": filename,
            "id": pid,
            "start_group": label_for_token(innen_tok),   # Gruppierung nach innen
            "sequence_tokens": " -> ".join(seq_tokens),
            "sequence_labels": " -> ".join(seq_labels),
            "innen_token": innen_tok,
            "mitte_token": mitte_tok,
            "aussen_token": aussen_tok,
            "aussenring_token": aussenring_tok,
            "n_considered": len(first_n),
            "chunk_sizes": "|".join(map(str, [len(x) for x in (innen_df, mitte_df, aussen_df, aussenring_df)]))
                         if len(first_n) > 0 else "0|0|0|0",
        })

    per_path_table = pd.DataFrame(per_path_rows)
    return sequences_labels, per_path_table


# -------------------------------------------------------------------
# 5) Sunburst helpers
# -------------------------------------------------------------------
def sequences_to_sunburst_wide(seqs: List[List[str]], max_depth: int = 12) -> pd.DataFrame:
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


def wide_to_sunburst_nodes(df_wide: pd.DataFrame, max_depth: int) -> pd.DataFrame:
    nodes: Dict[Tuple[str, str], int] = {}

    for _, r in df_wide.iterrows():
        value = int(r["value"])
        steps = [r.get(f"step{i+1}") for i in range(max_depth)]
        steps = [s for s in steps if s is not None and str(s).strip() != ""]
        parent = "ROOT"
        for s in steps:
            nodes[(parent, s)] = nodes.get((parent, s), 0) + value
            parent = f"{parent}||{s}"

    parent_sums: Dict[str, int] = {}
    for (parent, _label), v in nodes.items():
        parent_sums[parent] = parent_sums.get(parent, 0) + v

    long_rows = []
    for (parent, label), v in nodes.items():
        denom = parent_sums.get(parent, 0)
        p = v / denom if denom > 0 else math.nan
        long_rows.append({"parent": parent, "label": label, "value": v, "p_child_given_parent": p})

    out = pd.DataFrame(long_rows)
    out["id"] = out.apply(lambda rr: f"{rr['parent']}||{rr['label']}", axis=1)
    out["parent_id"] = out["parent"].map(lambda p: "" if p == "ROOT" else p)
    return out


# -------------------------------------------------------------------
# 6) Main
# -------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default="extracted_sequences.csv", help="Input CSV")
    ap.add_argument("--out_prefix", default="out_paths", help="Prefix für Output-Dateien")
    ap.add_argument("--max_depth", type=int, default=50, help="Max Tiefe für Sunburst")
    ap.add_argument("--start_lookahead_n", type=int, default=5, help="Lookahead N Events pro Pfad")
    ap.add_argument("--no_sunburst", action="store_true", help="Kein Sunburst erzeugen")
    args = ap.parse_args()

    df = pd.read_csv(args.csv)

    seqs_labels, per_path = build_sequences_from_paths_csv(df, start_lookahead_n=args.start_lookahead_n)

    per_path.to_csv(f"{args.out_prefix}_per_path_sequences.csv", index=False)

    counts = (
        per_path.groupby(["start_group", "sequence_labels"])
        .size()
        .reset_index(name="count")
        .sort_values(["start_group", "count"], ascending=[True, False])
    )
    counts.to_csv(f"{args.out_prefix}_path_counts.csv", index=False)

    print(
        f"[OK] Wrote:\n"
        f" - {args.out_prefix}_per_path_sequences.csv\n"
        f" - {args.out_prefix}_path_counts.csv"
    )

    if args.no_sunburst:
        return
    if px is None:
        print("[WARN] plotly not installed; skipping sunburst. Install: pip install plotly")
        return

    wide = sequences_to_sunburst_wide(seqs_labels, max_depth=args.max_depth)
    nodes = wide_to_sunburst_nodes(wide, max_depth=args.max_depth)

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
