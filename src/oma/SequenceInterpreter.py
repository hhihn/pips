from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from OMAConfig import OMAConfig
from CodeNameMapper import CodeNameMapper

# ---------------------------------------------------------------------
# Interpretation
# ---------------------------------------------------------------------


class SequenceInterpreter:
    def __init__(self, config: OMAConfig):
        self.config = config

    def state_distribution(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
    ) -> pd.DataFrame:
        rows = []

        for sequence_id, seq in sequences.items():
            cluster = labels.loc[sequence_id]
            counts = pd.Series(seq).value_counts(normalize=True)

            for state, proportion in counts.items():
                rows.append(
                    {
                        "id": sequence_id,
                        "cluster": cluster,
                        "state": state,
                        "proportion": proportion,
                    }
                )

        result = pd.DataFrame(rows)

        if result.empty:
            return result

        return (
            result.groupby(["cluster", "state"], as_index=False)["proportion"]
            .mean()
            .sort_values(["cluster", "proportion"], ascending=[True, False])
        )

    def sequence_lengths(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
    ) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "id": list(sequences.keys()),
                "n_steps": [len(seq) for seq in sequences.values()],
            }
        ).assign(cluster=lambda d: d["id"].map(labels.to_dict()))

    def cluster_code_frequencies(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
        code_name_mapper: Optional[CodeNameMapper] = None,
    ) -> pd.DataFrame:
        code_name_mapper = code_name_mapper or CodeNameMapper(self.config)
        rows = []

        for sequence_id, sequence in sequences.items():
            cluster = labels.loc[sequence_id]
            for state in sequence:
                for code in self._state_components(state):
                    rows.append(
                        {
                            "id": sequence_id,
                            "cluster": cluster,
                            "code": code,
                        }
                    )

        output_columns = [
            "cluster",
            "code",
            "long_name",
            "occurrence_count",
            "occurrence_relative_within_cluster",
            "occurrence_percent_within_cluster",
            "sequence_count_with_code",
            "sequence_relative_with_code",
            "sequence_percent_with_code",
            "n_sequences_in_cluster",
            "total_code_occurrences_in_cluster",
        ]

        occurrences = pd.DataFrame(rows)
        if occurrences.empty:
            return pd.DataFrame(columns=output_columns)

        cluster_sequence_counts = (
            pd.Series(labels)
            .groupby(labels)
            .size()
            .rename("n_sequences_in_cluster")
        )
        total_cluster_occurrences = (
            occurrences.groupby("cluster")
            .size()
            .rename("total_code_occurrences_in_cluster")
        )
        occurrence_counts = (
            occurrences.groupby(["cluster", "code"])
            .size()
            .rename("occurrence_count")
        )
        sequence_counts = (
            occurrences.drop_duplicates(["cluster", "code", "id"])
            .groupby(["cluster", "code"])
            .size()
            .rename("sequence_count_with_code")
        )

        result = (
            pd.concat([occurrence_counts, sequence_counts], axis=1)
            .reset_index()
            .merge(
                cluster_sequence_counts.reset_index(name="n_sequences_in_cluster"),
                on="cluster",
                how="left",
            )
            .merge(
                total_cluster_occurrences.reset_index(),
                on="cluster",
                how="left",
            )
        )
        result["long_name"] = result["code"].map(code_name_mapper.rename_state)
        result["occurrence_relative_within_cluster"] = (
            result["occurrence_count"]
            / result["total_code_occurrences_in_cluster"]
        )
        result["occurrence_percent_within_cluster"] = (
            result["occurrence_relative_within_cluster"] * 100
        )
        result["sequence_relative_with_code"] = (
            result["sequence_count_with_code"]
            / result["n_sequences_in_cluster"]
        )
        result["sequence_percent_with_code"] = (
            result["sequence_relative_with_code"] * 100
        )

        return (
            result[output_columns]
            .sort_values(
                ["cluster", "occurrence_count", "sequence_count_with_code", "code"],
                ascending=[True, False, False, True],
            )
            .reset_index(drop=True)
        )

    def raw_cluster_code_frequencies(
        self,
        df: pd.DataFrame,
        labels: pd.Series,
        code_name_mapper: Optional[CodeNameMapper] = None,
    ) -> pd.DataFrame:
        code_name_mapper = code_name_mapper or CodeNameMapper(self.config)
        output_columns = [
            "cluster",
            "code",
            "long_name",
            "raw_observation_count",
            "raw_observation_relative_within_cluster",
            "raw_observation_percent_within_cluster",
            "sequence_count_with_code",
            "sequence_relative_with_code",
            "sequence_percent_with_code",
            "n_sequences_in_cluster",
            "total_raw_code_observations_in_cluster",
        ]

        if df.empty:
            return pd.DataFrame(columns=output_columns)

        raw = df[[self.config.id_col, self.config.code_col]].copy()
        raw[self.config.id_col] = raw[self.config.id_col].astype(str).str.strip()
        raw[self.config.code_col] = raw[self.config.code_col].astype(str).str.strip()
        raw = raw[raw[self.config.code_col].ne("")]

        label_lookup = labels.copy()
        label_lookup.index = label_lookup.index.astype(str)
        raw["cluster"] = raw[self.config.id_col].map(label_lookup.to_dict())

        if raw["cluster"].isna().any():
            missing = sorted(raw.loc[raw["cluster"].isna(), self.config.id_col].unique())
            raise ValueError(f"Missing cluster labels for raw sequence ids: {missing}")

        raw = raw.rename(
            columns={
                self.config.id_col: "id",
                self.config.code_col: "code",
            }
        )

        if raw.empty:
            return pd.DataFrame(columns=output_columns)

        cluster_sequence_counts = (
            pd.Series(labels)
            .groupby(labels)
            .size()
            .rename("n_sequences_in_cluster")
        )
        total_cluster_observations = (
            raw.groupby("cluster")
            .size()
            .rename("total_raw_code_observations_in_cluster")
        )
        raw_observation_counts = (
            raw.groupby(["cluster", "code"])
            .size()
            .rename("raw_observation_count")
        )
        sequence_counts = (
            raw.drop_duplicates(["cluster", "code", "id"])
            .groupby(["cluster", "code"])
            .size()
            .rename("sequence_count_with_code")
        )

        result = (
            pd.concat([raw_observation_counts, sequence_counts], axis=1)
            .reset_index()
            .merge(
                cluster_sequence_counts.reset_index(name="n_sequences_in_cluster"),
                on="cluster",
                how="left",
            )
            .merge(
                total_cluster_observations.reset_index(),
                on="cluster",
                how="left",
            )
        )
        result["long_name"] = result["code"].map(code_name_mapper.rename_state)
        result["raw_observation_relative_within_cluster"] = (
            result["raw_observation_count"]
            / result["total_raw_code_observations_in_cluster"]
        )
        result["raw_observation_percent_within_cluster"] = (
            result["raw_observation_relative_within_cluster"] * 100
        )
        result["sequence_relative_with_code"] = (
            result["sequence_count_with_code"]
            / result["n_sequences_in_cluster"]
        )
        result["sequence_percent_with_code"] = (
            result["sequence_relative_with_code"] * 100
        )

        return (
            result[output_columns]
            .sort_values(
                [
                    "cluster",
                    "raw_observation_count",
                    "sequence_count_with_code",
                    "code",
                ],
                ascending=[True, False, False, True],
            )
            .reset_index(drop=True)
        )

    def transition_table(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
    ) -> pd.DataFrame:
        rows = []

        for sequence_id, seq in sequences.items():
            cluster = labels.loc[sequence_id]

            for current_state, next_state in zip(seq[:-1], seq[1:]):
                rows.append(
                    {
                        "id": sequence_id,
                        "cluster": cluster,
                        "from_state": current_state,
                        "to_state": next_state,
                    }
                )

        transitions = pd.DataFrame(rows)

        if transitions.empty:
            return transitions

        return (
            transitions.groupby(["cluster", "from_state", "to_state"], as_index=False)
            .size()
            .sort_values(["cluster", "size"], ascending=[True, False])
        )

    def prototypical_sequences(
        self,
        sequences: Dict[str, List[str]],
        labels: pd.Series,
        distance_matrix: pd.DataFrame,
        filenames: Optional[Dict[str, str]] = None,
        code_name_mapper: Optional[CodeNameMapper] = None,
    ) -> pd.DataFrame:
        """
        Return all within-cluster medoids.

        A prototype is the observed sequence whose sum of distances to all
        other sequences in its cluster is minimal. If several sequences share
        the same minimum, all tied sequences are returned.
        """
        aligned_labels = self._align_labels(distance_matrix, labels)
        filenames = filenames or {}
        code_name_mapper = code_name_mapper or CodeNameMapper(self.config)
        rows = []

        for cluster in self._sorted_cluster_labels(aligned_labels):
            sequence_ids = aligned_labels[aligned_labels == cluster].index.tolist()
            within_cluster = distance_matrix.loc[sequence_ids, sequence_ids]
            total_distances = within_cluster.sum(axis=1)
            min_total_distance = float(total_distances.min())
            tied_ids = total_distances[
                np.isclose(total_distances, min_total_distance)
            ].index.tolist()

            for sequence_id in tied_ids:
                sequence = sequences[sequence_id]
                distances_to_prototype = within_cluster[sequence_id]
                max_distance_to_prototype = float(distances_to_prototype.max())
                farthest_ids = distances_to_prototype[
                    np.isclose(distances_to_prototype, max_distance_to_prototype)
                ].index.tolist()
                mean_distance = (
                    0.0
                    if len(sequence_ids) == 1
                    else float(
                        total_distances.loc[sequence_id]
                        / (len(sequence_ids) - 1)
                    )
                )

                rows.append(
                    {
                        "cluster": cluster,
                        "id": sequence_id,
                        "filename": filenames.get(sequence_id, ""),
                        "n_sequences_in_cluster": len(sequence_ids),
                        "n_steps": len(sequence),
                        "total_distance_to_cluster": float(
                            total_distances.loc[sequence_id]
                        ),
                        "mean_distance_to_other_cluster_sequences": mean_distance,
                        "tie_size": len(tied_ids),
                        "sequence_codes": " -> ".join(sequence),
                        "sequence_long_names": " -> ".join(
                            code_name_mapper.rename_state(state)
                            for state in sequence
                        ),
                        "farthest_distance_to_prototype": max_distance_to_prototype,
                        "farthest_tie_size": len(farthest_ids),
                        "farthest_ids": " || ".join(farthest_ids),
                        "farthest_filenames": " || ".join(
                            filenames.get(farthest_id, "")
                            for farthest_id in farthest_ids
                        ),
                        "farthest_sequence_codes": " || ".join(
                            self._format_sequence(sequences[farthest_id])
                            for farthest_id in farthest_ids
                        ),
                        "farthest_sequence_long_names": " || ".join(
                            self._format_sequence_long_names(
                                sequences[farthest_id],
                                code_name_mapper,
                            )
                            for farthest_id in farthest_ids
                        ),
                    }
                )

        return pd.DataFrame(rows)

    def prototypical_sequence_steps(
        self,
        prototypes: pd.DataFrame,
        sequences: Dict[str, List[str]],
        code_name_mapper: Optional[CodeNameMapper] = None,
    ) -> pd.DataFrame:
        code_name_mapper = code_name_mapper or CodeNameMapper(self.config)
        rows = []

        for prototype in prototypes.itertuples(index=False):
            for step, state in enumerate(sequences[prototype.id], start=1):
                rows.append(
                    {
                        "cluster": prototype.cluster,
                        "id": prototype.id,
                        "filename": prototype.filename,
                        "step": step,
                        "code": state,
                        "long_name": code_name_mapper.rename_state(state),
                    }
                )

        return pd.DataFrame(rows)

    def distances_to_prototypes(
        self,
        labels: pd.Series,
        distance_matrix: pd.DataFrame,
        prototypes: pd.DataFrame,
        filenames: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        aligned_labels = self._align_labels(distance_matrix, labels)
        filenames = filenames or {}
        rows = []

        for prototype in prototypes.itertuples(index=False):
            sequence_ids = aligned_labels[
                aligned_labels == prototype.cluster
            ].index.tolist()

            for sequence_id in sequence_ids:
                rows.append(
                    {
                        "cluster": prototype.cluster,
                        "id": sequence_id,
                        "filename": filenames.get(sequence_id, ""),
                        "prototype_id": prototype.id,
                        "prototype_filename": prototype.filename,
                        "distance_to_prototype": float(
                            distance_matrix.loc[sequence_id, prototype.id]
                        ),
                        "is_prototype": sequence_id == prototype.id,
                    }
                )

        result = pd.DataFrame(rows)

        if result.empty:
            return result

        return result.sort_values(
            ["cluster", "prototype_id", "distance_to_prototype", "id"],
            ascending=[True, True, True, True],
        ).reset_index(drop=True)

    def _align_labels(
        self,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
    ) -> pd.Series:
        aligned = labels.reindex(distance_matrix.index)

        if aligned.isna().any():
            missing = aligned[aligned.isna()].index.tolist()
            raise ValueError(f"Missing cluster labels for sequences: {missing}")

        missing_sequences = [
            sequence_id
            for sequence_id in aligned.index
            if sequence_id not in distance_matrix.columns
        ]
        if missing_sequences:
            raise ValueError(
                "Distance matrix columns are missing sequences: "
                f"{missing_sequences}"
            )

        return aligned

    @staticmethod
    def _sorted_cluster_labels(labels: pd.Series) -> list:
        values = list(pd.unique(labels))
        try:
            return sorted(values)
        except TypeError:
            return sorted(values, key=lambda value: str(value))

    @staticmethod
    def _format_sequence(sequence: List[str]) -> str:
        return " -> ".join(sequence)

    @staticmethod
    def _state_components(state: str) -> List[str]:
        return [
            component.strip()
            for component in str(state).split("|")
            if component.strip()
        ]

    @staticmethod
    def _format_sequence_long_names(
        sequence: List[str],
        code_name_mapper: CodeNameMapper,
    ) -> str:
        return " -> ".join(
            code_name_mapper.rename_state(state)
            for state in sequence
        )
