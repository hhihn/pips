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

    def create_distance_heatmap(
        self,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
        output_path: Path,
    ) -> None:
        """
        Creates a cluster-ordered heatmap of the OMA distance matrix.

        Rows and columns are ordered by cluster label, making low-distance
        blocks visible as emerging sequence clusters.
        """
        if distance_matrix.empty:
            logging.warning("Distance matrix is empty. No heatmap created.")
            return

        labels = labels.reindex(distance_matrix.index)
        if labels.isna().any():
            missing = labels[labels.isna()].index.tolist()
            raise ValueError(f"Missing cluster labels for sequences: {missing}")

        order_df = pd.DataFrame(
            {
                "sequence_id": distance_matrix.index,
                "cluster": labels.astype(int).values,
            },
            index=distance_matrix.index,
        ).sort_values(["cluster", "sequence_id"])

        ordered_ids = order_df.index.tolist()
        ordered_matrix = distance_matrix.loc[ordered_ids, ordered_ids]
        tick_labels = [
            f"C{cluster} | {sequence_id}"
            for sequence_id, cluster in zip(
                order_df["sequence_id"],
                order_df["cluster"],
            )
        ]

        fig = px.imshow(
            ordered_matrix.values,
            x=tick_labels,
            y=tick_labels,
            color_continuous_scale="Viridis",
            origin="upper",
            labels={
                "x": "Sequence",
                "y": "Sequence",
                "color": "OMA distance",
            },
            title="OMA Distance Matrix Ordered by Cluster",
        )

        cluster_sizes = order_df["cluster"].value_counts(sort=False).tolist()
        boundary = 0
        for size in cluster_sizes[:-1]:
            boundary += size
            line_at = boundary - 0.5
            fig.add_shape(
                type="line",
                x0=line_at,
                x1=line_at,
                y0=-0.5,
                y1=len(ordered_ids) - 0.5,
                line={"color": "white", "width": 2},
            )
            fig.add_shape(
                type="line",
                x0=-0.5,
                x1=len(ordered_ids) - 0.5,
                y0=line_at,
                y1=line_at,
                line={"color": "white", "width": 2},
            )

        fig.update_layout(
            width=max(800, min(1800, 24 * len(ordered_ids))),
            height=max(800, min(1800, 24 * len(ordered_ids))),
            xaxis={"tickangle": 90},
            yaxis={"autorange": "reversed"},
        )

        fig.write_html(output_path)
