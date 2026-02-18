import json
import math
from typing import Dict, List, Tuple

import pandas as pd


def _weighted_path_counts(
    seqs: List[List[str]], max_depth: int | None = None
) -> Dict[Tuple[str, ...], int]:
    counts: Dict[Tuple[str, ...], int] = {}
    for seq in seqs:
        if not seq:
            continue
        path = tuple(seq[:max_depth] if max_depth is not None else seq)
        if not path:
            continue
        counts[path] = counts.get(path, 0) + 1
    return counts


def _entropy_from_counts(values: List[int]) -> float:
    total = sum(values)
    if total <= 0:
        return 0.0
    h = 0.0
    for v in values:
        if v <= 0:
            continue
        p = v / total
        h -= p * math.log2(p)
    return h


def analyze_branching_codes(
    seqs: List[List[str]],
    max_depth: int | None = None,
    min_parent_count: int = 3,
    min_child_count: int = 1,
    min_distinct_children: int = 2,
) -> pd.DataFrame:
    """
    Find branching codes automatically based on weighted path transitions.
    A code is branching if it has >= min_distinct_children valid next codes.
    """
    path_counts = _weighted_path_counts(seqs, max_depth=max_depth)

    transitions: Dict[str, Dict[str, int]] = {}
    for path, weight in path_counts.items():
        for i in range(len(path) - 1):
            parent = path[i]
            child = path[i + 1]
            if parent not in transitions:
                transitions[parent] = {}
            transitions[parent][child] = transitions[parent].get(child, 0) + weight

    rows = []
    for code, child_map in transitions.items():
        outgoing_total = sum(child_map.values())
        if outgoing_total < min_parent_count:
            continue

        kept = {c: n for c, n in child_map.items() if n >= min_child_count}
        if len(kept) < min_distinct_children:
            continue

        sorted_children = sorted(kept.items(), key=lambda x: (-x[1], x[0]))
        top_child, top_count = sorted_children[0]
        entropy = _entropy_from_counts([n for _c, n in sorted_children])
        dominance = top_count / outgoing_total if outgoing_total > 0 else math.nan

        rows.append(
            {
                "code": code,
                "outgoing_total": outgoing_total,
                "distinct_children": len(sorted_children),
                "top_child": top_child,
                "top_child_count": top_count,
                "top_child_share": dominance,
                "branch_entropy": entropy,
                "branching_score": entropy * outgoing_total,
                "children_counts": json.dumps(
                    {c: n for c, n in sorted_children}, ensure_ascii=False
                ),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(
            columns=[
                "code",
                "outgoing_total",
                "distinct_children",
                "top_child",
                "top_child_count",
                "top_child_share",
                "branch_entropy",
                "branching_score",
                "children_counts",
            ]
        )
    return out.sort_values(
        by=["branching_score", "outgoing_total"], ascending=[False, False]
    ).reset_index(drop=True)


def analyze_branching_nodes(
    seqs: List[List[str]],
    max_depth: int | None = None,
    min_parent_count: int = 3,
    min_child_count: int = 1,
    min_distinct_children: int = 2,
) -> pd.DataFrame:
    """
    Contextual branching analysis for concrete nodes (path prefix + code).
    """
    path_counts = _weighted_path_counts(seqs, max_depth=max_depth)

    transitions: Dict[Tuple[int, Tuple[str, ...]], Dict[str, int]] = {}
    for path, weight in path_counts.items():
        for i in range(len(path) - 1):
            parent_prefix = tuple(path[: i + 1])  # includes current parent code
            key = (i + 1, parent_prefix)  # depth is 1-based
            child = path[i + 1]
            if key not in transitions:
                transitions[key] = {}
            transitions[key][child] = transitions[key].get(child, 0) + weight

    rows = []
    for (depth, parent_prefix), child_map in transitions.items():
        outgoing_total = sum(child_map.values())
        if outgoing_total < min_parent_count:
            continue

        kept = {c: n for c, n in child_map.items() if n >= min_child_count}
        if len(kept) < min_distinct_children:
            continue

        sorted_children = sorted(kept.items(), key=lambda x: (-x[1], x[0]))
        top_child, top_count = sorted_children[0]
        entropy = _entropy_from_counts([n for _c, n in sorted_children])
        dominance = top_count / outgoing_total if outgoing_total > 0 else math.nan

        rows.append(
            {
                "depth": depth,
                "node_code": parent_prefix[-1],
                "node_path": " -> ".join(parent_prefix),
                "outgoing_total": outgoing_total,
                "distinct_children": len(sorted_children),
                "top_child": top_child,
                "top_child_count": top_count,
                "top_child_share": dominance,
                "branch_entropy": entropy,
                "branching_score": entropy * outgoing_total,
                "children_counts": json.dumps(
                    {c: n for c, n in sorted_children}, ensure_ascii=False
                ),
            }
        )

    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(
            columns=[
                "depth",
                "node_code",
                "node_path",
                "outgoing_total",
                "distinct_children",
                "top_child",
                "top_child_count",
                "top_child_share",
                "branch_entropy",
                "branching_score",
                "children_counts",
            ]
        )
    return out.sort_values(
        by=["branching_score", "outgoing_total"], ascending=[False, False]
    ).reset_index(drop=True)
