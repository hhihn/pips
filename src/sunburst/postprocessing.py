from typing import List

from src.sunburst.util import COMBO_RULES


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

    # (2) merge co-occurring
    merged: List[str] = []
    changed = False
    i = 0
    while i <= len(collapsed) - 1:
        matched_combo = None
        if i == len(collapsed) - 1:
            merged.append(collapsed[i])
            break
        for combo in COMBO_RULES:
            if (collapsed[i], collapsed[i + 1]) == combo[0] or (
                collapsed[i + 1],
                collapsed[i],
            ) == combo[0]:
                matched_combo = combo[1]
                changed = True
                break
        if matched_combo:
            merged.append(matched_combo)
            i = i + 2
        else:
            merged.append(collapsed[i])
            i = i + 1
    if changed:
        print(f"changed {collapsed} to {merged}")
    return merged
