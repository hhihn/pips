from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

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

    # How to handle overlapping codes per time bin:
    # "combine" = create compound states from all active codes
    # "priority" = select first active code based on code_priority
    overlap_strategy: str = "combine"

    # Used only if overlap_strategy == "priority"
    code_priority: Optional[List[str]] = None

    empty_state: str = "EMPTY"

    # OMA costs
    default_substitution_cost: float = 2.0
    indel_cost: Optional[float] = None

    # Clustering
    min_clusters: int = 2
    max_clusters: int = 8
    clustering_method: str = "average"
    random_state: int = 42

    # Output
    output_dir: Path = Path("../oma_output")
