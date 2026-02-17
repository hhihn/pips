import json
import pandas as pd
from typing import List, Tuple, Dict

# -------------------------------------------------------------------
# 1) Labeling
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
}
labels = json.load(open("../output.json", "r"))
for key, label in LABEL_MAP.items():
    LABEL_MAP[key] = labels.get(key, label)

PLACEHOLDER_OTHER = "Andere"

# -------------------------------------------------------------------
# 2) Priority Groups
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
GROUP_NAME_TO_CODES: Dict[str, set] = {name: set(codes) for name, codes in PRIO_GROUPS}

# ===================================================================
# 3) PREDEFINED COMBO RULES (Expert-defined)
# ===================================================================
PREDEFINED_COMBO_RULES: List[Tuple[Tuple[str, str], str]] = [
    (("2.1.3.1", "6.4.3"), "2.1.3.1 & 6.4.3"),
    (("2.1.3.1", "6.4.4"), "2.1.3.1 & 6.4.4"),
    (("2.1.3.1", "6.4.5"), "2.1.3.1 & 6.4.5"),
    (("2.1.3.1", "2.2.3.14"), "2.1.3.1 & 2.2.3.14"),
    (("2.1.3.1", "2.2.3.4"), "2.1.3.1 & 2.2.3.4"),
    (("2.2.3.4", "2.2.3.14"), "2.2.3.4 & 2.2.3.14"),
]

# Add labels for predefined rules
for (a, b), combo in PREDEFINED_COMBO_RULES:
    label_a = LABEL_MAP.get(a, a)
    label_b = LABEL_MAP.get(b, b)
    LABEL_MAP[combo] = f"{label_a} + {label_b}"

# ===================================================================
# 4) DATA-DRIVEN COMBO RULES (Generated from Co-occurrence Analysis)
# ===================================================================
DATA_DRIVEN_COMBO_RULES: List[Tuple[Tuple[str, str], str, int]] = []  # (pair, label, count)


def load_data_driven_rules(cooccurrence_csv: str, min_window_count: int = 5):
    """
    Load co-occurrence analysis results and create data-driven combo rules.
    Only pairs with Same_Window_Count >= min_window_count are included.

    Args:
        cooccurrence_csv: Path to *_cooccurrence_summary.csv
        min_window_count: Minimum co-occurrence count to create a rule
    """
    global DATA_DRIVEN_COMBO_RULES

    try:
        df = pd.read_csv(cooccurrence_csv)
    except FileNotFoundError:
        print(f"[WARN] Could not load co-occurrence file: {cooccurrence_csv}")
        return

    # Filter for significant co-occurrences
    significant = df[df["Same_Window_Count"] >= min_window_count].copy()

    predefined_pairs = {
        frozenset(pair) for pair in PREDEFINED_COMBO_RULES
    }

    for _, row in significant.iterrows():
        code1, code2 = row["Code1"], row["Code2"]
        pair = frozenset([code1, code2])

        # Skip if already in predefined rules
        if pair in predefined_pairs:
            continue

        # Create normalized pair (sorted by priority)
        pair_sorted = tuple(sorted([code1, code2], key=lambda c: CODE_TO_PRIO.get(c, (999, 999))))
        label = f"{row['Label1']} + {row['Label2']}"
        count = int(row["Same_Window_Count"])

        DATA_DRIVEN_COMBO_RULES.append((pair_sorted, label, count))

        # Add to LABEL_MAP
        combo_key = f"{pair_sorted} & {pair_sorted[1]}"
        LABEL_MAP[combo_key] = label

    print(f"[OK] Loaded {len(DATA_DRIVEN_COMBO_RULES)} data-driven combo rules from {cooccurrence_csv}")
    print(f"     (filtered for Same_Window_Count >= {min_window_count})")


def get_all_combo_rules() -> List[Tuple[Tuple[str, str], str]]:
    """Combine predefined and data-driven rules, excluding duplicates."""
    all_rules = PREDEFINED_COMBO_RULES.copy()
    for (pair, label, count) in DATA_DRIVEN_COMBO_RULES:
        all_rules.append((pair, f"{label} [data-driven: n={count}]"))
    return all_rules


def is_predefined_rule(pair: Tuple[str, str]) -> bool:
    """Check if a rule was predefined by an expert."""
    for (predefined_pair, _) in PREDEFINED_COMBO_RULES:
        if set(pair) == set(predefined_pair):
            return True
    return False


COMBO_RULES = get_all_combo_rules()
COMBO_RULES_KEYS = [l for l in COMBO_RULES]
ALLOWED_CODES = set(CODE_TO_PRIO.keys()).union(set(COMBO_RULES_KEYS))
COMBO_RULES_KEYS = [l[1] for l in COMBO_RULES]
ALLOWED_CODES = ALLOWED_CODES.union(set(COMBO_RULES_KEYS))

ACTING_CODES = {
    "2.1.3.1",
    "6.5.3",
    "2.1.3.1 & 6.4.3",
    "2.1.3.1 & 6.4.4",
    "2.1.3.1 & 6.4.5",
    "2.1.3.1 & 2.2.3.4",
    "2.2.3.4 & 2.2.3.14",
    "2.1.3.1 & 2.2.3.14",
}