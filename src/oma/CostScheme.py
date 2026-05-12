from typing import Dict, Optional, Tuple, Sequence
import itertools
# ---------------------------------------------------------------------
# Cost scheme
# ---------------------------------------------------------------------


class CostScheme:
    def __init__(
        self,
        alphabet: Sequence[str],
        default_substitution_cost: float = 2.0,
        indel_cost: Optional[float] = None,
        custom_substitution_costs: Optional[Dict[Tuple[str, str], float]] = None,
    ):
        self.alphabet = sorted(set(alphabet))
        self.default_substitution_cost = default_substitution_cost
        self.indel_cost = (
            indel_cost if indel_cost is not None else default_substitution_cost / 2.0
        )
        self.custom_substitution_costs = custom_substitution_costs or {}

        self.substitution_matrix = self._build_substitution_matrix()

    def _build_substitution_matrix(self) -> Dict[Tuple[str, str], float]:
        matrix: Dict[Tuple[str, str], float] = {}

        for a, b in itertools.product(self.alphabet, self.alphabet):
            if a == b:
                cost = 0.0
            else:
                cost = self.custom_substitution_costs.get(
                    (a, b),
                    self.custom_substitution_costs.get(
                        (b, a),
                        self.default_substitution_cost,
                    ),
                )

            matrix[(a, b)] = float(cost)

        return matrix

    def substitution_cost(self, a: str, b: str) -> float:
        return self.substitution_matrix[(a, b)]
