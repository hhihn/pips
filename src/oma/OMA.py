"""
Baseline Optimal Matching Analysis for MAXQDA-style interval annotations.

Input CSV format:
Filename,Sequence_Code,Sequence_Start,Sequence_End,id
1-P-1_transformed.xlsx,6.1.1 PK,"0:00:31,6","0:00:51,9",0_0
...

Main workflow:
1. Load interval-coded annotations.
2. Parse German-style timestamps.
3. Discretize each sequence into equal-width time bins.
4. Convert overlapping annotations into categorical sequence states.
5. Compute pairwise OMA distances via Needleman-Wunsch.
6. Cluster sequences.
7. Summarize behavioral typologies.
8. Optionally create a Plotly sunburst visualization.

Install:
pip install pandas numpy scipy scikit-learn plotly
"""

from __future__ import annotations

from pathlib import Path

import logging

from OMAConfig import OMAConfig
from OMAPipeline import OMAPipeline


# ---------------------------------------------------------------------
# Example usage
# ---------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    config = OMAConfig(
        input_path=Path("../extracted_sequences.csv"),
        output_dir=Path("../oma_output"),
        # 1 second is a useful baseline.
        # For very short care routines, 0.5 seconds may be more sensitive.
        time_step_seconds=1.0,
        # Recommended first baseline:
        overlap_strategy="combine",
        # OMA costs:
        default_substitution_cost=2.0,
        indel_cost=1.0,
        # Use average or complete with precomputed OMA distances.
        # Do not use Ward directly on a precomputed distance matrix.
        clustering_method="average",
        min_clusters=2,
        max_clusters=8,
    )

    # Optional: theory-informed substitution costs.
    #
    # Example:
    # custom_costs = {
    #     ("2.1.2.3 PK", "2.1.3.1 PK"): 1.0,
    #     ("6.1.1 PK", "6.2.1 PK"): 0.5,
    # }
    #
    # For the first baseline, leave this empty.
    custom_costs = {}

    pipeline = OMAPipeline(
        config=config,
        custom_substitution_costs=custom_costs,
    )

    pipeline.run()
