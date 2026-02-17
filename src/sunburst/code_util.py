import json
import pandas as pd
from typing import List, Tuple, Dict


class CodeUtil:
    """Singleton class to manage sunburst analysis configuration."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # Only initialize once
        if self._initialized:
            return
        self._initialized = True

        # Initialize all variables
        self.PLACEHOLDER_OTHER = "Andere"

        self.PRIO_GROUPS: List[Tuple[str, List[str]]] = [
            ("innen", ["2.1.2.3", "6.5.1"]),
            ("mitte", ["6.4.2", "6.5.4"]),
            ("aussen", ["2.1.3.1", "6.5.3", "6.4.3", "6.4.4", "6.4.5"]),
            ("aussenring", ["2.1.3.5", "2.2.3.14", "2.2.3.4"]),
        ]

        # Build CODE_TO_PRIO
        self.CODE_TO_PRIO = {}
        for gi, (_gname, codes) in enumerate(self.PRIO_GROUPS):
            for ci, c in enumerate(codes):
                self.CODE_TO_PRIO[c] = (gi, ci)

        self.GROUP_NAME_TO_CODES: Dict[str, set] = {
            name: set(codes) for name, codes in self.PRIO_GROUPS
        }

        # Initialize labels
        self.LABEL_MAP: Dict[str, str] = {
            "2.1.2.3": "FK benennt Ziel",
            "6.5.1": "Kindliches Signal",
            "6.4.2": "Aufforderung Vorb.",
            "6.5.4": "Verbale Begleitung",
            "2.1.3.1": "FK führt Hdlg. aus",
            "6.5.3": "K führt Hdlg aus",
            "6.4.3": "FK von vorn",
            "6.4.4": "FK von der Seite",
            "6.4.5": "FK von hinten",
            "2.1.3.5": "Unterstützung nur verbal",
            "2.2.3.14": "KK Objektbezug",
            "2.2.3.4": "KK Halten",
        }

        # Load external labels (optional)
        self._load_external_labels()

        # Predefined rules
        self.PREDEFINED_COMBO_RULES: List[Tuple[Tuple[str, str], str]] = [
            (("2.1.3.1", "6.4.3"), "2.1.3.1 & 6.4.3"),
            (("2.1.3.1", "6.4.4"), "2.1.3.1 & 6.4.4"),
            (("2.1.3.1", "6.4.5"), "2.1.3.1 & 6.4.5"),
            (("2.1.3.1", "2.2.3.14"), "2.1.3.1 & 2.2.3.14"),
            (("2.1.3.1", "2.2.3.4"), "2.1.3.1 & 2.2.3.4"),
            (("2.2.3.4", "2.2.3.14"), "2.2.3.4 & 2.2.3.14"),
        ]

        # Add labels for predefined rules
        for (a, b), combo in self.PREDEFINED_COMBO_RULES:
            label_a = self.LABEL_MAP.get(a, a)
            label_b = self.LABEL_MAP.get(b, b)
            self.LABEL_MAP[combo] = f"{label_a} + {label_b}"

        # Data-driven rules
        self.DATA_DRIVEN_COMBO_RULES: List[Tuple[Tuple[str, str], str, int]] = []

        # Combo rules
        self.COMBO_RULES = self._get_all_combo_rules()
        self.ALLOWED_CODES = self._compute_allowed_codes()

        self.ACTING_CODES = {
            "2.1.3.1",
            "6.5.3",
            "2.1.3.1 & 6.4.3",
            "2.1.3.1 & 6.4.4",
            "2.1.3.1 & 6.4.5",
            "2.1.3.1 & 2.2.3.4",
            "2.2.3.4 & 2.2.3.14",
            "2.1.3.1 & 2.2.3.14",
        }

    def _load_external_labels(self):
        """Load labels from JSON file if available."""
        try:
            with open("../output.json", "r") as f:
                labels = json.load(f)
            for key, label in self.LABEL_MAP.items():
                self.LABEL_MAP[key] = labels.get(key, label)
        except FileNotFoundError:
            pass  # Silently skip if file not found

    def _get_all_combo_rules(self) -> List[Tuple[Tuple[str, str], str]]:
        """Combine predefined and data-driven rules."""
        all_rules = self.PREDEFINED_COMBO_RULES.copy()
        for pair, label, count in self.DATA_DRIVEN_COMBO_RULES:
            label_name = f"{label} [data-driven: n={count}]"
            all_rules.append((pair, label_name))
        return all_rules

    def _compute_allowed_codes(self) -> set:
        """Compute set of allowed codes."""
        combo_keys = [pair for pair, _ in self.COMBO_RULES]
        return set(self.CODE_TO_PRIO.keys()).union(set(combo_keys))

    def load_data_driven_rules(self, cooccurrence_csv: str, min_window_count: int = 5):
        """Load data-driven combo rules from co-occurrence analysis."""
        try:
            df = pd.read_csv(cooccurrence_csv)
        except FileNotFoundError:
            print(f"[WARN] Could not load co-occurrence file: {cooccurrence_csv}")
            return
        self.DATA_DRIVEN_COMBO_RULES = []
        significant = df[df["Same_Window_Count"] >= min_window_count].copy()
        predefined_pairs = {frozenset(pair) for pair in self.PREDEFINED_COMBO_RULES}

        for _, row in significant.iterrows():
            code1, code2 = row["Code1"], row["Code2"]
            pair = frozenset([code1, code2])

            if pair in predefined_pairs:
                continue

            pair_sorted = tuple(
                sorted([code1, code2], key=lambda c: self.CODE_TO_PRIO.get(c, (999, 999)))
            )
            label = f"{row['Label1']} + {row['Label2']}"
            count = int(row["Same_Window_Count"])

            self.DATA_DRIVEN_COMBO_RULES.append((pair_sorted, label, count))
            combo_key = f"{pair_sorted} & {pair_sorted[1]}"
            self.LABEL_MAP[combo_key] = label

        # Re-compute combo rules and allowed codes
        self.COMBO_RULES = self._get_all_combo_rules()
        self.ALLOWED_CODES = self._compute_allowed_codes()

        print(f"[OK] Loaded {len(self.DATA_DRIVEN_COMBO_RULES)} data-driven rules")

    def is_predefined_rule(self, pair: Tuple[str, str]) -> bool:
        """Check if a rule was predefined by an expert."""
        for predefined_pair, _ in self.PREDEFINED_COMBO_RULES:
            if set(pair) == set(predefined_pair):
                return True
        return False


