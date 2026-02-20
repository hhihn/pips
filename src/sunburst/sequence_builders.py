from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.sunburst.bundling import BundleStrategy
from src.sunburst.context import AnalysisContext
from src.sunburst.helper import (
    normalize_code,
    parse_time_to_seconds,
    pick_group_token_from_first_n,
    label_for_token,
)
from src.sunburst.postprocessing import postprocess_sequence


@dataclass
class PartsSequenceBuilder:
    context: AnalysisContext
    bundle_strategy: BundleStrategy

    def build(
        self,
        df: pd.DataFrame,
        start_lookahead_n: int = 12,
    ) -> tuple[list[list[str]], pd.DataFrame]:
        d = df.copy()
        d["code"] = d["Sequence_Code"].map(normalize_code)
        d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
        d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
        d = d[d["code"].isin(self.context.allowed_codes)].copy()

        sequences_labels: list[list[str]] = []
        per_path_rows: list[dict[str, Any]] = []
        group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]

        for key, g in d.groupby(group_cols, sort=True):
            if isinstance(key, tuple):
                filename, pid = key
            else:
                filename, pid = key, ""

            g_sorted = g.copy()
            g_sorted["code_priority"] = g_sorted["code"].map(
                lambda c: self.context.code_to_prio.get(c, (999, 999))
            )
            g_sorted = g_sorted.sort_values(
                by=["start_s", "end_s", "code_priority"]
            ).drop("code_priority", axis=1)

            bundles = []
            for bundle_group in self.bundle_strategy.build(g_sorted):
                bundles.append(
                    {
                        "start_s": float(bundle_group["start_s"].min()),
                        "end_s": float(bundle_group["end_s"].max()),
                        "codes": bundle_group["code"].tolist(),
                        "data": bundle_group.copy(),
                    }
                )

            bundles.sort(key=lambda b: (b["start_s"], b["end_s"]))

            n_bundles = len(bundles)
            if n_bundles == 0:
                innen_tok = self.context.placeholder_other
                mitte_tok = self.context.placeholder_other
                aussen_tok = self.context.placeholder_other
                aussenring_tok = self.context.placeholder_other
                parts_bundles = []
            else:
                bundles = bundles[: max(4, start_lookahead_n)]
                n_bundles = len(bundles)
                base = n_bundles // 4
                rem = n_bundles % 4
                sizes = [base + (1 if i < rem else 0) for i in range(4)]

                parts_bundles = []
                idx0 = 0
                for sz in sizes:
                    bundle_subset = bundles[idx0 : idx0 + sz]
                    dfs = [b["data"] for b in bundle_subset]
                    combined_df = (
                        pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
                    )
                    parts_bundles.append(combined_df)
                    idx0 += sz

                innen_df, mitte_df, aussen_df, aussenring_df = parts_bundles

                def pick_with_adjacent(parts_list, idx, allowed_codes):
                    n_parts = len(parts_list)
                    for dist in range(n_parts):
                        candidates = []
                        if dist == 0:
                            candidates = [idx]
                        else:
                            if idx - dist >= 0:
                                candidates.append(idx - dist)
                            if idx + dist < n_parts:
                                candidates.append(idx + dist)
                        for j in candidates:
                            tok = pick_group_token_from_first_n(
                                parts_list[j],
                                allowed_codes,
                                combo_time_match_mode=self.bundle_strategy.mode,
                                context=self.context,
                            )
                            if tok != [self.context.placeholder_other]:
                                return tok
                    return [self.context.placeholder_other]

                parts_list = [innen_df, mitte_df, aussen_df, aussenring_df]
                innen_tok = pick_with_adjacent(
                    parts_list, 0, self.context.group_name_to_codes["innen"]
                )
                mitte_tok = pick_with_adjacent(
                    parts_list, 1, self.context.group_name_to_codes["mitte"]
                )
                aussen_tok = pick_with_adjacent(
                    parts_list, 2, self.context.group_name_to_codes["aussen"]
                )
                aussenring_tok = pick_with_adjacent(
                    parts_list, 3, self.context.group_name_to_codes["aussenring"]
                )

            seq_tokens = innen_tok + mitte_tok + aussen_tok + aussenring_tok
            seq_tokens = postprocess_sequence(
                seq_tokens,
                context=self.context,
                combo_time_match_mode=self.bundle_strategy.mode,
            )
            seq_labels = [label_for_token(t, context=self.context) for t in seq_tokens]
            sequences_labels.append(seq_labels)

            per_path_rows.append(
                {
                    "Filename": filename,
                    "id": pid,
                    "start_group": label_for_token(
                        innen_tok[0] if innen_tok else self.context.placeholder_other,
                        context=self.context,
                    ),
                    "sequence_tokens": " -> ".join(seq_tokens),
                    "sequence_labels": " -> ".join(seq_labels),
                    "innen_token": str(innen_tok),
                    "mitte_token": str(mitte_tok),
                    "aussen_token": str(aussen_tok),
                    "aussenring_token": str(aussenring_tok),
                    "n_bundles": len(bundles) if n_bundles > 0 else 0,
                    "bundle_sizes": "|".join(map(str, [len(df) for df in parts_bundles]))
                    if parts_bundles
                    else "0|0|0|0",
                }
            )

        per_path_table = pd.DataFrame(per_path_rows)
        return sequences_labels, per_path_table


@dataclass
class AllCodesSequenceBuilder:
    context: AnalysisContext

    def build(
        self,
        df: pd.DataFrame,
        start_lookahead_n: int = 12,
        combo_time_match_mode: str = "exact",
    ) -> tuple[list[list[str]], pd.DataFrame]:
        d = df.copy()
        d["code"] = d["Sequence_Code"].map(normalize_code)
        d["start_s"] = d["Sequence_Start"].map(parse_time_to_seconds)
        d["end_s"] = d["Sequence_End"].map(parse_time_to_seconds)
        d = d[d["code"].isin(self.context.allowed_codes)].copy()
        sequences_labels: list[list[str]] = []
        per_path_rows: list[dict[str, Any]] = []
        group_cols = ["Filename", "id"] if "id" in d.columns else ["Filename"]

        for key, g in d.groupby(group_cols, sort=True):
            if isinstance(key, tuple):
                filename, pid = key
            else:
                filename, pid = key, ""

            g_sorted = g.copy()
            g_sorted["code_priority"] = g_sorted["code"].map(
                lambda c: self.context.code_to_prio.get(c, (999, 999))
            )
            g_sorted = g_sorted.sort_values(
                by=["start_s", "end_s", "code_priority"]
            ).drop("code_priority", axis=1)

            first_n = g_sorted.head(max(4, start_lookahead_n)).copy()

            if first_n.empty:
                seq_tokens = [self.context.placeholder_other]
            else:
                all_codes = sorted(first_n["code"].unique().tolist())
                seq_tokens = all_codes if all_codes else [self.context.placeholder_other]

            seq_tokens = postprocess_sequence(
                seq_tokens,
                context=self.context,
                combo_time_match_mode=combo_time_match_mode,
            )
            seq_labels = [label_for_token(t, context=self.context) for t in seq_tokens]
            sequences_labels.append(seq_labels)

            per_path_rows.append(
                {
                    "Filename": filename,
                    "id": pid,
                    "start_group": "All Codes Together",
                    "sequence_tokens": " -> ".join(seq_tokens),
                    "sequence_labels": " -> ".join(seq_labels),
                    "all_codes_token": str(seq_tokens),
                    "n_events": len(first_n),
                }
            )

        per_path_table = pd.DataFrame(per_path_rows)
        return sequences_labels, per_path_table
