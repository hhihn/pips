from __future__ import annotations

import itertools
import json
import logging
from pathlib import Path
from typing import Dict, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------
# Cost scheme
# ---------------------------------------------------------------------


class CostScheme:
    def __init__(
        self,
        alphabet: Sequence[str],
        default_substitution_cost: float = 2.0,
        indel_cost: Optional[float] = None,
        custom_substitution_costs: Optional[Mapping[Tuple[str, str], float]] = None,
        custom_indel_costs: Optional[Mapping[str, float]] = None,
        compound_cost_strategy: str = "average_components",
    ):
        self.alphabet = sorted({str(state) for state in alphabet})
        self.alphabet_components = self._alphabet_components(self.alphabet)
        self.default_substitution_cost = self._validate_cost(
            default_substitution_cost,
            "default_substitution_cost",
        )
        self.default_indel_cost = self._validate_cost(
            (
                indel_cost
                if indel_cost is not None
                else self.default_substitution_cost / 2.0
            ),
            "indel_cost",
        )
        self.compound_cost_strategy = compound_cost_strategy
        if self.compound_cost_strategy != "average_components":
            raise ValueError(
                "compound_cost_strategy must be 'average_components'."
            )

        self.custom_substitution_costs = self._normalize_substitution_costs(
            custom_substitution_costs or {}
        )
        self.custom_indel_costs = self._normalize_indel_costs(
            custom_indel_costs or {}
        )
        self._warn_for_unknown_custom_states()

        self.substitution_matrix = self._build_substitution_matrix()
        self.indel_costs = {
            state: self.indel_cost(state)
            for state in self.alphabet
        }

    @classmethod
    def from_files(
        cls,
        alphabet: Sequence[str],
        default_substitution_cost: float = 2.0,
        indel_cost: Optional[float] = None,
        custom_substitution_costs: Optional[Mapping[Tuple[str, str], float]] = None,
        custom_indel_costs: Optional[Mapping[str, float]] = None,
        substitution_costs_path: Optional[Path] = None,
        indel_costs_path: Optional[Path] = None,
        compound_cost_strategy: str = "average_components",
    ) -> "CostScheme":
        substitution_costs = cls.load_substitution_costs(
            substitution_costs_path
        )
        substitution_costs.update(custom_substitution_costs or {})

        indel_costs = cls.load_indel_costs(indel_costs_path)
        indel_costs.update(custom_indel_costs or {})

        return cls(
            alphabet=alphabet,
            default_substitution_cost=default_substitution_cost,
            indel_cost=indel_cost,
            custom_substitution_costs=substitution_costs,
            custom_indel_costs=indel_costs,
            compound_cost_strategy=compound_cost_strategy,
        )

    @staticmethod
    def load_substitution_costs(
        path: Optional[Path],
    ) -> Dict[Tuple[str, str], float]:
        if path is None:
            return {}

        cost_path = Path(path)
        if cost_path.suffix.lower() == ".csv":
            df = pd.read_csv(cost_path)
            required = {"state_a", "state_b", "cost"}
            missing = required.difference(df.columns)
            if missing:
                raise ValueError(
                    f"Substitution cost file is missing columns: {missing}"
                )
            return {
                (str(row.state_a).strip(), str(row.state_b).strip()): row.cost
                for row in df.itertuples(index=False)
            }

        if cost_path.suffix.lower() == ".json":
            with cost_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError(
                    "Substitution cost JSON must be a list of objects with "
                    "state_a, state_b, and cost."
                )
            return {
                (str(item["state_a"]).strip(), str(item["state_b"]).strip()):
                item["cost"]
                for item in data
            }

        raise ValueError(
            "Substitution cost file must be a .csv or .json file."
        )

    @staticmethod
    def load_indel_costs(path: Optional[Path]) -> Dict[str, float]:
        if path is None:
            return {}

        cost_path = Path(path)
        if cost_path.suffix.lower() == ".csv":
            df = pd.read_csv(cost_path)
            required = {"state", "cost"}
            missing = required.difference(df.columns)
            if missing:
                raise ValueError(f"Indel cost file is missing columns: {missing}")
            return {
                str(row.state).strip(): row.cost
                for row in df.itertuples(index=False)
            }

        if cost_path.suffix.lower() == ".json":
            with cost_path.open(encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                raise ValueError(
                    "Indel cost JSON must be an object mapping states to costs."
                )
            return {
                str(state).strip(): cost
                for state, cost in data.items()
            }

        raise ValueError("Indel cost file must be a .csv or .json file.")

    def _build_substitution_matrix(self) -> Dict[Tuple[str, str], float]:
        matrix: Dict[Tuple[str, str], float] = {}

        for a, b in itertools.product(self.alphabet, self.alphabet):
            matrix[(a, b)] = self.substitution_cost(a, b)

        return matrix

    def substitution_cost(self, a: str, b: str) -> float:
        a = str(a)
        b = str(b)

        if a == b:
            return 0.0

        custom_cost = self._direct_substitution_cost(a, b)
        if custom_cost is not None:
            return custom_cost

        a_components = self._split_state(a)
        b_components = self._split_state(b)
        if len(a_components) > 1 or len(b_components) > 1:
            costs = [
                self.substitution_cost(component_a, component_b)
                for component_a in a_components
                for component_b in b_components
            ]
            return float(np.mean(costs))

        return self.default_substitution_cost

    def indel_cost(self, state: str) -> float:
        state = str(state)
        if state in self.custom_indel_costs:
            return self.custom_indel_costs[state]

        components = self._split_state(state)
        if len(components) > 1:
            costs = [self.indel_cost(component) for component in components]
            return float(np.mean(costs))

        return self.default_indel_cost

    def substitution_cost_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                [self.substitution_matrix[(row_state, col_state)]
                 for col_state in self.alphabet]
                for row_state in self.alphabet
            ],
            index=self.alphabet,
            columns=self.alphabet,
        )

    def indel_cost_dataframe(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "state": self.alphabet,
                "indel_cost": [
                    self.indel_costs[state]
                    for state in self.alphabet
                ],
            }
        )

    def _direct_substitution_cost(self, a: str, b: str) -> Optional[float]:
        if (a, b) in self.custom_substitution_costs:
            return self.custom_substitution_costs[(a, b)]
        if (b, a) in self.custom_substitution_costs:
            return self.custom_substitution_costs[(b, a)]
        return None

    def _normalize_substitution_costs(
        self,
        costs: Mapping[Tuple[str, str], float],
    ) -> Dict[Tuple[str, str], float]:
        normalized: Dict[Tuple[str, str], float] = {}

        for key, raw_cost in costs.items():
            if len(key) != 2:
                raise ValueError(
                    "Substitution cost keys must be (state_a, state_b) pairs."
                )

            state_a = str(key[0]).strip()
            state_b = str(key[1]).strip()
            cost = self._validate_cost(
                raw_cost,
                f"custom_substitution_costs[{state_a!r}, {state_b!r}]",
            )

            reverse_key = (state_b, state_a)
            if reverse_key in normalized and not np.isclose(
                normalized[reverse_key],
                cost,
            ):
                raise ValueError(
                    "Conflicting symmetric substitution costs for "
                    f"{(state_a, state_b)} and {reverse_key}."
                )

            normalized[(state_a, state_b)] = cost

        return normalized

    def _normalize_indel_costs(
        self,
        costs: Mapping[str, float],
    ) -> Dict[str, float]:
        return {
            str(state).strip(): self._validate_cost(
                cost,
                f"custom_indel_costs[{state!r}]",
            )
            for state, cost in costs.items()
        }

    @staticmethod
    def _validate_cost(value: float, name: str) -> float:
        try:
            cost = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must be numeric.") from exc

        if not np.isfinite(cost):
            raise ValueError(f"{name} must be finite.")

        if cost < 0:
            raise ValueError(f"{name} must be non-negative.")

        return cost

    def _warn_for_unknown_custom_states(self) -> None:
        known_states = set(self.alphabet) | self.alphabet_components
        unknown_states = set(self.custom_indel_costs).difference(known_states)

        for state_a, state_b in self.custom_substitution_costs:
            if state_a not in known_states:
                unknown_states.add(state_a)
            if state_b not in known_states:
                unknown_states.add(state_b)

        if unknown_states:
            logging.warning(
                "Custom costs reference states not present in the sequence "
                "alphabet: %s",
                sorted(unknown_states),
            )

    @classmethod
    def _alphabet_components(cls, alphabet: Sequence[str]) -> set[str]:
        components = set()
        for state in alphabet:
            components.update(cls._split_state(state))
        return components

    @staticmethod
    def _split_state(state: str) -> Tuple[str, ...]:
        return tuple(
            component.strip()
            for component in str(state).split("|")
            if component.strip()
        )
