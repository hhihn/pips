from typing import List
from src.sunburst.code_util import CodeUtil

code_util = CodeUtil()


def postprocess_sequence(tokens: List[str]) -> List[str]:
    """
    Merge co-occurring tokens according to combo rules.
    Tracks whether each merge was from a predefined or data-driven rule.
    """
    if not tokens:
        return tokens

    # (1) Collapse duplicates
    collapsed: List[str] = []
    for t in tokens:
        if not collapsed or collapsed[-1] != t:
            collapsed.append(t)

    # (2) Merge co-occurring tokens
    merged: List[str] = []
    merge_log: List[str] = []  # Track merges
    i = 0

    while i <= len(collapsed) - 1:
        matched_combo = None
        matched_source = None

        if i == len(collapsed) - 1:
            merged.append(collapsed[i])
            break

        for combo_rule in code_util.COMBO_RULES:
            pair, _label = combo_rule, combo_rule[1]
            if (collapsed[i], collapsed[i + 1]) == pair or (
                collapsed[i + 1],
                collapsed[i],
            ) == pair:
                matched_combo = pair
                matched_source = (
                    "predefined" if code_util.is_predefined_rule(pair) else "data-driven"
                )
                break

        if matched_combo:
            # Create combo token
            combo_token = f"{matched_combo} & {matched_combo[1]}"
            merged.append(combo_token)

            # Log the merge
            merge_log.append(
                f"[{matched_source.upper()}] {collapsed[i]} + {collapsed[i + 1]} "
                f"→ {combo_token}"
            )
            i += 2
        else:
            merged.append(collapsed[i])
            i += 1

    if merge_log:
        print(f"\n[MERGES] ({len(merge_log)} total):")
        for log in merge_log:
            print(f"  {log}")

    return merged