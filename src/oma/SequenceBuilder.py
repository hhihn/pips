from typing import Dict, List, Tuple

import pandas as pd
import numpy as np

from CodeNormalizer import normalize_code_for_lookup
from OMAConfig import OMAConfig
# ---------------------------------------------------------------------
# Sequence construction
# ---------------------------------------------------------------------


class SequenceBuilder:
    def __init__(self, config: OMAConfig):
        self.config = config
        self.excluded_codes = {
            normalize_code_for_lookup(code)
            for code in (self.config.excluded_codes or [])
        }

    def build_sequences(self, df: pd.DataFrame) -> Dict[str, List[str]]:
        sequences: Dict[str, List[str]] = {}

        for sequence_id, group in df.groupby(self.config.id_col):
            sequence = self._build_single_sequence(group)
            sequences[sequence_id] = self._apply_sequence_representation(sequence)

        return sequences

    def _build_single_sequence(self, group: pd.DataFrame) -> List[str]:
        min_start = group["start_s"].min()
        max_end = group["end_s"].max()

        # Normalize each sequence to start at t = 0
        duration = max_end - min_start
        n_steps = int(np.ceil(duration / self.config.time_step_seconds))

        states: List[str] = []

        for step in range(n_steps):
            t_start = min_start + step * self.config.time_step_seconds
            t_end = t_start + self.config.time_step_seconds

            active_codes = (
                group.loc[
                    (group["start_s"] < t_end) & (group["end_s"] > t_start),
                    self.config.code_col,
                ]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )

            states.extend(self._resolve_active_codes(active_codes))

        if not self.config.include_empty_state:
            states = [state for state in states if state != self.config.empty_state]

        return states

    def _resolve_active_codes(self, active_codes: List[str]) -> List[str]:
        if not active_codes:
            return [self.config.empty_state]

        if self.excluded_codes:
            active_codes = [
                code for code in active_codes
                if normalize_code_for_lookup(code) not in self.excluded_codes
            ]

            if not active_codes:
                return [self.config.empty_state]

        active_codes = sorted(active_codes, key=self._canonical_code_sort_key)

        if self.config.overlap_strategy == "combine":
            return ["|".join(active_codes)]

        if self.config.overlap_strategy == "priority":
            if not self.config.code_priority:
                raise ValueError(
                    "code_priority must be provided when overlap_strategy='priority'."
                )

            priority_lookup = {
                code: rank for rank, code in enumerate(self.config.code_priority)
            }

            ranked_codes = sorted(
                active_codes,
                key=lambda c: priority_lookup.get(c, len(priority_lookup)),
            )

            return [ranked_codes[0]]

        if self.config.overlap_strategy == "split":
            return active_codes

        raise ValueError(f"Unknown overlap strategy: {self.config.overlap_strategy}")

    @staticmethod
    def _canonical_code_sort_key(code: str) -> Tuple[List[int], str]:
        lookup_code = normalize_code_for_lookup(code)
        parts = lookup_code.split(".")

        if all(part.isdigit() for part in parts):
            return [int(part) for part in parts], str(code)

        return [], str(code)

    def _apply_sequence_representation(self, sequence: List[str]) -> List[str]:
        representation = self.config.sequence_representation.lower()

        if representation == "sts":
            return sequence

        if representation == "dss":
            return self._distinct_successive_states(sequence)

        raise ValueError(
            "Unknown sequence representation: "
            f"{self.config.sequence_representation}. Use 'sts' or 'dss'."
        )

    @staticmethod
    def _distinct_successive_states(sequence: List[str]) -> List[str]:
        if not sequence:
            return []

        dss_sequence = [sequence[0]]
        for state in sequence[1:]:
            if state != dss_sequence[-1]:
                dss_sequence.append(state)

        return dss_sequence
