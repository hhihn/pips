from pathlib import Path
import logging

import pandas as pd
import plotly.express as px

from OMAConfig import OMAConfig
# ---------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------


class SequenceVisualizer:
    def __init__(self, config: OMAConfig):
        self.config = config

    def create_sunburst(
        self,
        transition_table: pd.DataFrame,
        output_path: Path,
        min_transition_count: int = 1,
    ) -> None:
        """
        Creates a simple cluster-level transition sunburst.

        The hierarchy is:
        cluster -> from_state -> to_state
        """
        if transition_table.empty:
            logging.warning("Transition table is empty. No sunburst created.")
            return

        plot_df = transition_table[
            transition_table["size"] >= min_transition_count
        ].copy()

        plot_df["cluster_label"] = "Cluster " + plot_df["cluster"].astype(str)

        fig = px.sunburst(
            plot_df,
            path=["cluster_label", "from_state", "to_state"],
            values="size",
            title="Common Behavioral Transitions by Cluster",
        )

        fig.write_html(output_path)
