from typing import Dict, List

import pandas as pd
import numpy as np

from OMAConfig import OMAConfig
# ---------------------------------------------------------------------
# Sequence construction
# ---------------------------------------------------------------------


class SequenceBuilder:
    def __init__(self, config: OMAConfig):
        self.config = config

    def build_sequences(self, df: pd.DataFrame) -> Dict[str, List[str]]:
        sequences: Dict[str, List[str]] = {}

        for sequence_id, group in df.groupby(self.config.id_col):
            sequences[sequence_id] = self._build_single_sequence(group)

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
                .unique()
                .tolist()
            )

            state = self._resolve_active_codes(active_codes)
            states.append(state)

        return states

    def _resolve_active_codes(self, active_codes: List[str]) -> str:
        if not active_codes:
            return self.config.empty_state

        active_codes = sorted(active_codes)

        if self.config.overlap_strategy == "combine":
            return "|".join(active_codes)

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

            return ranked_codes[0]

        raise ValueError(f"Unknown overlap strategy: {self.config.overlap_strategy}")
