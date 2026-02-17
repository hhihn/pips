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

        # Predefined rules: Now supports arbitrary-length tuples
        self.PREDEFINED_COMBO_RULES: List[Tuple[Tuple[str, ...], str]] = [
            (("2.1.3.1", "6.4.3"), "2.1.3.1 & 6.4.3"),
            (("2.1.3.1", "6.4.4"), "2.1.3.1 & 6.4.4"),
            (("2.1.3.1", "6.4.5"), "2.1.3.1 & 6.4.5"),
            (("2.1.3.1", "2.2.3.14"), "2.1.3.1 & 2.2.3.14"),
            (("2.1.3.1", "2.2.3.4"), "2.1.3.1 & 2.2.3.4"),
            (("2.2.3.4", "2.2.3.14"), "2.2.3.4 & 2.2.3.14"),
        ]

        # Add labels for predefined rules
        for codes_tuple, combo in self.PREDEFINED_COMBO_RULES:
            labels = [self.LABEL_MAP.get(c, c) for c in codes_tuple]
            self.LABEL_MAP[" & ".join(codes_tuple)] = " + ".join(labels)

        # Data-driven rules: Now supports arbitrary-length tuples
        self.DATA_DRIVEN_COMBO_RULES: List[Tuple[Tuple[str, ...], str, int]] = []
        self.load_data_driven_rules(cooccurrence_csv="out_paths_cooccurrence_same_window.csv",
                                    refresh=False)
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
        print("[INFO] Initializing done")

    def _load_external_labels(self):
        """Load labels from JSON file if available."""
        try:
            with open("../output.json", "r") as f:
                labels = json.load(f)
            for key, label in self.LABEL_MAP.items():
                self.LABEL_MAP[key] = labels.get(key, label)
        except FileNotFoundError:
            pass

    def _get_all_combo_rules(self) -> List[Tuple[Tuple[str, ...], str]]:
        """Combine predefined and data-driven rules (supports arbitrary-length tuples)."""
        all_rules = self.PREDEFINED_COMBO_RULES.copy()
        for codes_tuple, label, count in self.DATA_DRIVEN_COMBO_RULES:
            all_rules.append((codes_tuple, label))
        print("[INFO] Loading pre-defined combo rules")
        print(json.dumps(all_rules, indent=4))
        return all_rules

    def _compute_allowed_codes(self) -> set:
        """Compute set of allowed codes from arbitrary-length tuples."""
        allowed = set(self.CODE_TO_PRIO.keys())
        # Add all codes from combo tuples of any length
        for codes_tuple, _ in self.COMBO_RULES:
            allowed.update(codes_tuple)
        return allowed

    def load_data_driven_rules(
        self, cooccurrence_csv: str, min_window_count: int = 5, refresh: bool = False
    ):
        """Load data-driven combo rules from co-occurrence analysis (bundles or pairs)."""
        if not refresh:
            try:
                self.DATA_DRIVEN_COMBO_RULES = json.load(
                    open("DATA_DRIVEN_COMBO_RULES.json", "r")
                )
                print("[OK] Loaded data-driven combo rules from co-occurrence analysis")
                print(json.dumps(self.DATA_DRIVEN_COMBO_RULES, indent=4))
                return
            except FileNotFoundError:
                print(
                    "[WARN] Could not load pre-computed combo rules file. Proceeding with refresh."
                )

        try:
            df = pd.read_csv(cooccurrence_csv)
        except FileNotFoundError:
            print(f"[WARN] Could not load co-occurrence file: {cooccurrence_csv}")
            return

        # Check what columns exist in the CSV[1][4]
        if "bundle_key" in df.columns:
            # NEW FORMAT: Extended co-occurrence bundles (arbitrary-length)
            self._load_bundle_rules(df, min_window_count)
        elif "Same_Window_Count" in df.columns:
            # OLD FORMAT: Pairwise co-occurrences (backward compatibility)
            self._load_pairwise_rules(df, min_window_count)
        else:
            print("[WARN] Unknown co-occurrence CSV format.")
            print(f"      Available columns: {df.columns.tolist()}")
            return

        # Re-compute combo rules and allowed codes
        self._instance.COMBO_RULES = self._get_all_combo_rules()
        self.ALLOWED_CODES = self._compute_allowed_codes()

        json.dump(
            [
                (list(codes), label, count)
                for codes, label, count in self.DATA_DRIVEN_COMBO_RULES
            ],
            open("DATA_DRIVEN_COMBO_RULES.json", "w"),
            ensure_ascii=False,
            indent=4,
        )
        print(f"[OK] Loaded {len(self.DATA_DRIVEN_COMBO_RULES)} data-driven rules")

    def _load_bundle_rules(self, df: pd.DataFrame, min_window_count: int = 5):
        """Load data-driven rules from bundle format (arbitrary-length)."""
        self.DATA_DRIVEN_COMBO_RULES = []

        # Filter by minimum count
        significant = df[df["count"] >= min_window_count].copy()

        # Build predefined frozensets for comparison (works for any length)
        predefined_sets = {frozenset(codes) for codes, _ in self.PREDEFINED_COMBO_RULES}

        for _, row in significant.iterrows():
            # Parse bundle_key (e.g., "2.1.3.1 + 6.4.4 + 2.2.3.14")
            codes = row["bundle_key"].split(" + ")
            codes_set = frozenset(codes)

            # Skip if already in predefined rules
            if codes_set in predefined_sets:
                continue

            # Sort codes using priority
            codes_tuple = tuple(
                sorted(codes, key=lambda c: self.CODE_TO_PRIO.get(c, (999, 999)))
            )

            label = row["bundle_label"]
            count = int(row["count"])

            self.DATA_DRIVEN_COMBO_RULES.append((codes_tuple, label, count))

            # Add to LABEL_MAP with & separator for arbitrary-length tuples
            combo_key = " & ".join(codes_tuple)
            self.LABEL_MAP[combo_key] = label

    def _load_pairwise_rules(self, df: pd.DataFrame, min_window_count: int = 5):
        """Load data-driven rules from pairwise format (backward compatibility)."""
        self.DATA_DRIVEN_COMBO_RULES = []

        # Filter by minimum count
        significant = df[df["Same_Window_Count"] >= min_window_count].copy()

        # Build predefined frozensets for comparison
        predefined_sets = {frozenset(codes) for codes, _ in self.PREDEFINED_COMBO_RULES}

        for _, row in significant.iterrows():
            code1, code2 = row["Code1"], row["Code2"]
            pair_set = frozenset([code1, code2])

            # Skip if already in predefined rules
            if pair_set in predefined_sets:
                continue

            # Sort pair using priority
            pair_sorted = tuple(
                sorted(
                    [code1, code2], key=lambda c: self.CODE_TO_PRIO.get(c, (999, 999))
                )
            )

            label = f"{row['Label1']} + {row['Label2']}"
            count = int(row["Same_Window_Count"])

            self.DATA_DRIVEN_COMBO_RULES.append((pair_sorted, label, count))

            # Add to LABEL_MAP with & separator
            combo_key = " & ".join(pair_sorted)
            self.LABEL_MAP[combo_key] = label

    def is_predefined_rule(self, codes_tuple: Tuple[str, ...]) -> bool:
        """Check if a rule was predefined by an expert (works for any-length tuples)."""
        codes_set = frozenset(codes_tuple)
        for predefined_codes, _ in self.PREDEFINED_COMBO_RULES:
            if codes_set == frozenset(predefined_codes):
                return True
        return False
