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
        output_dir=Path("./oma_output"),
        # 1 second is a useful baseline.
        # For very short care routines, 0.5 seconds may be more sensitive.
        time_step_seconds=1.0,
        # Use "sts" to preserve duration or "dss" to keep only state-change order.
        sequence_representation="dss",
        # "combine", "priority", or "split".
        overlap_strategy="split",
        # Ignore empty time bins in matching and outputs.
        include_empty_state=False,
        # Optional: codes to ignore for matching.
        excluded_codes=["6.1.1 PK", "6.2.1 PK", "6.2.2 PK"],
        # Optional: compare sequence groups after OMA without matching on
        # the care-type marker codes themselves.
        care_type_codes={
            "6.2.1": "nase_putzen",
            "6.2.2": "gesicht_abwischen",
        },
        # Optional: map codes to display names in output files.
        code_name_mapping_path=Path("output.json"),
        # OMA costs:
        default_substitution_cost=2.0,
        indel_cost=1.0,
        # Optional: provide custom costs directly or via CSV/JSON files.
        custom_substitution_costs=None,
        custom_indel_costs=None,
        substitution_costs_path=None,
        indel_costs_path=None,
        compound_cost_strategy="average_components",
        # Use average or complete with precomputed OMA distances.
        # Do not use Ward directly on a precomputed distance matrix.
        clustering_method="average",
        min_clusters=2,
        max_clusters=10,
        pseudo_f_permutations=10000,
        pairwise_permanova_permutations=None,
        pairwise_permanova_alpha=0.05,
    )

    # Optional: theory-informed substitution costs.
    #
    # Example:
    # custom_costs = {
    #     ("2.1.2.3 PK", "2.1.3.1 PK"): 1.0,
    #     ("6.1.1 PK", "6.2.1 PK"): 0.5,
    # }
    # custom_indel_costs = {
    #     "2.1.2.3 PK": 2.0,
    # }
    #
    # For the first baseline, leave this empty.
    custom_costs = {}
    custom_indel_costs = {
      #  "2.2.3.4 PK": 2, # halten
      #  "6.4.3 PK": 1, # von vorne
      #  "6.4.4 PK": 2, # von der Seite
      #  "6.4.5 PK": 3 # von hinten
    }

    pipeline = OMAPipeline(
        config=config,
        custom_substitution_costs=custom_costs,
        custom_indel_costs=custom_indel_costs,
    )

    pipeline.run()
