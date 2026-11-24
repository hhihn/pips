from __future__ import annotations

import math
from itertools import combinations
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from scipy.stats import chi2_contingency, fisher_exact

from CodeNormalizer import normalize_code_for_lookup
from OMAConfig import OMAConfig
from SequenceClusterer import SequenceClusterer


class CareTypeAnalyzer:
    def __init__(self, config: OMAConfig):
        self.config = config

    def sequence_care_types(self, df: pd.DataFrame) -> pd.DataFrame:
        care_type_codes = self._normalized_care_type_codes()
        if not care_type_codes:
            return pd.DataFrame(
                columns=[
                    "id",
                    "filename",
                    "care_type",
                    "care_type_status",
                    "matched_care_codes",
                    "matched_care_labels",
                    "n_matched_care_types",
                ]
            )

        code_order = {code: order for order, code in enumerate(care_type_codes)}
        rows = []

        for sequence_id, group in df.groupby(self.config.id_col, sort=False):
            normalized_codes = (
                group[self.config.code_col]
                .dropna()
                .map(normalize_code_for_lookup)
                .tolist()
            )
            matched_codes = sorted(
                {code for code in normalized_codes if code in care_type_codes},
                key=lambda code: code_order[code],
            )
            matched_labels = [care_type_codes[code] for code in matched_codes]

            if len(matched_labels) == 0:
                care_type = self.config.care_type_missing_label
                status = "missing"
            elif len(matched_labels) == 1:
                care_type = matched_labels[0]
                status = "clean"
            else:
                care_type = self.config.care_type_mixed_label
                status = "mixed"

            rows.append(
                {
                    "id": str(sequence_id),
                    "filename": self._filename_value(group),
                    "care_type": care_type,
                    "care_type_status": status,
                    "matched_care_codes": " | ".join(matched_codes),
                    "matched_care_labels": " | ".join(matched_labels),
                    "n_matched_care_types": len(matched_labels),
                }
            )

        result = pd.DataFrame(rows)
        missing_ids = result.loc[
            result["care_type_status"] == "missing",
            "id",
        ].tolist()
        if missing_ids:
            raise ValueError(
                "Care type markers are missing for sequence ids: "
                f"{missing_ids}"
            )

        return result

    def distance_group_comparison(
        self,
        distance_matrix: pd.DataFrame,
        care_types: pd.DataFrame,
        clusterer: SequenceClusterer,
    ) -> pd.DataFrame:
        clean = self._aligned_clean_care_types(distance_matrix.index, care_types)
        labels = clean["care_type"]
        unique_labels = self._sorted_values(labels)
        output_columns = [
            "comparison",
            "n_total",
            "n_groups",
            "groups",
            "n_mixed_excluded",
            "pseudo_f_score",
            "sst",
            "ssw",
            "ssb",
            "r_squared",
            "p_value",
            "permutations",
        ]

        if len(unique_labels) < 2:
            return pd.DataFrame(
                [
                    {
                        "comparison": "care_type_permanova",
                        "n_total": len(clean),
                        "n_groups": len(unique_labels),
                        "groups": " | ".join(map(str, unique_labels)),
                        "n_mixed_excluded": self._excluded_count(
                            care_types,
                            "mixed",
                        ),
                        "pseudo_f_score": np.nan,
                        "sst": np.nan,
                        "ssw": np.nan,
                        "ssb": np.nan,
                        "r_squared": np.nan,
                        "p_value": np.nan,
                        "permutations": self._care_type_permutations(),
                    }
                ],
                columns=output_columns,
            )

        subset_distance_matrix = distance_matrix.loc[clean.index, clean.index]
        stats = clusterer.pseudo_f_statistic(subset_distance_matrix, labels)
        permutations = self._care_type_permutations()
        p_value = clusterer.pseudo_f_permutation_p_value(
            subset_distance_matrix,
            labels,
            n_permutations=permutations,
        )
        r_squared = (
            np.nan
            if np.isclose(stats["sst"], 0.0)
            else stats["ssb"] / stats["sst"]
        )

        row = {
            "comparison": "care_type_permanova",
            "n_total": len(clean),
            "n_groups": len(unique_labels),
            "groups": " | ".join(map(str, unique_labels)),
            "n_mixed_excluded": self._excluded_count(care_types, "mixed"),
            **stats,
            "r_squared": float(r_squared),
            "p_value": p_value,
            "permutations": permutations,
        }
        for care_type, count in labels.value_counts().sort_index().items():
            row[f"n_{care_type}"] = int(count)

        return pd.DataFrame([row])

    def distance_summary(
        self,
        distance_matrix: pd.DataFrame,
        care_types: pd.DataFrame,
    ) -> pd.DataFrame:
        clean = self._aligned_clean_care_types(distance_matrix.index, care_types)
        rows = []

        for care_type in self._sorted_values(clean["care_type"]):
            ids = clean.index[clean["care_type"] == care_type].tolist()
            values = self._within_pair_distances(distance_matrix, ids)
            rows.append(
                {
                    "comparison": "within",
                    "care_type_a": care_type,
                    "care_type_b": care_type,
                    "n_sequences_a": len(ids),
                    "n_sequences_b": len(ids),
                    **self._describe_distances(values),
                }
            )

        for care_type_a, care_type_b in combinations(
            self._sorted_values(clean["care_type"]),
            2,
        ):
            ids_a = clean.index[clean["care_type"] == care_type_a].tolist()
            ids_b = clean.index[clean["care_type"] == care_type_b].tolist()
            values = distance_matrix.loc[ids_a, ids_b].to_numpy(dtype=float).ravel()
            rows.append(
                {
                    "comparison": "between",
                    "care_type_a": care_type_a,
                    "care_type_b": care_type_b,
                    "n_sequences_a": len(ids_a),
                    "n_sequences_b": len(ids_b),
                    **self._describe_distances(values),
                }
            )

        return pd.DataFrame(rows)

    def cluster_crosstab(
        self,
        care_types: pd.DataFrame,
        labels: pd.Series,
    ) -> pd.DataFrame:
        aligned = self._align_care_types_to_labels(care_types, labels)
        table = pd.crosstab(aligned["care_type"], aligned["cluster"])
        table = table.rename(columns=lambda cluster: f"cluster_{cluster}")
        table["total"] = table.sum(axis=1)

        return table.reset_index()

    def cluster_association(
        self,
        care_types: pd.DataFrame,
        labels: pd.Series,
    ) -> pd.DataFrame:
        aligned = self._align_care_types_to_labels(care_types, labels)
        clean = aligned[aligned["care_type_status"] == "clean"].copy()
        table = pd.crosstab(clean["care_type"], clean["cluster"])
        output_columns = [
            "test",
            "n_total",
            "n_rows",
            "n_columns",
            "min_expected_count",
            "chi_square",
            "degrees_of_freedom",
            "p_value",
            "odds_ratio",
            "cramers_v",
            "n_mixed_excluded",
        ]

        if table.shape[0] < 2 or table.shape[1] < 2:
            return pd.DataFrame(
                [
                    {
                        "test": "not_run_insufficient_table",
                        "n_total": int(table.to_numpy().sum()),
                        "n_rows": table.shape[0],
                        "n_columns": table.shape[1],
                        "min_expected_count": np.nan,
                        "chi_square": np.nan,
                        "degrees_of_freedom": np.nan,
                        "p_value": np.nan,
                        "odds_ratio": np.nan,
                        "cramers_v": np.nan,
                        "n_mixed_excluded": self._excluded_count(
                            care_types,
                            "mixed",
                        ),
                    }
                ],
                columns=output_columns,
            )

        chi_square, chi_p_value, dof, expected = chi2_contingency(
            table,
            correction=False,
        )
        n_total = int(table.to_numpy().sum())
        cramers_v = self._cramers_v(chi_square, n_total, table.shape)
        min_expected = float(np.min(expected))
        odds_ratio = np.nan

        if table.shape == (2, 2):
            odds_ratio = self._odds_ratio(table.to_numpy(dtype=float))
            if min_expected < 5:
                test = "fisher_exact"
                odds_ratio, p_value = fisher_exact(table.to_numpy())
                chi_square_for_output = chi_square
                dof_for_output = dof
            else:
                test = "chi_square"
                p_value = chi_p_value
                chi_square_for_output = chi_square
                dof_for_output = dof
        elif min_expected >= 5:
            test = "chi_square"
            p_value = chi_p_value
            chi_square_for_output = chi_square
            dof_for_output = dof
        else:
            test = "not_run_expected_counts_lt_5"
            p_value = np.nan
            chi_square_for_output = chi_square
            dof_for_output = dof

        return pd.DataFrame(
            [
                {
                    "test": test,
                    "n_total": n_total,
                    "n_rows": table.shape[0],
                    "n_columns": table.shape[1],
                    "min_expected_count": min_expected,
                    "chi_square": float(chi_square_for_output),
                    "degrees_of_freedom": int(dof_for_output),
                    "p_value": float(p_value),
                    "odds_ratio": float(odds_ratio),
                    "cramers_v": cramers_v,
                    "n_mixed_excluded": self._excluded_count(
                        care_types,
                        "mixed",
                    ),
                }
            ],
            columns=output_columns,
        )

    def recommendation(
        self,
        distance_group_comparison: pd.DataFrame,
        cluster_association: pd.DataFrame,
    ) -> pd.DataFrame:
        distance_row = distance_group_comparison.iloc[0]
        association_row = cluster_association.iloc[0]

        distance_meaningful = (
            pd.notna(distance_row["p_value"])
            and distance_row["p_value"] < self.config.care_type_alpha
            and distance_row["r_squared"] >= self.config.care_type_min_r_squared
        )
        cluster_meaningful = (
            (
                pd.notna(association_row["p_value"])
                and association_row["p_value"] < self.config.care_type_alpha
            )
            or (
                pd.notna(association_row["cramers_v"])
                and association_row["cramers_v"]
                >= self.config.care_type_min_cramers_v
            )
        )
        separate_recommended = bool(distance_meaningful and cluster_meaningful)
        recommendation = (
            "run_separate_oma_as_secondary_exploratory_analysis"
            if separate_recommended
            else "keep_pooled_oma_as_primary_analysis"
        )

        return pd.DataFrame(
            [
                {
                    "recommendation": recommendation,
                    "separate_oma_recommended": separate_recommended,
                    "distance_p_value": distance_row["p_value"],
                    "distance_r_squared": distance_row["r_squared"],
                    "cluster_association_p_value": association_row["p_value"],
                    "cluster_association_cramers_v": association_row["cramers_v"],
                    "alpha": self.config.care_type_alpha,
                    "min_r_squared_for_separate_analysis": (
                        self.config.care_type_min_r_squared
                    ),
                    "min_cramers_v_for_separate_analysis": (
                        self.config.care_type_min_cramers_v
                    ),
                }
            ]
        )

    def _normalized_care_type_codes(self) -> Dict[str, str]:
        return {
            normalize_code_for_lookup(code): label
            for code, label in (self.config.care_type_codes or {}).items()
        }

    def _aligned_clean_care_types(
        self,
        sequence_ids: pd.Index,
        care_types: pd.DataFrame,
    ) -> pd.DataFrame:
        aligned = care_types.set_index("id").reindex(sequence_ids.astype(str))
        if aligned["care_type"].isna().any():
            missing = aligned[aligned["care_type"].isna()].index.tolist()
            raise ValueError(f"Missing care type rows for sequence ids: {missing}")

        return aligned[aligned["care_type_status"] == "clean"].copy()

    @staticmethod
    def _align_care_types_to_labels(
        care_types: pd.DataFrame,
        labels: pd.Series,
    ) -> pd.DataFrame:
        aligned = care_types.set_index("id").reindex(labels.index.astype(str))
        if aligned["care_type"].isna().any():
            missing = aligned[aligned["care_type"].isna()].index.tolist()
            raise ValueError(f"Missing care type rows for sequence ids: {missing}")

        aligned = aligned.copy()
        aligned["cluster"] = labels.to_numpy()
        return aligned

    def _care_type_permutations(self) -> int:
        if self.config.care_type_permutations is not None:
            return self.config.care_type_permutations

        return self.config.pseudo_f_permutations

    def _excluded_count(self, care_types: pd.DataFrame, status: str) -> int:
        return int((care_types["care_type_status"] == status).sum())

    def _filename_value(self, group: pd.DataFrame) -> str:
        if self.config.filename_col not in group.columns:
            return ""

        filenames = (
            group[self.config.filename_col]
            .dropna()
            .astype(str)
            .str.strip()
            .unique()
            .tolist()
        )
        return " | ".join(filenames)

    @staticmethod
    def _within_pair_distances(
        distance_matrix: pd.DataFrame,
        sequence_ids: List[str],
    ) -> np.ndarray:
        if len(sequence_ids) < 2:
            return np.array([], dtype=float)

        values = distance_matrix.loc[sequence_ids, sequence_ids].to_numpy(dtype=float)
        upper_triangle = np.triu_indices(len(sequence_ids), k=1)
        return values[upper_triangle]

    @staticmethod
    def _describe_distances(values: np.ndarray) -> dict:
        values = np.asarray(values, dtype=float)
        if values.size == 0:
            return {
                "n_pairs": 0,
                "mean_distance": np.nan,
                "median_distance": np.nan,
                "sd_distance": np.nan,
                "min_distance": np.nan,
                "max_distance": np.nan,
            }

        return {
            "n_pairs": int(values.size),
            "mean_distance": float(np.mean(values)),
            "median_distance": float(np.median(values)),
            "sd_distance": (
                float(np.std(values, ddof=1)) if values.size > 1 else np.nan
            ),
            "min_distance": float(np.min(values)),
            "max_distance": float(np.max(values)),
        }

    @staticmethod
    def _cramers_v(
        chi_square: float,
        n_total: int,
        shape: tuple,
    ) -> float:
        if n_total == 0:
            return np.nan

        denominator = n_total * min(shape[0] - 1, shape[1] - 1)
        if denominator <= 0:
            return np.nan

        return float(math.sqrt(chi_square / denominator))

    @staticmethod
    def _odds_ratio(values: np.ndarray) -> float:
        denominator = values[0, 1] * values[1, 0]
        if np.isclose(denominator, 0.0):
            return np.inf

        return float(values[0, 0] * values[1, 1] / denominator)

    @staticmethod
    def _sorted_values(values: pd.Series) -> List:
        unique_values = list(pd.unique(values))
        try:
            return sorted(unique_values)
        except TypeError:
            return sorted(unique_values, key=lambda value: str(value))
