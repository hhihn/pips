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
        Uses silhouette scores on the precomputed OMA distance matrix.

        Note:
        Ward linkage is not appropriate directly on a precomputed distance
        matrix in sklearn. For true distance-based clustering, average or
        complete linkage is more appropriate. Ward can be approximated after
        embedding the distance matrix into Euclidean space via MDS.
        """
        results = []

        n_sequences = distance_matrix.shape[0]

        for k in range(
            self.config.min_clusters,
            min(self.config.max_clusters, n_sequences - 1) + 1,
        ):
            labels = self.cluster_with_precomputed_distance(distance_matrix, k)
            score = silhouette_score(
                distance_matrix.values,
                labels,
                metric="precomputed",
            )

            results.append(
                {
                    "n_clusters": k,
                    "silhouette_score": score,
                }
            )

        return pd.DataFrame(results).sort_values(
            "silhouette_score",
            ascending=False,
        )

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
