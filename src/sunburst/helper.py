import math
import textwrap
from typing import List, Any, Tuple, Dict, Literal

import pandas as pd

from src.sunburst.bundling import make_bundle_strategy
from src.sunburst.context import AnalysisContext, get_default_context


def _ctx(context: AnalysisContext | None) -> AnalysisContext:
    return context if context is not None else get_default_context()


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


def normalize_combo_key(
    codes: List[str], context: AnalysisContext | None = None
) -> str:
    ctx = _ctx(context)

    def _key(c: str):
        return ctx.code_to_prio.get(c, (999, 999, c))

    codes_sorted = sorted(set(codes), key=_key)
    return " & ".join(codes_sorted)


def label_for_token(token: str, context: AnalysisContext | None = None) -> str:
    ctx = _ctx(context)
    if token in ctx.label_map:
        return ctx.label_map[token]
    if not is_combo_token(token):
        return ctx.label_map.get(token, token)
    atoms = atomic_codes(token)
    atom_labels = [ctx.label_map.get(a, a) for a in atoms]
    return " + ".join(atom_labels)


def apply_bundle_combos(
    codes: List[str], context: AnalysisContext | None = None
) -> List[str]:
    """
    Wendet Kombi-Regeln innerhalb eines Bundles an.
    Input: codes (atomare Codes) innerhalb exakt gleicher (start,end)
    Output: Liste aus Kombi-Tokens und ggf. Rest-atomaren Codes
    """
    ctx = _ctx(context)
    s = set(codes)
    out: List[str] = []

    for (a, b), combo in ctx.combo_rules:
        if a in s and b in s:
            out.append(combo)
            s.remove(a)
            s.remove(b)

    out.extend(sorted(s, key=lambda c: ctx.code_to_prio.get(c, (999, 999))))
    return out


def build_time_bundles(
    events: pd.DataFrame,
    combo_time_match_mode: Literal["keine", "exact", "overlap"] = "exact",
) -> List[pd.DataFrame]:
    """
    Build temporal bundles from events.
    - keine: no bundling (each event is its own bundle)
    - exact: same (start_s, end_s)
    - overlap: overlapping time windows are merged into one bundle
    """
    return make_bundle_strategy(combo_time_match_mode).build(events)


def pick_group_token_from_first_n(
    first_n_events: pd.DataFrame,
    group_codes: set,
    combo_time_match_mode: Literal["keine", "exact", "overlap"] = "exact",
    context: AnalysisContext | None = None,
) -> List[str]:
    """
    Wählt für eine Gruppe (innen/mitte/außen/außenring) das früheste Token
    innerhalb first_n_events.
    - berücksichtigt COMBO_RULES pro Bundle
    - wenn nichts gefunden: PLACEHOLDER_OTHER
    """
    ctx = _ctx(context)
    if first_n_events.empty:
        return [ctx.placeholder_other]

    # bundles in first_n according to requested matching mode
    fe = first_n_events.copy()
    bundle_frames = build_time_bundles(fe, combo_time_match_mode=combo_time_match_mode)

    candidates: List[Tuple[float, float, Tuple[int, int, str], str]] = []
    # (start_s, end_s, prio, token)

    for bg in bundle_frames:
        bs = float(bg["start_s"].min())
        be = float(bg["end_s"].max())
        tokens = sorted(
            set(bg["code"].tolist()),
            key=lambda c: ctx.code_to_prio.get(c, (999, 999)),
        )
        #  tokens = atom_codes # apply_bundle_combos(atom_codes)

        for tok in tokens:
            atoms = atomic_codes(tok) if is_combo_token(tok) else [tok]
            if any(a in group_codes for a in atoms):
                # Priority for tie-break: min priority of involved atomic codes
                pr = min([ctx.code_to_prio.get(a, (999, 999)) for a in atoms])
                candidates.append((float(bs), float(be), (pr[0], pr[1], tok), tok))

    if not candidates:
        return [ctx.placeholder_other]

    candidates.sort(key=lambda x: (x[0], x[1], x[2][0], x[2][1], x[2][2]))
    return [candidates[0][3]]


def customwrap(s, width=20):
    """Wrap text by adding <br> tags for Plotly"""
    try:
        return "<br>".join(textwrap.wrap(s, width=width))
    except Exception:
        return s


def sequences_to_sunburst_wide(
    seqs: List[List[str]],
    max_depth: int = 12,
    min_support: int = 1,
    rare_label: str | None = "Andere (selten)",
) -> pd.DataFrame:
    counts: Dict[Tuple[str, ...], int] = {}
    for seq in seqs:
        if not seq:
            continue
        truncated = tuple(seq[:max_depth])
        counts[truncated] = counts.get(truncated, 0) + 1

    if min_support > 1:
        filtered: Dict[Tuple[str, ...], int] = {}
        for path, c in counts.items():
            if c >= min_support:
                filtered[path] = filtered.get(path, 0) + c
                continue

            if rare_label is None:
                continue

            if len(path) == 0:
                bucket = (rare_label,)
            elif len(path) == 1:
                bucket = (path[0], rare_label)
            else:
                bucket = (path[0], rare_label)
            filtered[bucket] = filtered.get(bucket, 0) + c

        counts = filtered

    rows = []
    for path, c in counts.items():
        row = {
            f"step{i + 1}": (path[i] if i < len(path) else None)
            for i in range(max_depth)
        }
        row["value"] = c
        rows.append(row)
    return pd.DataFrame(rows)


def wide_to_sunburst_nodes(df_wide: pd.DataFrame, max_depth: int) -> pd.DataFrame:
    nodes: Dict[Tuple[str, str], int] = {}

    for _, r in df_wide.iterrows():
        value = int(r["value"])
        steps = [r.get(f"step{i + 1}") for i in range(max_depth)]
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
        long_rows.append(
            {"parent": parent, "label": label, "value": v, "p_child_given_parent": p}
        )

    out = pd.DataFrame(long_rows)
    out["id"] = out.apply(lambda rr: f"{rr['parent']}||{rr['label']}", axis=1)
    out["parent_id"] = out["parent"].map(lambda p: "" if p == "ROOT" else p)
    return out
