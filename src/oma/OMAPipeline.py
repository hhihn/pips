import logging
from typing import Dict, List, Tuple, Optional

import pandas as pd

from OMAConfig import OMAConfig
from MAXQDALoader import MaxQDALoader
from SequenceBuilder import SequenceBuilder
from SequenceClusterer import SequenceClusterer
from SequenceInterpreter import SequenceInterpreter
from SequenceVisualizer import SequenceVisualizer
from CostScheme import CostScheme
from OptimalMatcher import OptimalMatcher
from CodeNameMapper import CodeNameMapper
from CareTypeAnalyzer import CareTypeAnalyzer

# ---------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------


class OMAPipeline:
    def __init__(
        self,
        config: OMAConfig,
        custom_substitution_costs: Optional[Dict[Tuple[str, str], float]] = None,
        custom_indel_costs: Optional[Dict[str, float]] = None,
    ):
        self.config = config
        self.custom_substitution_costs = custom_substitution_costs or {}
        self.custom_indel_costs = custom_indel_costs or {}

        self.loader = MaxQDALoader(config)
        self.sequence_builder = SequenceBuilder(config)
        self.clusterer = SequenceClusterer(config)
        self.interpreter = SequenceInterpreter(config)
        self.visualizer = SequenceVisualizer(config)
        self.code_name_mapper = CodeNameMapper(config)
        self.care_type_analyzer = CareTypeAnalyzer(config)

    def run(self) -> None:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

        logging.info("Loading data...")
        df = self.loader.load()

        logging.info("Building discrete sequences...")
        sequences = self.sequence_builder.build_sequences(df)
        logging.info(
            "Using %s sequence representation.",
            self.config.sequence_representation.upper(),
        )

        if len(sequences) < 2:
            raise ValueError("At least two sequences are required for OMA.")

        alphabet = sorted({state for seq in sequences.values() for state in seq})

        custom_substitution_costs = dict(
            self.config.custom_substitution_costs or {}
        )
        custom_substitution_costs.update(self.custom_substitution_costs)
        custom_indel_costs = dict(self.config.custom_indel_costs or {})
        custom_indel_costs.update(self.custom_indel_costs)

        cost_scheme = CostScheme.from_files(
            alphabet=alphabet,
            default_substitution_cost=self.config.default_substitution_cost,
            indel_cost=self.config.indel_cost,
            custom_substitution_costs=custom_substitution_costs,
            custom_indel_costs=custom_indel_costs,
            substitution_costs_path=self.config.substitution_costs_path,
            indel_costs_path=self.config.indel_costs_path,
            compound_cost_strategy=self.config.compound_cost_strategy,
        )

        matcher = OptimalMatcher(cost_scheme)

        logging.info("Computing OMA distance matrix...")
        distance_matrix = matcher.distance_matrix(sequences, normalize=True)

        distance_matrix.to_csv(
            self.config.output_dir / "oma_distance_matrix.csv",
            index=True,
        )
        cost_scheme.substitution_cost_dataframe().to_csv(
            self.config.output_dir / "oma_substitution_cost_matrix.csv",
            index=True,
        )
        cost_scheme.indel_cost_dataframe().to_csv(
            self.config.output_dir / "oma_indel_costs.csv",
            index=False,
        )

        logging.info("Choosing number of clusters...")
        cluster_scores = self.clusterer.choose_number_of_clusters(distance_matrix)
        cluster_scores.to_csv(
            self.config.output_dir / "cluster_scores.csv",
            index=False,
        )
        cluster_scores[["n_clusters", "silhouette_score"]].sort_values(
            "silhouette_score",
            ascending=False,
        ).to_csv(
            self.config.output_dir / "cluster_silhouette_scores.csv",
            index=False,
        )

        best_k = int(cluster_scores.iloc[0]["n_clusters"])
        logging.info("Best k according to pseudo-F score: %s", best_k)

        labels = self.clusterer.cluster_with_precomputed_distance(
            distance_matrix,
            n_clusters=best_k,
        )

        labels.to_csv(
            self.config.output_dir / "cluster_labels.csv",
            header=True,
        )

        self._write_care_type_analysis(df, distance_matrix, labels)

        logging.info("Finding prototypical sequences per cluster...")
        sequence_filenames = self._sequence_filename_lookup(df)

        prototypes = self.interpreter.prototypical_sequences(
            sequences=sequences,
            labels=labels,
            distance_matrix=distance_matrix,
            filenames=sequence_filenames,
            code_name_mapper=self.code_name_mapper,
        )
        prototypes.to_csv(
            self.config.output_dir / "cluster_prototypes.csv",
            index=False,
        )

        prototype_steps = self.interpreter.prototypical_sequence_steps(
            prototypes=prototypes,
            sequences=sequences,
            code_name_mapper=self.code_name_mapper,
        )
        prototype_steps.to_csv(
            self.config.output_dir / "cluster_prototype_steps.csv",
            index=False,
        )

        distances_to_prototypes = self.interpreter.distances_to_prototypes(
            labels=labels,
            distance_matrix=distance_matrix,
            prototypes=prototypes,
            filenames=sequence_filenames,
        )
        distances_to_prototypes.to_csv(
            self.config.output_dir / "cluster_distances_to_prototypes.csv",
            index=False,
        )

        logging.info("Running pairwise PERMANOVA-style cluster comparisons...")
        pairwise_permanova = self.clusterer.pairwise_permanova(
            distance_matrix,
            labels,
        )
        pairwise_permanova.to_csv(
            self.config.output_dir / "cluster_pair_permanova.csv",
            index=False,
        )

        logging.info("Creating cluster-ordered OMA distance heatmap...")
        self.visualizer.create_distance_heatmap(
            distance_matrix,
            labels,
            output_path=self.config.output_dir / "oma_distance_heatmap.html",
        )

        logging.info("Interpreting clusters...")
        state_dist = self.interpreter.state_distribution(sequences, labels)
        state_dist = self._rename_state_columns(state_dist, ["state"])
        state_dist.to_csv(
            self.config.output_dir / "cluster_state_distribution.csv",
            index=False,
        )

        lengths = self.interpreter.sequence_lengths(sequences, labels)
        lengths.to_csv(
            self.config.output_dir / "sequence_lengths_by_cluster.csv",
            index=False,
        )

        code_frequencies = self.interpreter.cluster_code_frequencies(
            sequences,
            labels,
            code_name_mapper=self.code_name_mapper,
        )
        code_frequencies.to_csv(
            self.config.output_dir / "cluster_code_frequencies.csv",
            index=False,
        )

        raw_code_frequencies = self.interpreter.raw_cluster_code_frequencies(
            df,
            labels,
            code_name_mapper=self.code_name_mapper,
        )
        raw_code_frequencies.to_csv(
            self.config.output_dir / "raw_cluster_code_frequencies.csv",
            index=False,
        )

        transitions = self.interpreter.transition_table(sequences, labels)
        transitions = self._rename_state_columns(
            transitions,
            ["from_state", "to_state"],
        )
        transitions.to_csv(
            self.config.output_dir / "cluster_transition_table.csv",
            index=False,
        )

        logging.info("Done. Results written to: %s", self.config.output_dir)

    def _write_care_type_analysis(
        self,
        df: pd.DataFrame,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
    ) -> None:
        if not self.config.care_type_codes:
            return

        logging.info("Analyzing care-type differences...")
        care_types = self.care_type_analyzer.sequence_care_types(df)
        care_types.to_csv(
            self.config.output_dir / "care_type_by_sequence.csv",
            index=False,
        )

        distance_group_comparison = (
            self.care_type_analyzer.distance_group_comparison(
                distance_matrix,
                care_types,
                self.clusterer,
            )
        )
        distance_group_comparison.to_csv(
            self.config.output_dir / "care_type_distance_permanova.csv",
            index=False,
        )

        distance_summary = self.care_type_analyzer.distance_summary(
            distance_matrix,
            care_types,
        )
        distance_summary.to_csv(
            self.config.output_dir / "care_type_distance_summary.csv",
            index=False,
        )

        cluster_crosstab = self.care_type_analyzer.cluster_crosstab(
            care_types,
            labels,
        )
        cluster_crosstab.to_csv(
            self.config.output_dir / "care_type_cluster_crosstab.csv",
            index=False,
        )

        cluster_association = self.care_type_analyzer.cluster_association(
            care_types,
            labels,
        )
        cluster_association.to_csv(
            self.config.output_dir / "care_type_cluster_association.csv",
            index=False,
        )

        recommendation = self.care_type_analyzer.recommendation(
            distance_group_comparison,
            cluster_association,
        )
        recommendation.to_csv(
            self.config.output_dir / "care_type_recommendation.csv",
            index=False,
        )

    def _rename_state_columns(
        self,
        df: pd.DataFrame,
        columns: List[str],
    ) -> pd.DataFrame:
        renamed = df.copy()
        for column in columns:
            if column in renamed.columns:
                renamed[column] = renamed[column].map(
                    self.code_name_mapper.rename_state
                )

        return renamed

    def _sequence_filename_lookup(self, df: pd.DataFrame) -> Dict[str, str]:
        if self.config.filename_col not in df.columns:
            return {}

        filenames = {}
        for sequence_id, group in df.groupby(self.config.id_col):
            unique_filenames = (
                group[self.config.filename_col]
                .dropna()
                .astype(str)
                .str.strip()
                .unique()
                .tolist()
            )
            filenames[str(sequence_id)] = " | ".join(unique_filenames)

        return filenames
