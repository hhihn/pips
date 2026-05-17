from typing import Optional

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import linkage, fcluster
from scipy.spatial.distance import squareform

from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.manifold import MDS

from OMAConfig import OMAConfig


# ---------------------------------------------------------------------
# Clustering
# ---------------------------------------------------------------------


class SequenceClusterer:
    def __init__(self, config: OMAConfig):
        self.config = config

    def choose_number_of_clusters(
        self,
        distance_matrix: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Uses the pseudo-F statistic as the primary stopping rule on the
        precomputed OMA distance matrix. Silhouette scores are retained as a
        diagnostic metric.

        Note:
        Ward linkage is not appropriate directly on a precomputed distance
        matrix in sklearn. For true distance-based clustering, average or
        complete linkage is more appropriate. Ward can be approximated after
        embedding the distance matrix into Euclidean space via MDS.
        """
        results = []

        n_sequences = distance_matrix.shape[0]
        max_clusters = min(self.config.max_clusters, n_sequences - 1)

        if self.config.min_clusters > max_clusters:
            raise ValueError(
                "Cluster search range is empty. Pseudo-F and silhouette "
                "selection require at least three sequences and k < n."
            )

        rng = np.random.default_rng(self.config.random_state)

        for k in range(
            self.config.min_clusters,
            max_clusters + 1,
        ):
            labels = self.cluster_with_precomputed_distance(distance_matrix, k)
            score = silhouette_score(
                distance_matrix.values,
                labels,
                metric="precomputed",
            )
            pseudo_f_stats = self.pseudo_f_statistic(distance_matrix, labels)
            pseudo_f_p_value = self.pseudo_f_permutation_p_value(
                distance_matrix,
                labels,
                n_permutations=self.config.pseudo_f_permutations,
                rng=rng,
            )

            results.append(
                {
                    "n_clusters": k,
                    "silhouette_score": score,
                    **pseudo_f_stats,
                    "pseudo_f_p_value": pseudo_f_p_value,
                    "pseudo_f_permutations": self.config.pseudo_f_permutations,
                }
            )

        return pd.DataFrame(results).sort_values(
            ["pseudo_f_score", "silhouette_score"],
            ascending=[False, False],
            na_position="last",
        ).reset_index(drop=True)

    def pseudo_f_statistic(
        self,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
    ) -> dict:
        """
        Calculate the distance-matrix pseudo-F statistic.

        The sums of squares use the discrepancy-analysis convention for
        pairwise distances: sum(D^2) / (2n).
        """
        squared_distances = self._squared_distances(distance_matrix)
        aligned_labels = self._align_labels(distance_matrix, labels)

        return self._pseudo_f_from_squared_distances(
            squared_distances,
            aligned_labels.to_numpy(),
        )

    def pseudo_f_permutation_p_value(
        self,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
        n_permutations: Optional[int] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> float:
        """
        Estimate a one-sided permutation p-value for the observed pseudo-F.

        Labels are shuffled while preserving the number and size of clusters.
        """
        permutations = (
            self.config.pseudo_f_permutations
            if n_permutations is None
            else n_permutations
        )

        if permutations < 0:
            raise ValueError("n_permutations must be non-negative.")

        squared_distances = self._squared_distances(distance_matrix)
        aligned_labels = self._align_labels(distance_matrix, labels)
        label_values = aligned_labels.to_numpy()
        observed = self._pseudo_f_from_squared_distances(
            squared_distances,
            label_values,
        )["pseudo_f_score"]

        random_generator = rng or np.random.default_rng(self.config.random_state)
        return self._permutation_p_value_from_squared_distances(
            squared_distances,
            label_values,
            observed_score=observed,
            n_permutations=permutations,
            rng=random_generator,
        )

    def pairwise_permanova(
        self,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
        n_permutations: Optional[int] = None,
        alpha: Optional[float] = None,
        rng: Optional[np.random.Generator] = None,
    ) -> pd.DataFrame:
        """
        Run pairwise PERMANOVA-style tests between cluster pairs.

        Each pair is evaluated by subsetting the OMA distance matrix to the
        two clusters and calculating a two-group pseudo-F statistic. Raw
        permutation p-values are adjusted with Bonferroni correction across
        all pairwise tests in this clustering solution.
        """
        permutations = self._resolve_pairwise_permutations(n_permutations)
        significance_alpha = (
            self.config.pairwise_permanova_alpha if alpha is None else alpha
        )

        if not 0 <= significance_alpha <= 1:
            raise ValueError("alpha must be between 0 and 1.")

        squared_distances = self._squared_distances(distance_matrix)
        aligned_labels = self._align_labels(distance_matrix, labels)
        unique_labels = self._sorted_cluster_labels(aligned_labels)
        output_columns = [
            "cluster_a",
            "cluster_b",
            "n_a",
            "n_b",
            "n_total",
            "pseudo_f_score",
            "sst",
            "ssw",
            "ssb",
            "p_value",
            "p_value_adjusted",
            "p_adjust_method",
            "significant",
            "permutations",
        ]

        if len(unique_labels) < 2:
            return pd.DataFrame(columns=output_columns)

        random_generator = rng or np.random.default_rng(self.config.random_state)
        rows = []

        for i, cluster_a in enumerate(unique_labels[:-1]):
            for cluster_b in unique_labels[i + 1 :]:
                pair_mask = aligned_labels.isin([cluster_a, cluster_b]).to_numpy()
                positions = np.flatnonzero(pair_mask)
                pair_labels = aligned_labels.iloc[positions].to_numpy()
                pair_squared_distances = squared_distances[
                    np.ix_(positions, positions)
                ]

                if len(pd.unique(pair_labels)) >= len(pair_labels):
                    stats = self._undefined_pseudo_f_from_squared_distances(
                        pair_squared_distances,
                        pair_labels,
                    )
                    p_value = float("nan")
                else:
                    stats = self._pseudo_f_from_squared_distances(
                        pair_squared_distances,
                        pair_labels,
                    )
                    p_value = self._permutation_p_value_from_squared_distances(
                        pair_squared_distances,
                        pair_labels,
                        observed_score=stats["pseudo_f_score"],
                        n_permutations=permutations,
                        rng=random_generator,
                    )

                n_a = int(np.sum(pair_labels == cluster_a))
                n_b = int(np.sum(pair_labels == cluster_b))

                rows.append(
                    {
                        "cluster_a": cluster_a,
                        "cluster_b": cluster_b,
                        "n_a": n_a,
                        "n_b": n_b,
                        "n_total": n_a + n_b,
                        **stats,
                        "p_value": p_value,
                    }
                )

        results = pd.DataFrame(rows)
        n_tests = len(results)
        results["p_value_adjusted"] = (results["p_value"] * n_tests).clip(
            upper=1.0
        )
        results["p_adjust_method"] = "bonferroni"
        results["significant"] = (
            results["p_value_adjusted"] < significance_alpha
        ).fillna(False)
        results["permutations"] = permutations

        return results[output_columns]

    def cluster_with_precomputed_distance(
        self,
        distance_matrix: pd.DataFrame,
        n_clusters: int,
    ) -> pd.Series:
        model = AgglomerativeClustering(
            n_clusters=n_clusters,
            metric="precomputed",
            linkage=self.config.clustering_method,
        )

        labels = model.fit_predict(distance_matrix.values)

        return pd.Series(
            labels + 1,
            index=distance_matrix.index,
            name="cluster",
        )

    def _squared_distances(self, distance_matrix: pd.DataFrame) -> np.ndarray:
        values = distance_matrix.to_numpy(dtype=float)

        if values.ndim != 2 or values.shape[0] != values.shape[1]:
            raise ValueError("distance_matrix must be a square matrix.")

        if not distance_matrix.index.equals(distance_matrix.columns):
            raise ValueError(
                "distance_matrix index and columns must contain the same "
                "sequence ids in the same order."
            )

        if not np.all(np.isfinite(values)):
            raise ValueError("distance_matrix must contain only finite values.")

        if not np.allclose(values, values.T):
            raise ValueError("distance_matrix must be symmetric.")

        if not np.allclose(np.diag(values), 0.0):
            raise ValueError("distance_matrix diagonal must be zero.")

        return values**2

    def _align_labels(
        self,
        distance_matrix: pd.DataFrame,
        labels: pd.Series,
    ) -> pd.Series:
        if isinstance(labels, pd.Series):
            aligned = labels.reindex(distance_matrix.index)
        else:
            aligned = pd.Series(
                labels,
                index=distance_matrix.index,
                name="cluster",
            )

        if len(aligned) != distance_matrix.shape[0]:
            raise ValueError("labels must contain one label per sequence.")

        if aligned.isna().any():
            missing = aligned[aligned.isna()].index.tolist()
            raise ValueError(f"Missing cluster labels for sequences: {missing}")

        return aligned

    def _sorted_cluster_labels(self, labels: pd.Series) -> list:
        values = list(pd.unique(labels))
        try:
            return sorted(values)
        except TypeError:
            return sorted(values, key=lambda value: str(value))

    def _resolve_pairwise_permutations(
        self,
        n_permutations: Optional[int],
    ) -> int:
        if n_permutations is not None:
            permutations = n_permutations
        elif self.config.pairwise_permanova_permutations is not None:
            permutations = self.config.pairwise_permanova_permutations
        else:
            permutations = self.config.pseudo_f_permutations

        if permutations < 0:
            raise ValueError("n_permutations must be non-negative.")

        return permutations

    def _permutation_p_value_from_squared_distances(
        self,
        squared_distances: np.ndarray,
        labels: np.ndarray,
        observed_score: float,
        n_permutations: int,
        rng: np.random.Generator,
    ) -> float:
        if n_permutations == 0 or np.isnan(observed_score):
            return float("nan")

        count_at_least_observed = 0

        for _ in range(n_permutations):
            permuted_labels = rng.permutation(labels)
            permuted_score = self._pseudo_f_from_squared_distances(
                squared_distances,
                permuted_labels,
            )["pseudo_f_score"]

            if permuted_score >= observed_score:
                count_at_least_observed += 1

        return float((count_at_least_observed + 1) / (n_permutations + 1))

    def _undefined_pseudo_f_from_squared_distances(
        self,
        squared_distances: np.ndarray,
        labels: np.ndarray,
    ) -> dict:
        n_sequences = squared_distances.shape[0]
        sst = float(squared_distances.sum() / (2 * n_sequences))
        ssw = 0.0

        for label in pd.unique(labels):
            positions = np.flatnonzero(labels == label)
            cluster_size = positions.size
            ssw += float(
                squared_distances[np.ix_(positions, positions)].sum()
                / (2 * cluster_size)
            )

        ssb = sst - ssw
        if np.isclose(ssb, 0.0):
            ssb = 0.0

        return {
            "pseudo_f_score": float("nan"),
            "sst": float(sst),
            "ssw": float(ssw),
            "ssb": float(ssb),
        }

    def _pseudo_f_from_squared_distances(
        self,
        squared_distances: np.ndarray,
        labels: np.ndarray,
    ) -> dict:
        n_sequences = squared_distances.shape[0]
        unique_labels = pd.unique(labels)
        n_clusters = len(unique_labels)

        if n_clusters < 2:
            raise ValueError("Pseudo-F requires at least two clusters.")

        if n_clusters >= n_sequences:
            raise ValueError("Pseudo-F requires fewer clusters than sequences.")

        sst = float(squared_distances.sum() / (2 * n_sequences))
        ssw = 0.0

        for label in unique_labels:
            positions = np.flatnonzero(labels == label)
            cluster_size = positions.size
            ssw += float(
                squared_distances[np.ix_(positions, positions)].sum()
                / (2 * cluster_size)
            )

        ssb = sst - ssw
        if np.isclose(ssb, 0.0):
            ssb = 0.0

        between_mean_square = ssb / (n_clusters - 1)
        within_mean_square = ssw / (n_sequences - n_clusters)

        if np.isclose(within_mean_square, 0.0):
            pseudo_f = np.inf if between_mean_square > 0 else np.nan
        else:
            pseudo_f = between_mean_square / within_mean_square

        return {
            "pseudo_f_score": float(pseudo_f),
            "sst": float(sst),
            "ssw": float(ssw),
            "ssb": float(ssb),
        }

    def cluster_with_scipy(
        self,
        distance_matrix: pd.DataFrame,
        n_clusters: int,
        method: str = "average",
    ) -> pd.Series:
        condensed = squareform(distance_matrix.values, checks=False)
        z = linkage(condensed, method=method)
        labels = fcluster(z, t=n_clusters, criterion="maxclust")

        return pd.Series(
            labels,
            index=distance_matrix.index,
            name="cluster",
        )

    def cluster_with_ward_after_mds(
        self,
        distance_matrix: pd.DataFrame,
        n_clusters: int,
        n_components: int = 5,
    ) -> pd.Series:
        """
        Approximate Ward clustering by embedding OMA distances into a
        Euclidean space using MDS first.

        This is useful if you specifically want a Ward-like solution.
        """
        mds = MDS(
            n_components=n_components,
            dissimilarity="precomputed",
            random_state=self.config.random_state,
            normalized_stress="auto",
        )

        coordinates = mds.fit_transform(distance_matrix.values)

        model = AgglomerativeClustering(
            n_clusters=n_clusters,
            linkage="ward",
        )

        labels = model.fit_predict(coordinates)

        return pd.Series(
            labels + 1,
            index=distance_matrix.index,
            name="cluster",
        )
