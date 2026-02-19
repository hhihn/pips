from typing import List
import logging
from src.sunburst.code_util import CodeUtil

code_util = CodeUtil()
logger = logging.getLogger(__name__)


def postprocess_sequence(tokens: List[str]) -> List[str]:
    """
    Postprocessing to merge co-occurring codes at arbitrary lengths.
    Handles combo rules with 2, 3, 4, or more codes.
    """
    if not tokens:
        return tokens

    # (1) Collapse duplicates
    collapsed: List[str] = []
    for t in tokens:
        if not collapsed or collapsed[-1] != t:
            collapsed.append(t)

    # (2) Merge co-occurring sequences of arbitrary length
    merged: List[str] = []
    changed = False
    i = 0

    while i < len(collapsed):
        matched_combo = None
        matched_length = 0

        # Try to match sequences of decreasing length (greedy from longest)
        # This prioritizes longer matches over shorter ones[1]
        max_lookahead = len(collapsed) - i

        for length in range(max_lookahead, 0, -1):
            # Get the next `length` tokens
            candidate_sequence = tuple(collapsed[i : i + length])

            # Check if this sequence matches any combo rule
            for combo_codes, combo_label in code_util.COMBO_RULES:
                # Check both original and reverse order (order-independent matching)
                if _matches_combo(candidate_sequence, combo_codes):
                    matched_combo = combo_label
                    matched_length = length
                    changed = True
                    if len(combo_codes) > 2:
                        logger.info(
                            "Matched combo code with length > 2: %s", combo_codes
                        )
                    break

            # Stop at first match (longest match found)
            if matched_combo:
                break

        if matched_combo:
            # Add the merged combo
            merged.append(matched_combo)
            # Skip the matched tokens
            i += matched_length
        else:
            # No match, keep the single token
            merged.append(collapsed[i])
            i += 1

    if changed:
        logger.debug("Postprocessing changed %s to %s", collapsed, merged)

    return merged


def _matches_combo(sequence: tuple, combo_codes: tuple) -> bool:
    """
    Check if a sequence of tokens matches a combo rule.
    Handles order-independent matching for arbitrary-length tuples[1][2].

    Args:
        sequence: Tuple of consecutive tokens from collapsed list
        combo_codes: Tuple of codes from a combo rule

    Returns:
        True if sequence matches the combo (in any order or exact order)
    """
    # Exact order match
    if sequence == combo_codes:
        return True

    # Reverse order match (for sequences that can appear in either order)
    if sequence == tuple(reversed(combo_codes)):
        return True

    # Set-based match (order doesn't matter)
    # Use frozenset for unordered comparison
    if frozenset(sequence) == frozenset(combo_codes) and len(sequence) == len(
        combo_codes
    ):
        return True

    return False
