from typing import Dict, Sequence, List
import numpy as np
import pandas as pd

from CostScheme import CostScheme

# ---------------------------------------------------------------------
# Optimal Matching / Needleman-Wunsch
# ---------------------------------------------------------------------


class OptimalMatcher:
    def __init__(self, cost_scheme: CostScheme):
        self.cost_scheme = cost_scheme

    def distance(self, seq_a: Sequence[str], seq_b: Sequence[str]) -> float:
        """
        Needleman-Wunsch style dynamic programming distance.

        dp[i, j] = minimum cost to transform seq_a[:i] into seq_b[:j].
        """
        n = len(seq_a)
        m = len(seq_b)

        dp = np.zeros((n + 1, m + 1), dtype=float)

        for i in range(1, n + 1):
            dp[i, 0] = i * self.cost_scheme.indel_cost

        for j in range(1, m + 1):
            dp[0, j] = j * self.cost_scheme.indel_cost

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                delete_cost = dp[i - 1, j] + self.cost_scheme.indel_cost
                insert_cost = dp[i, j - 1] + self.cost_scheme.indel_cost
                substitute_cost = dp[i - 1, j - 1] + self.cost_scheme.substitution_cost(
                    seq_a[i - 1], seq_b[j - 1]
                )

                dp[i, j] = min(delete_cost, insert_cost, substitute_cost)

        return float(dp[n, m])

    def distance_matrix(
        self,
        sequences: Dict[str, List[str]],
        normalize: bool = True,
    ) -> pd.DataFrame:
        ids = list(sequences.keys())
        n = len(ids)

        matrix = np.zeros((n, n), dtype=float)

        for i in range(n):
            for j in range(i + 1, n):
                seq_i = sequences[ids[i]]
                seq_j = sequences[ids[j]]

                dist = self.distance(seq_i, seq_j)

                if normalize:
                    max_len = max(len(seq_i), len(seq_j))
                    if max_len > 0:
                        dist = dist / max_len

                matrix[i, j] = dist
                matrix[j, i] = dist

        return pd.DataFrame(matrix, index=ids, columns=ids)
