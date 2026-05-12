import logging
from typing import Dict, Tuple, Optional

from OMAConfig import OMAConfig
from MAXQDALoader import MaxQDALoader
from SequenceBuilder import SequenceBuilder
from SequenceClusterer import SequenceClusterer
from SequenceInterpreter import SequenceInterpreter
from SequenceVisualizer import SequenceVisualizer
from CostScheme import CostScheme
from OptimalMatcher import OptimalMatcher

# ---------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------


class OMAPipeline:
    def __init__(
        self,
        config: OMAConfig,
        custom_substitution_costs: Optional[Dict[Tuple[str, str], float]] = None,
    ):
        self.config = config
        self.custom_substitution_costs = custom_substitution_costs or {}

        self.loader = MaxQDALoader(config)
        self.sequence_builder = SequenceBuilder(config)
        self.clusterer = SequenceClusterer(config)
        self.interpreter = SequenceInterpreter(config)
        self.visualizer = SequenceVisualizer(config)

    def run(self) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        logging.info("Loading data...")
        df = self.loader.load()

        logging.info("Building discrete sequences...")
        sequences = self.sequence_builder.build_sequences(df)

        if len(sequences) < 2:
            raise ValueError("At least two sequences are required for OMA.")

        alphabet = sorted({state for seq in sequences.values() for state in seq})

        cost_scheme = CostScheme(
            alphabet=alphabet,
            default_substitution_cost=self.config.default_substitution_cost,
            indel_cost=self.config.indel_cost,
            custom_substitution_costs=self.custom_substitution_costs,
        )

        matcher = OptimalMatcher(cost_scheme)

        logging.info("Computing OMA distance matrix...")
        distance_matrix = matcher.distance_matrix(sequences, normalize=True)

        distance_matrix.to_csv(
            self.config.output_dir / "oma_distance_matrix.csv",
            index=True,
        )

        logging.info("Choosing number of clusters...")
        cluster_scores = self.clusterer.choose_number_of_clusters(distance_matrix)
        cluster_scores.to_csv(
            self.config.output_dir / "cluster_silhouette_scores.csv",
            index=False,
        )

        best_k = int(cluster_scores.iloc[0]["n_clusters"])
        logging.info("Best k according to silhouette score: %s", best_k)

        labels = self.clusterer.cluster_with_precomputed_distance(
            distance_matrix,
            n_clusters=best_k,
        )

        labels.to_csv(
            self.config.output_dir / "cluster_labels.csv",
            header=True,
        )

        logging.info("Interpreting clusters...")
        state_dist = self.interpreter.state_distribution(sequences, labels)
        state_dist.to_csv(
            self.config.output_dir / "cluster_state_distribution.csv",
            index=False,
        )

        lengths = self.interpreter.sequence_lengths(sequences, labels)
        lengths.to_csv(
            self.config.output_dir / "sequence_lengths_by_cluster.csv",
            index=False,
        )

        transitions = self.interpreter.transition_table(sequences, labels)
        transitions.to_csv(
            self.config.output_dir / "cluster_transition_table.csv",
            index=False,
        )

        logging.info("Creating sunburst visualization...")
        self.visualizer.create_sunburst(
            transitions,
            output_path=self.config.output_dir / "transition_sunburst.html",
            min_transition_count=1,
        )

        logging.info("Done. Results written to: %s", self.config.output_dir)
