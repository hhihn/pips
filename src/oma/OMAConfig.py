from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------


@dataclass
class OMAConfig:
    input_path: Path
    id_col: str = "id"
    code_col: str = "Sequence_Code"
    start_col: str = "Sequence_Start"
    end_col: str = "Sequence_End"
    filename_col: str = "Filename"

    time_step_seconds: float = 1.0

    # Sequence representation used for OMA:
    # "sts" = state sequence, preserving repeated states and duration
    # "dss" = distinct successive states, preserving only state-change order
    sequence_representation: str = "sts"

    # How to handle overlapping codes per time bin:
    # "combine" = create compound states from all active codes
    # "priority" = select first active code based on code_priority
    # "split" = append each active code as its own state in canonical code order
    overlap_strategy: str = "combine"

    # Used only if overlap_strategy == "priority"
    code_priority: Optional[List[str]] = None

    # Codes listed here are ignored when constructing states for matching.
    # They still contribute to the sequence time span, but never appear in
    # simple or compound states.
    excluded_codes: Optional[List[str]] = None

    # Optional JSON file mapping code numbers to display names.
    code_name_mapping_path: Optional[Path] = Path("output.json")

    empty_state: str = "EMPTY"
    include_empty_state: bool = False

    # OMA costs
    default_substitution_cost: float = 2.0
    indel_cost: Optional[float] = None
    custom_substitution_costs: Optional[Dict[Tuple[str, str], float]] = None
    custom_indel_costs: Optional[Dict[str, float]] = None
    substitution_costs_path: Optional[Path] = None
    indel_costs_path: Optional[Path] = None
    compound_cost_strategy: str = "average_components"

    # Clustering
    min_clusters: int = 2
    max_clusters: int = 8
    clustering_method: str = "average"
    pseudo_f_permutations: int = 1000
    pairwise_permanova_permutations: Optional[int] = None
    pairwise_permanova_alpha: float = 0.05
    random_state: int = 42

    # Output
    output_dir: Path = Path("../oma_output")
