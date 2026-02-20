import json
import logging
from pathlib import Path
import pandas as pd
from typing import List, Tuple, Dict

logger = logging.getLogger(__name__)


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

        # Load static config from JSON file.
        self._load_base_config()

        # Build CODE_TO_PRIO from configured prio groups
        self.CODE_TO_PRIO = {}
        for gi, (_gname, codes) in enumerate(self.PRIO_GROUPS):
            for ci, c in enumerate(codes):
                self.CODE_TO_PRIO[c] = (gi, ci)

        self.GROUP_NAME_TO_CODES: Dict[str, set] = {
            name: set(codes) for name, codes in self.PRIO_GROUPS
        }

        # Load external labels (optional)
        self._load_external_labels()

        # Add labels for predefined rules
        for codes_tuple, combo in self.PREDEFINED_COMBO_RULES:
            labels = [self.LABEL_MAP.get(c, c) for c in codes_tuple]
            self.LABEL_MAP[" & ".join(codes_tuple)] = " + ".join(labels)

        # Data-driven rules: Now supports arbitrary-length tuples
        self.DATA_DRIVEN_COMBO_RULES: List[Tuple[Tuple[str, ...], str, int]] = []
        self.load_data_driven_rules(
            cooccurrence_csv="csv_analysen/cooccurrence/out_paths_cooccurrence_same_window.csv",
            refresh=False,
        )
        # Combo rules
        self.COMBO_RULES = self._get_all_combo_rules()
        self.ALLOWED_CODES = self._compute_allowed_codes()

        logger.info("CodeUtil initialization done")

    def _load_base_config(self):
        """Load static code definitions from JSON config."""
        base_dir = Path(__file__).resolve().parent
        config_path = base_dir / "code_util_config.json"
        try:
            with config_path.open("r", encoding="utf-8") as f:
                config = json.load(f)
        except FileNotFoundError as exc:
            raise FileNotFoundError(
                f"Missing CodeUtil config file: {config_path}"
            ) from exc

        required = [
            "placeholder_other",
            "prio_groups",
            "label_map",
            "predefined_combo_rules",
            "acting_codes",
        ]
        missing = [k for k in required if k not in config]
        if missing:
            raise ValueError(
                f"Invalid code_util_config.json: missing keys {missing}"
            )

        self.PLACEHOLDER_OTHER = str(config["placeholder_other"])

        raw_prio_groups = config["prio_groups"]
        if not isinstance(raw_prio_groups, list):
            raise ValueError("Invalid code_util_config.json: 'prio_groups' must be a list.")
        self.PRIO_GROUPS = []
        for item in raw_prio_groups:
            if not isinstance(item, dict):
                raise ValueError(
                    "Invalid code_util_config.json: each prio_groups entry must be an object."
                )
            name = str(item.get("name", "")).strip()
            codes = item.get("codes")
            if not name or not isinstance(codes, list):
                raise ValueError(
                    "Invalid code_util_config.json: each prio group needs name and codes list."
                )
            self.PRIO_GROUPS.append((name, [str(c).strip() for c in codes if str(c).strip()]))

        raw_label_map = config["label_map"]
        if not isinstance(raw_label_map, dict):
            raise ValueError("Invalid code_util_config.json: 'label_map' must be an object.")
        self.LABEL_MAP = {str(k): str(v) for k, v in raw_label_map.items()}

        raw_combo_rules = config["predefined_combo_rules"]
        if not isinstance(raw_combo_rules, list):
            raise ValueError(
                "Invalid code_util_config.json: 'predefined_combo_rules' must be a list."
            )
        self.PREDEFINED_COMBO_RULES = []
        for rule in raw_combo_rules:
            if not isinstance(rule, dict):
                raise ValueError(
                    "Invalid code_util_config.json: each predefined combo rule must be an object."
                )
            codes = rule.get("codes")
            label = rule.get("label")
            if not isinstance(codes, list) or not label:
                raise ValueError(
                    "Invalid code_util_config.json: each predefined combo rule needs codes list and label."
                )
            codes_tuple = tuple(str(c).strip() for c in codes if str(c).strip())
            if not codes_tuple:
                raise ValueError(
                    "Invalid code_util_config.json: predefined combo rule with empty codes."
                )
            self.PREDEFINED_COMBO_RULES.append((codes_tuple, str(label)))

        raw_acting_codes = config["acting_codes"]
        if not isinstance(raw_acting_codes, list):
            raise ValueError(
                "Invalid code_util_config.json: 'acting_codes' must be a list."
            )
        self.ACTING_CODES = {str(c).strip() for c in raw_acting_codes if str(c).strip()}

    def _load_external_labels(self):
        """Load labels from JSON file if available."""
        base_dir = Path(__file__).resolve().parent
        labels_path = base_dir.parent / "output.json"
        try:
            with labels_path.open("r", encoding="utf-8") as f:
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
        logger.info("Loading pre-defined combo rules")
        logger.debug("Combo rules:\n%s", json.dumps(all_rules, indent=4))
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
        base_dir = Path(__file__).resolve().parent
        rules_cache_path = base_dir / "DATA_DRIVEN_COMBO_RULES.json"

        if not refresh:
            try:
                with rules_cache_path.open("r", encoding="utf-8") as f:
                    self.DATA_DRIVEN_COMBO_RULES = json.load(f)
                logger.info("Loaded data-driven combo rules from cache")
                logger.debug(
                    "Data-driven rules:\n%s",
                    json.dumps(self.DATA_DRIVEN_COMBO_RULES, indent=4),
                )
                return
            except FileNotFoundError:
                logger.warning(
                    "Could not load pre-computed combo rules file. Proceeding with refresh."
                )

        cooccurrence_path = Path(cooccurrence_csv)
        if not cooccurrence_path.is_absolute():
            cooccurrence_path = base_dir / cooccurrence_path

        try:
            df = pd.read_csv(cooccurrence_path)
        except FileNotFoundError:
            logger.warning("Could not load co-occurrence file: %s", cooccurrence_path)
            return

        # Check what columns exist in the CSV[1][4]
        if "bundle_key" in df.columns:
            # NEW FORMAT: Extended co-occurrence bundles (arbitrary-length)
            self._load_bundle_rules(df, min_window_count)
        elif "Same_Window_Count" in df.columns:
            # OLD FORMAT: Pairwise co-occurrences (backward compatibility)
            self._load_pairwise_rules(df, min_window_count)
        else:
            logger.warning("Unknown co-occurrence CSV format.")
            logger.warning("Available columns: %s", df.columns.tolist())
            return

        # Re-compute combo rules and allowed codes
        self._instance.COMBO_RULES = self._get_all_combo_rules()
        self.ALLOWED_CODES = self._compute_allowed_codes()

        with rules_cache_path.open("w", encoding="utf-8") as f:
            json.dump(
                [
                    (list(codes), label, count)
                    for codes, label, count in self.DATA_DRIVEN_COMBO_RULES
                ],
                f,
                ensure_ascii=False,
                indent=4,
            )
        logger.info("Loaded %d data-driven rules", len(self.DATA_DRIVEN_COMBO_RULES))

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
