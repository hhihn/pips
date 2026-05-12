from typing import Dict, List

import pandas as pd

from OMAConfig import OMAConfig

# ---------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------


class SequenceInterpreter:
    def __init__(self, config: OMAConfig):
        self.config = config

    def state_distribution(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
    ) -> pd.DataFrame:
        rows = []

        for sequence_id, seq in sequences.items():
            cluster = labels.loc[sequence_id]
            counts = pd.Series(seq).value_counts(normalize=True)

            for state, proportion in counts.items():
                rows.append(
                    {
                        "id": sequence_id,
                        "cluster": cluster,
                        "state": state,
                        "proportion": proportion,
                    }
                )

        result = pd.DataFrame(rows)

        if result.empty:
            return result

        return (
            result.groupby(["cluster", "state"], as_index=False)["proportion"]
            .mean()
            .sort_values(["cluster", "proportion"], ascending=[True, False])
        )

    def sequence_lengths(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "id": list(sequences.keys()),
                "n_steps": [len(seq) for seq in sequences.values()],
            }
        ).assign(cluster=lambda d: d["id"].map(labels.to_dict()))

    def transition_table(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
    ) -> pd.DataFrame:
        rows = []

        for sequence_id, seq in sequences.items():
            cluster = labels.loc[sequence_id]

            for current_state, next_state in zip(seq[:-1], seq[1:]):
                rows.append(
                    {
                        "id": sequence_id,
                        "cluster": cluster,
                        "from_state": current_state,
                        "to_state": next_state,
                    }
                )

        transitions = pd.DataFrame(rows)

        if transitions.empty:
            return transitions

        return (
            transitions.groupby(["cluster", "from_state", "to_state"], as_index=False)
            .size()
            .sort_values(["cluster", "size"], ascending=[True, False])
        )
