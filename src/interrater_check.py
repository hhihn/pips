"""Regenerate complete care sequences and compare two raters without a gold standard."""

import argparse
import csv
from dataclasses import dataclass, field
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
from statsmodels.stats.inter_rater import cohens_kappa
from statsmodels.stats.multitest import multipletests
from scipy.stats import permutation_test

from care_overlap import export_care_sequences
from create_row_view import (
    code_prefix, time_milliseconds, merge_intervals, intersect_intervals, interval_duration,
)
from pattern_detector import PatternDetector


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config/interrater.json"
EVENT_FIELDS = [
    "video", "code", "status", "reason", "old_start_ms", "old_end_ms",
    "new_start_ms", "new_end_ms", "old_situations", "new_situations",
    "start_difference_ms", "end_difference_ms",
]
CHILD_CODES = {f"5.5.{i}" for i in range(1, 11)}
SPEECH_CODE = "5.3.1"
REPORT_TABLE_SLUGS = {
    "Code-Präsenz": "code_presence",
    "Zeitliche Ereignisübereinstimmung": "event_timing",
    "Zuordnung der Sprechintervalle": "speech_event_matching",
    "Gemeinsame Sprechzeit": "shared_speech_time_coverage",
    "Dauer der Codes": "code_durations",
}


@dataclass(frozen=True, order=True)
class Event:
    code: str
    start: int
    end: int


@dataclass
class Video:
    filename: str
    situations: dict = field(default_factory=dict)
    events: dict = field(default_factory=dict)
    duplicate_rows: int = 0


def video_id(filename):
    return Path(filename).stem.removesuffix("_IR").removesuffix("_transformed")


def excel_index(folder):
    folder = Path(folder)
    if not folder.is_dir():
        raise ValueError(f"Input directory does not exist: {folder}")
    index = {}
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {".xlsx", ".xls"} or path.name.startswith("~$"):
            continue
        key = video_id(path.name)
        if key in index:
            raise ValueError(f"Ambiguous video {key}: {index[key]} and {path}")
        index[key] = path
    return index


def pair_files(old_folder, new_folder):
    old, new = excel_index(old_folder), excel_index(new_folder)
    if not new:
        raise ValueError("No new Excel annotations found")
    missing = sorted(new.keys() - old.keys())
    if missing:
        raise ValueError(f"Missing old annotations for videos: {', '.join(missing)}")
    return [(key, old[key], new[key]) for key in sorted(new)], sorted(old.keys() - new.keys())


def read_sequences(path):
    """Load only actual care sequences, retaining each event's situation memberships."""
    videos, seen = {}, set()
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"Filename", "Situation_ID", "Child_Code", "Child_Start", "Child_End",
                    "Sequence_Code", "Sequence_Start", "Sequence_End"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for number, row in enumerate(reader, 2):
            key = video_id(row["Filename"])
            video = videos.setdefault(key, Video(row["Filename"]))
            try:
                if video.filename != row["Filename"]:
                    raise ValueError(f"Ambiguous filenames for video {key}")
                if code_prefix(row["Child_Code"]) != "6.1.1":
                    raise ValueError("Expected a 6.1.1 care situation")
                situation = (time_milliseconds(row["Child_Start"]), time_milliseconds(row["Child_End"]))
                sid = row["Situation_ID"]
                if not sid or situation[1] <= situation[0]:
                    raise ValueError("Invalid care situation")
                if sid in video.situations and video.situations[sid] != situation:
                    raise ValueError(f"Conflicting boundaries for {sid}")
                video.situations[sid] = situation
                code = code_prefix(row["Sequence_Code"])
                if not code:
                    raise ValueError("Missing numeric sequence code")
                event = Event(code, time_milliseconds(row["Sequence_Start"]), time_milliseconds(row["Sequence_End"]))
                if event.end < event.start:
                    raise ValueError("Reversed event interval")
                if min(event.end, situation[1]) <= max(event.start, situation[0]):
                    raise ValueError("Sequence event does not overlap its care situation")
                identity = (key, sid, event)
                if identity in seen:
                    video.duplicate_rows += 1
                seen.add(identity)
                video.events.setdefault(event, set()).add(sid)
            except ValueError as error:
                raise ValueError(f"{path}, CSV row {number}, {key}: {error}") from error
    return videos


def ordered_match(left, right, quality):
    """Lexicographic optimum: most chronological matches, then highest quality.

    A quality of None forbids a pair. Stable input sorting and diagonal-first
    ties make the selected alignment reproducible.
    """
    n, m = len(left), len(right)
    best = [[(0, 0) for _ in range(m + 1)] for _ in range(n + 1)]
    actions = [[0 for _ in range(m)] for _ in range(n)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            value, action = best[i + 1][j], 0
            if best[i][j + 1] > value:
                value, action = best[i][j + 1], 1
            score = quality(left[i], right[j])
            if score is not None:
                following = best[i + 1][j + 1]
                candidate = (following[0] + 1, following[1] + score)
                if candidate >= value:
                    value, action = candidate, 2
            best[i][j], actions[i][j] = value, action
    pairs, i, j = [], 0, 0
    while i < n and j < m:
        action = actions[i][j]
        if action == 2:
            pairs.append((i, j))
            i, j = i + 1, j + 1
        elif action == 0:
            i += 1
        else:
            j += 1
    return pairs


def align_situations(old, new):
    left = sorted(old.situations, key=lambda sid: (*old.situations[sid], sid))
    right = sorted(new.situations, key=lambda sid: (*new.situations[sid], sid))

    def quality(a, b):
        a0, a1 = old.situations[a]
        b0, b1 = new.situations[b]
        intersection = min(a1, b1) - max(a0, b0)
        return intersection / (max(a1, b1) - min(a0, b0)) if intersection > 0 else None

    indices = ordered_match(left, right, quality)
    matched_old, matched_new = {a for a, _ in indices}, {b for _, b in indices}
    pairs = [(left[a], right[b]) for a, b in indices]
    pairs.extend((sid, None) for i, sid in enumerate(left) if i not in matched_old)
    pairs.extend((None, sid) for i, sid in enumerate(right) if i not in matched_new)
    return sorted(pairs, key=lambda pair: (
        min(old.situations[pair[0]][0] if pair[0] else float("inf"),
            new.situations[pair[1]][0] if pair[1] else float("inf")),
        pair[0] or "", pair[1] or ""))


def presence_metrics(counts):
    """Binary agreement, kappa and nominal alpha for two complete ratings per unit."""
    both, old_only, new_only, neither = map(int, counts)
    n = both + old_only + new_only + neither
    agreement = (both + neither) / n if n else None
    expected_numerator = ((both + old_only) * (both + new_only)
                          + (new_only + neither) * (old_only + neither))
    denominator = n * n - expected_numerator
    kappa = (n * (both + neither) - expected_numerator) / denominator if denominator else None
    # Alpha pools the two raters' category frequencies and draws without
    # replacement: D_o = disagreements / n, D_e = positives * negatives / (n * (2*n - 1)).
    positives = 2 * both + old_only + new_only
    negatives = 2 * neither + old_only + new_only
    alpha_denominator = positives * negatives
    alpha = (1 - (old_only + new_only) * (2 * n - 1) / alpha_denominator
             if alpha_denominator else None)
    f1 = 2 * both / (2 * both + old_only + new_only) if both + old_only + new_only else None
    negative = (2 * neither / (2 * neither + old_only + new_only)
                if neither + old_only + new_only else None)
    return {"both_present": both, "old_only": old_only, "new_only": new_only,
            "both_absent": neither, "units": n, "agreement": agreement,
            "agreement_percent": agreement * 100 if agreement is not None else None,
            "kappa": kappa, "krippendorff_alpha": alpha, "positive_f1": f1,
            "positive_specific_agreement": f1, "negative_specific_agreement": negative,
            "kappa_status": "defined" if kappa is not None else "undefined_constant_ratings_or_no_units",
            "krippendorff_alpha_status": "defined" if alpha is not None else "undefined_constant_ratings_or_no_units",
            "positive_specific_agreement_status": "defined" if f1 is not None else "undefined_no_positive_ratings",
            "negative_specific_agreement_status": "defined" if negative is not None else "undefined_no_negative_ratings",
            "f1_status": "defined" if f1 is not None else "undefined_no_positive_ratings"}


def kappa_significance(row):
    """Statsmodels' asymptotic two-sided test of H0: kappa = 0.

    Called for final estimates only, not thousands of bootstrap replicates.
    Zero null variance has no defined normal test, even if kappa is defined.
    """
    result = {"kappa_pvalue_two_sided": None, "kappa_z_statistic": None,
              "kappa_test_status": row["kappa_status"]}
    if row["kappa"] is None:
        return result
    table = [[row["both_present"], row["old_only"]],
             [row["new_only"], row["both_absent"]]]
    with np.errstate(divide="ignore", invalid="ignore"):
        test = cohens_kappa(table)
    if not np.isfinite(test.var_kappa0) or test.var_kappa0 <= 0:
        result["kappa_test_status"] = "undefined_zero_or_nonfinite_null_variance"
        return result
    result.update(kappa_pvalue_two_sided=float(test.pvalue_two_sided),
                  kappa_z_statistic=float(test.kappa / np.sqrt(test.var_kappa0)),
                  kappa_test_status="defined")
    return result


def timing_metrics(counts):
    old, new, matched, start_error, end_error, start_squares, end_squares = map(int, counts)
    def sample_sd(total, squares):
        return (max(0, (squares - total * total / matched) / (matched - 1)) ** .5
                if matched > 1 else None)
    return {"old_events": int(old), "new_events": int(new), "matched_events": int(matched),
            "old_only": int(old - matched), "new_only": int(new - matched),
            "f1": 2 * matched / (old + new) if old + new else None,
            "mean_abs_start_error_ms": start_error / matched if matched else None,
            "mean_abs_end_error_ms": end_error / matched if matched else None,
            "sd_abs_start_error_ms": sample_sd(start_error, start_squares),
            "sd_abs_end_error_ms": sample_sd(end_error, end_squares),
            "sd_status": "defined" if matched > 1 else "undefined_fewer_than_two_matches",
            "f1_status": "defined" if old + new else "undefined_no_events"}


def presence_counts(old, new, pairs, codes, key):
    arrays = {level: np.zeros((len(codes), 4), dtype=np.int64) for level in ("video", "situation")}
    details = []
    units = [("video", "video", None, None)] + [
        ("situation", f"p{i:03d}", a, b) for i, (a, b) in enumerate(pairs, 1)]
    for level, uid, a, b in units:
        old_codes = {e.code for e, memberships in old.events.items() if level == "video" or a in memberships}
        new_codes = {e.code for e, memberships in new.events.items() if level == "video" or b in memberships}
        for i, code in enumerate(codes):
            yes_old, yes_new = code in old_codes, code in new_codes
            outcome = 0 if yes_old and yes_new else 1 if yes_old else 2 if yes_new else 3
            arrays[level][i, outcome] += 1
            details.append({"video": key, "level": level, "unit": uid, "code": code,
                            "old_situation": a, "new_situation": b,
                            "old_present": yes_old, "new_present": yes_new,
                            "outcome": ("both_present", "old_only", "new_only", "both_absent")[outcome]})
    return arrays, details


def compare_timing(old, new, pairs, codes, tolerance_ms, key):
    counts = np.zeros((len(codes), 7), dtype=np.int64)
    details = []
    allowed = {(a, b) for a, b in pairs if a is not None and b is not None}
    paired_old, paired_new = {a for a, _ in allowed}, {b for _, b in allowed}
    for index, code in enumerate(codes):
        left = sorted((e for e in old.events if e.code == code), key=lambda e: (e.start, e.end))
        right = sorted((e for e in new.events if e.code == code), key=lambda e: (e.start, e.end))

        def quality(a, b):
            if abs(a.start - b.start) > tolerance_ms or abs(a.end - b.end) > tolerance_ms:
                return None
            if not any((s, t) in allowed for s in old.events[a] for t in new.events[b]):
                return None
            return -abs(a.start - b.start) - abs(a.end - b.end)

        matched = ordered_match(left, right, quality)
        used_old, used_new = {i for i, _ in matched}, {j for _, j in matched}
        counts[index] = [len(left), len(right), len(matched),
                         sum(abs(left[i].start - right[j].start) for i, j in matched),
                         sum(abs(left[i].end - right[j].end) for i, j in matched),
                         sum((left[i].start - right[j].start) ** 2 for i, j in matched),
                         sum((left[i].end - right[j].end) ** 2 for i, j in matched)]
        rows = [(left[i], right[j], "matched", "within_tolerance") for i, j in matched]
        rows.extend((e, None, "old_only", "unmatched_situation" if not old.events[e] & paired_old
                     else "no_available_match_within_tolerance") for i, e in enumerate(left) if i not in used_old)
        rows.extend((None, e, "new_only", "unmatched_situation" if not new.events[e] & paired_new
                     else "no_available_match_within_tolerance") for j, e in enumerate(right) if j not in used_new)
        for a, b, status, reason in rows:
            details.append({"video": key, "code": code, "status": status, "reason": reason,
                "old_start_ms": a.start if a else None, "old_end_ms": a.end if a else None,
                "new_start_ms": b.start if b else None, "new_end_ms": b.end if b else None,
                "old_situations": "|".join(sorted(old.events[a])) if a else "",
                "new_situations": "|".join(sorted(new.events[b])) if b else "",
                "start_difference_ms": b.start - a.start if a and b else None,
                "end_difference_ms": b.end - a.end if a and b else None})
    return counts, details


def pflegekind_speech(video, key, rater):
    """Filter speech memberships using exact child/care and child/speech times.

    Child IDs are resolved independently per rater and situation. A long child
    annotation merely overlapping an utterance is not an addressee assignment.
    Non-speech events remain unchanged for use with the configured main scores.
    """
    children, care_rows, speech_rows = {}, [], []
    recipients = {}
    for event in video.events:
        if event.code.startswith("5.5."):
            recipients.setdefault((event.start, event.end), set()).add(event.code)
    for sid, window in video.situations.items():
        candidates = sorted(recipients.get(window, set()) & CHILD_CODES)
        children[sid] = candidates[0] if len(candidates) == 1 else None
        care_rows.append({
            "video": key, "rater": rater, "situation": sid,
            "start_ms": window[0], "end_ms": window[1],
            "pflegekind": children[sid], "candidate_children": "|".join(candidates),
            "status": "identified" if len(candidates) == 1 else "missing" if not candidates else "ambiguous",
        })
    filtered = Video(video.filename, dict(video.situations), {}, video.duplicate_rows)
    for event, memberships in sorted(video.events.items()):
        if event.code != SPEECH_CODE:
            filtered.events[event] = set(memberships)
            continue
        addresses = recipients.get((event.start, event.end), set())
        included = set()
        for sid in sorted(memberships):
            child = children[sid]
            if child is None:
                category = "unknown_pflegekind"
            elif child in addresses:
                category = "pflegekind_and_others" if addresses - {child} else "pflegekind_only"
                included.add(sid)
            elif addresses & CHILD_CODES:
                category = "other_child_without_explicit_pflegekind"
            elif addresses:
                category = "group_without_explicit_pflegekind"
            else:
                category = "unlinked_speech"
            speech_rows.append({
                "video": key, "rater": rater, "situation": sid, "code": SPEECH_CODE,
                "start_ms": event.start, "end_ms": event.end, "pflegekind": child,
                "recipient_codes": "|".join(sorted(addresses)), "category": category,
                "included_pflegekind_speech": sid in included,
            })
        if included:
            filtered.events[event] = included
    return filtered, care_rows, speech_rows


def code_coverage_counts(old, new, pairs, code):
    """Code union durations in intersections of paired care windows; no tolerance.

    Clip each event only to shared windows whose own situation membership it
    retains. This matters when one utterance spans situations with different
    care children. Unmatched situations are assessed by event/presence scores,
    and are outside this shared-observation duration comparison.
    """
    shared, old_intervals, new_intervals = [], [], []
    for a, b in pairs:
        if a is None or b is None:
            continue
        start = max(old.situations[a][0], new.situations[b][0])
        end = min(old.situations[a][1], new.situations[b][1])
        shared.append((start, end))
        for video, sid, intervals in ((old, a, old_intervals), (new, b, new_intervals)):
            intervals.extend((max(event.start, start), min(event.end, end))
                             for event, memberships in video.events.items()
                             if event.code == code and sid in memberships
                             and min(event.end, end) > max(event.start, start))
    old_intervals, new_intervals = merge_intervals(old_intervals), merge_intervals(new_intervals)
    return np.array([
        interval_duration(shared), interval_duration(old_intervals), interval_duration(new_intervals),
        interval_duration(intersect_intervals(old_intervals, new_intervals)),
    ], dtype=np.int64)


def speech_coverage_counts(old, new, pairs):
    return code_coverage_counts(old, new, pairs, SPEECH_CODE)


def code_duration_counts(old, new, pairs, codes):
    """Original retained interval unions and comparable shared-window coverage.

    Full durations include unmatched situations and unclipped boundary-crossing
    events. Union intervals separately per code/video, never across videos.
    """
    rows = []
    for code in codes:
        totals = [interval_duration((e.start, e.end) for e in video.events if e.code == code)
                  for video in (old, new)]
        rows.append([*totals, *code_coverage_counts(old, new, pairs, code), abs(totals[1] - totals[0])])
    return np.asarray(rows, dtype=np.int64)


def code_duration_metrics(counts, videos):
    old, new, shared, old_shared, new_shared, overlap, sum_abs_difference = map(int, counts)
    denominator = old_shared + new_shared
    union = denominator - overlap
    return {
        "videos": videos, "old_duration_ms": old, "new_duration_ms": new,
        "duration_difference_ms": new - old, "absolute_duration_difference_ms": abs(new - old),
        "duration_change_percent": 100 * (new - old) / old if old else None,
        "change_status": "defined" if old else "undefined_zero_old_duration",
        "sum_abs_video_difference_ms": sum_abs_difference,
        "mean_abs_video_difference_ms": sum_abs_difference / videos if videos else None,
        "shared_observation_ms": shared, "old_shared_duration_ms": old_shared,
        "new_shared_duration_ms": new_shared, "shared_overlap_ms": overlap,
        "duration_dice": 2 * overlap / denominator if denominator else None,
        "duration_jaccard": overlap / union if union else None,
        "shared_duration_status": "no_shared_observation" if not shared else "no_code_duration" if not union else "defined",
    }


def duration_difference_test(differences_ms):
    """Paired sign-flip test: exchangeable rater labels within independent videos.

    Tests the mean signed difference, not temporal overlap or equivalence.
    Enumerate all swaps up to 16 videos; otherwise use a seeded Monte Carlo test.
    """
    differences = np.asarray(differences_ms, dtype=float)
    if differences.ndim != 1 or not np.isfinite(differences).all():
        raise ValueError("Duration differences must be a finite one-dimensional array")
    n = len(differences)
    result = {"duration_test": "paired_sign_flip_mean_two_sided",
              "duration_test_videos": n,
              "duration_test_nonzero_pairs": int(np.count_nonzero(differences)),
              "mean_signed_duration_difference_ms": float(differences.mean()) if n else None,
              "duration_pvalue_two_sided": None,
              "duration_test_permutations": 0,
              "duration_test_status": "undefined_no_video_pairs"}
    if not n:
        return result
    exact = n <= 16
    # scipy requires at least two observations; a single pair cannot yield p<1.
    if n == 1:
        pvalue, permutations = 1.0, 2
    else:
        test = permutation_test((differences,), np.mean, permutation_type="samples",
                                vectorized=True, alternative="two-sided", batch=1024,
                                n_resamples=np.inf if exact else 65536,
                                rng=np.random.default_rng(42))
        pvalue, permutations = float(test.pvalue), len(test.null_distribution)
    result.update(duration_pvalue_two_sided=pvalue,
                  duration_test_permutations=permutations,
                  duration_test_status="exact" if exact else "monte_carlo")
    return result


def summarize_code_durations(per_video, codes, weights):
    videos = len(per_video)
    samples = np.einsum("bv,vck->bck", weights, per_video)
    rows = []
    for index, code in enumerate(codes):
        row = {"code": code, **code_duration_metrics(per_video[:, index].sum(axis=0), videos)}
        row.update(duration_difference_test(per_video[:, index, 1] - per_video[:, index, 0]))
        metrics = [code_duration_metrics(sample[index], videos) for sample in samples]
        for name in ("duration_difference_ms", "duration_change_percent", "mean_abs_video_difference_ms", "duration_dice"):
            defined = [m[name] for m in metrics if m[name] is not None]
            low, high = np.percentile(defined, [2.5, 97.5]) if defined else (None, None)
            row.update({f"{name}_ci_low": low, f"{name}_ci_high": high,
                        f"{name}_bootstrap_valid": len(defined)})
        rows.append(row)
    valid = [row for row in rows if row["duration_pvalue_two_sided"] is not None]
    for row in rows:
        row.update(duration_pvalue_holm=None, duration_significant_holm=None)
    if valid:
        rejected, adjusted, _, _ = multipletests(
            [row["duration_pvalue_two_sided"] for row in valid], alpha=.05, method="holm")
        for row, pvalue, significant in zip(valid, adjusted, rejected):
            row.update(duration_pvalue_holm=float(pvalue), duration_significant_holm=bool(significant))
    return rows


def speech_coverage_metrics(counts):
    shared, old, new, overlap = map(int, counts)
    union = old + new - overlap
    return {
        "shared_observation_ms": shared, "old_speech_ms": old, "new_speech_ms": new,
        "overlap_ms": overlap, "old_only_ms": old - overlap, "new_only_ms": new - overlap,
        "duration_dice": 2 * overlap / (old + new) if old + new else None,
        "duration_jaccard": overlap / union if union else None,
        "old_covered_by_new": overlap / old if old else None,
        "new_covered_by_old": overlap / new if new else None,
        "coverage_status": "no_shared_observation" if not shared else "no_speech" if not union else "defined",
    }


def summarize_speech(blocks, seed, replicates):
    """Summarize complete-video comparisons and bootstrap whole videos."""
    presence_rows, timing_rows, coverage_rows = [], [], []
    for scope, data in blocks.items():
        n = len(data["timing"])
        rng = np.random.default_rng(seed)
        weights = rng.multinomial(n, np.full(n, 1 / n), size=replicates) if n else np.zeros((replicates, 0), dtype=int)
        base = {"scope": scope, "videos_included": n, "videos_excluded": data["excluded"],
                "availability": "available" if n else "no_eligible_videos"}
        timing = np.asarray(data["timing"], dtype=np.int64).reshape(n, 1, 7)
        intervals = bootstrap_intervals(timing, [SPEECH_CODE], "timing", weights)[SPEECH_CODE]
        timing_rows.append({**base, "code": SPEECH_CODE, **timing_metrics(timing.sum(axis=0)[0]), **intervals})
        for level in ("video", "situation"):
            presence = np.asarray(data[level], dtype=np.int64).reshape(n, 1, 4)
            intervals = bootstrap_intervals(presence, [SPEECH_CODE], "presence", weights)[SPEECH_CODE]
            presence_rows.append({**base, "level": level, "code": SPEECH_CODE,
                                  **presence_metrics(presence.sum(axis=0)[0]), **intervals})
        coverage = np.asarray(data["coverage"], dtype=np.int64).reshape(n, 4)
        samples = weights @ coverage
        metrics = [speech_coverage_metrics(row) for row in samples]
        limits = {}
        for metric in ("duration_dice", "duration_jaccard", "old_covered_by_new", "new_covered_by_old"):
            defined = [row[metric] for row in metrics if row[metric] is not None]
            low, high = np.percentile(defined, [2.5, 97.5]) if defined else (None, None)
            limits.update({f"{metric}_ci_low": low, f"{metric}_ci_high": high,
                           f"{metric}_bootstrap_valid": len(defined)})
        coverage_rows.append({**base, "video": "__overall__",
                              **speech_coverage_metrics(coverage.sum(axis=0)), **limits})
    return presence_rows, timing_rows, coverage_rows


def finite_mean(values):
    present = [v for v in values if v is not None]
    return float(np.mean(present)) if present else None


def score_rows(counts, codes, kind, pool_presence=False):
    metrics = presence_metrics if kind == "presence" else timing_metrics
    rows = [{"code": code, **metrics(count)} for code, count in zip(codes, counts)]
    overall = {"code": "__overall__", **metrics(counts.sum(axis=0))}
    metric = "positive_f1" if kind == "presence" else "f1"
    overall["macro_f1"] = finite_mean([r[metric] for r in rows])
    overall["macro_f1_codes"] = sum(r[metric] is not None for r in rows)
    if kind == "presence" and not pool_presence:
        overall["kappa"] = None
        overall["kappa_status"] = "not_pooled_across_codes"
        overall["krippendorff_alpha"] = None
        overall["krippendorff_alpha_status"] = "not_pooled_across_codes"
    return rows + [overall]


def bootstrap_intervals(per_video, codes, kind, weights, pool_presence=False):
    """Resample video clusters using sufficient counts; never resample CSV rows."""
    samples = np.einsum("bv,vck->bck", weights, per_video)
    metrics = ("agreement", "positive_f1", "positive_specific_agreement", "negative_specific_agreement",
               "kappa", "krippendorff_alpha", "macro_f1") if kind == "presence" else (
        "f1", "mean_abs_start_error_ms", "mean_abs_end_error_ms", "sd_abs_start_error_ms",
        "sd_abs_end_error_ms", "macro_f1")
    values = {(code, metric): [] for code in [*codes, "__overall__"] for metric in metrics}
    for counts in samples:
        for row in score_rows(counts, codes, kind, pool_presence=pool_presence):
            for metric in metrics:
                value = row.get(metric)
                if value is not None:
                    values[row["code"], metric].append(value)
    results = {}
    for code in [*codes, "__overall__"]:
        fields = {}
        for metric in metrics:
            defined = values[code, metric]
            low, high = np.percentile(defined, [2.5, 97.5]) if defined else (None, None)
            fields.update({f"{metric}_ci_low": low, f"{metric}_ci_high": high,
                           f"{metric}_bootstrap_valid": len(defined)})
        results[code] = fields
    return results


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row))
    with Path(path).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def export_report_tables(report, directory):
    """Export the displayed Markdown tables verbatim as conventional CSVs.

    Section headings name the tables; numbering preserves report order. The
    report's rounded numbers and 'undefined' cells are intentionally retained,
    while the detailed score CSVs remain available at full precision.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    lines = report.splitlines()
    paths, heading, index = [], "table", 0
    while index < len(lines):
        line = lines[index].strip()
        if line.startswith("#"):
            heading = line.lstrip("#").strip()
        if line.startswith("|") and index + 1 < len(lines):
            header = [cell.strip() for cell in line.strip("|").split("|")]
            separator = [cell.strip() for cell in lines[index + 1].strip().strip("|").split("|")]
            if len(header) == len(separator) and all(re.fullmatch(r":?-{3,}:?", cell) for cell in separator):
                rows = []
                index += 2
                while index < len(lines) and lines[index].strip().startswith("|"):
                    cells = [cell.strip() for cell in lines[index].strip().strip("|").split("|")]
                    if len(cells) != len(header):
                        raise ValueError(f"Report table {heading!r} has an inconsistent row width")
                    rows.append(cells)
                    index += 1
                slug = REPORT_TABLE_SLUGS.get(heading) or re.sub(r"[^a-z0-9]+", "_", heading.lower()).strip("_") or "table"
                path = directory / f"{len(paths) + 1:02d}_{slug}.csv"
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.writer(handle)
                    writer.writerow(header)
                    writer.writerows(rows)
                paths.append(path)
                continue
        index += 1
    return paths


def validate_config(config):
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    if config.get("speech_scope", "all") not in ("all", "pflegekind"):
        raise ValueError("speech_scope must be 'all' or 'pflegekind'")
    for key in ("old_input_dir", "new_input_dir", "output_dir"):
        if not isinstance(config.get(key), str) or not config[key].strip():
            raise ValueError(f"{key} must be a nonempty path string")
    for name in ("presence_codes", "timing_codes", *(["duration_codes"] if "duration_codes" in config else [])):
        codes = config.get(name)
        if (not isinstance(codes, list) or not codes
                or any(not isinstance(c, str) or not re.fullmatch(r"\d+(?:\.\d+)+", c) for c in codes)
                or len(codes) != len(set(codes))):
            raise ValueError(f"{name} must be a nonempty list of distinct exact numeric code IDs")
    for name, minimum in (("tolerance_ms", 0), ("bootstrap_replicates", 1), ("bootstrap_seed", 0)):
        value = config.get(name)
        if type(value) is not int or value < minimum:
            raise ValueError(f"{name} must be an integer >= {minimum}")


def resolve_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def run_check(config):
    validate_config(config)
    duration_codes = config.get("duration_codes", list(dict.fromkeys(config["presence_codes"] + config["timing_codes"])))
    pairs, excluded = pair_files(resolve_path(config["old_input_dir"]), resolve_path(config["new_input_dir"]))
    output = resolve_path(config["output_dir"])
    exclusions = []
    detector = PatternDetector(sequence_scope="care-overlap",
                               strict_codes=set(config["presence_codes"] + config["timing_codes"] + duration_codes + [SPEECH_CODE]),
                               extraction_exclusions=exclusions)
    extracted = {"old": [], "new": []}
    # Validate all paired inputs before writing any comparison artifacts.
    for _, old_file, new_file in pairs:
        for rater, path in (("old", old_file), ("new", new_file)):
            previous = len(exclusions)
            extracted[rater].extend(detector.detect_patterns(pd.read_excel(path), path.name))
            for item in exclusions[previous:]:
                item["Rater"] = rater
    source_paths = {rater: output / "sequences" / rater / "sequence_analysis.csv" for rater in extracted}
    for rater, results in extracted.items():
        export_care_sequences(results, source_paths[rater])
    old_videos, new_videos = (read_sequences(source_paths[rater]) for rater in ("old", "new"))
    roster = {key for key, _, _ in pairs}
    if set(old_videos) != roster or set(new_videos) != roster:
        raise ValueError("Regenerated exports do not cover the complete paired roster")

    presence_by_video = {"video": [], "situation": []}
    timing_by_video = []
    presence_details, event_details, alignment_rows, file_rows = [], [], [], []
    per_video_scores = []
    durations_by_video, duration_blocks = [], []
    speech_blocks = {scope: {"video": [], "situation": [], "timing": [], "coverage": [], "excluded": 0}
                     for scope in ("all", "pflegekind")}
    speech_children, speech_recipients, speech_events, speech_presence_details = [], [], [], []
    speech_by_video, speech_coverage_by_video = [], []
    for key, old_path, new_path in pairs:
        old, new = old_videos[key], new_videos[key]
        alignment = align_situations(old, new)
        old_focus, old_children, old_recipients = pflegekind_speech(old, key, "old")
        new_focus, new_children, new_recipients = pflegekind_speech(new, key, "new")
        speech_children.extend(old_children + new_children)
        speech_recipients.extend(old_recipients + new_recipients)
        missing = [row for row in old_children + new_children if row["status"] != "identified"]
        reason = "|".join(f"{row['rater']}:{row['situation']}:{row['status']}" for row in missing)
        main_old, main_new = old, new
        if config.get("speech_scope", "all") == "pflegekind":
            if missing and SPEECH_CODE in config["presence_codes"] + config["timing_codes"] + duration_codes:
                raise ValueError(f"{key}: Missing or ambiguous Pflegekind ({reason}); cannot score selected 5.3.1")
            main_old, main_new = old_focus, new_focus
        presence, details = presence_counts(main_old, main_new, alignment, config["presence_codes"], key)
        presence_details.extend(details)
        for level, counts in presence.items():
            presence_by_video[level].append(counts)
        timing, details = compare_timing(main_old, main_new, alignment, config["timing_codes"], config["tolerance_ms"], key)
        timing_by_video.append(timing)
        event_details.extend(details)
        per_video_scores.extend({"video": key, **row} for row in score_rows(timing, config["timing_codes"], "timing"))
        duration_counts = code_duration_counts(main_old, main_new, alignment, duration_codes)
        duration_blocks.append(duration_counts)
        durations_by_video.extend({"video": key, "code": code, **code_duration_metrics(counts, 1)}
                                  for code, counts in zip(duration_codes, duration_counts))
        for scope, left, right in (("all", old, new), ("pflegekind", old_focus, new_focus)):
            base = {"scope": scope, "video": key, "availability": "available", "reason": ""}
            data = speech_blocks[scope]
            if scope == "pflegekind" and missing:
                data["excluded"] += 1
                base.update(availability="unavailable_pflegekind", reason=reason)
                speech_by_video.append({**base, "code": SPEECH_CODE})
                speech_coverage_by_video.append(base)
                continue
            counts, decisions = presence_counts(left, right, alignment, [SPEECH_CODE], key)
            for level in ("video", "situation"):
                data[level].append(counts[level])
            speech_presence_details.extend({"scope": scope, **row} for row in decisions)
            counts, matches = compare_timing(left, right, alignment, [SPEECH_CODE], config["tolerance_ms"], key)
            data["timing"].append(counts)
            speech_events.extend({"scope": scope, **row} for row in matches)
            speech_by_video.append({**base, "code": SPEECH_CODE, **timing_metrics(counts[0])})
            coverage = speech_coverage_counts(left, right, alignment)
            data["coverage"].append(coverage)
            speech_coverage_by_video.append({**base, **speech_coverage_metrics(coverage)})
        file_rows.append({"video": key, "old_input": str(old_path), "new_input": str(new_path),
            "old_situations": len(old.situations), "new_situations": len(new.situations),
            "matched_situations": sum(a is not None and b is not None for a, b in alignment),
            "old_only_situations": sum(b is None for _, b in alignment),
            "new_only_situations": sum(a is None for a, _ in alignment),
            "old_duplicate_export_rows": old.duplicate_rows, "new_duplicate_export_rows": new.duplicate_rows})
        for index, (a, b) in enumerate(alignment, 1):
            left, right = old.situations.get(a), new.situations.get(b)
            intersection = max(0, min(left[1], right[1]) - max(left[0], right[0])) if left and right else None
            alignment_rows.append({"video": key, "pair": f"p{index:03d}",
                "old_situation": a, "new_situation": b,
                "status": "matched" if a and b else "old_only" if a else "new_only",
                "old_start_ms": left[0] if left else None, "old_end_ms": left[1] if left else None,
                "new_start_ms": right[0] if right else None, "new_end_ms": right[1] if right else None,
                "iou": intersection / (max(left[1], right[1]) - min(left[0], right[0])) if left and right else None})

    rng = np.random.default_rng(config["bootstrap_seed"])
    weights = rng.multinomial(len(pairs), np.full(len(pairs), 1 / len(pairs)), size=config["bootstrap_replicates"])
    presence_scores = []
    for level, blocks in presence_by_video.items():
        blocks = np.asarray(blocks)
        intervals = bootstrap_intervals(blocks, config["presence_codes"], "presence", weights,
                                        pool_presence=(level == "situation"))
        for row in score_rows(blocks.sum(axis=0), config["presence_codes"], "presence",
                              pool_presence=(level == "situation")):
            presence_scores.append({"level": level, **row, **intervals[row["code"]]})
    blocks = np.asarray(timing_by_video)
    intervals = bootstrap_intervals(blocks, config["timing_codes"], "timing", weights)
    timing_scores = [{**row, **intervals[row["code"]]} for row in score_rows(blocks.sum(axis=0), config["timing_codes"], "timing")]
    speech_presence_scores, speech_timing_scores, speech_coverage_scores = summarize_speech(
        speech_blocks, config["bootstrap_seed"], config["bootstrap_replicates"])
    duration_scores = summarize_code_durations(np.asarray(duration_blocks), duration_codes, weights)
    for row in presence_scores + speech_presence_scores:
        row.update(kappa_significance(row))
    for name, rows in {
        "file_pairs.csv": file_rows, "situation_pairs.csv": alignment_rows,
        "presence_details.csv": presence_details, "presence_scores.csv": presence_scores,
        "event_matches.csv": event_details, "timing_by_video.csv": per_video_scores,
        "timing_scores.csv": timing_scores,
        "code_duration_scores.csv": duration_scores,
        "code_durations_by_video.csv": durations_by_video,
        "speech_care_children.csv": speech_children,
        "speech_recipients.csv": speech_recipients,
        "speech_presence_details.csv": speech_presence_details,
        "speech_presence_scores.csv": speech_presence_scores,
        "speech_event_matches.csv": speech_events,
        "speech_timing_by_video.csv": speech_by_video,
        "speech_timing_scores.csv": speech_timing_scores,
        "speech_coverage.csv": speech_coverage_by_video + speech_coverage_scores,
    }.items():
        fields = EVENT_FIELDS if name == "event_matches.csv" else None
        if name == "speech_event_matches.csv":
            fields = ["scope", *EVENT_FIELDS]
        elif name == "speech_recipients.csv":
            fields = ["video", "rater", "situation", "code", "start_ms", "end_ms", "pflegekind",
                      "recipient_codes", "category", "included_pflegekind_speech"]
        write_csv(output / name, rows, fields)
    with (output / "excluded_annotations.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["Rater", "Filename", "Excel_Row", "Code", "Start", "End", "Reason"])
        writer.writeheader()
        writer.writerows(exclusions)
    manifest = {**config, "extraction_scope": "care-overlap", "duration_unit": "milliseconds",
                "duration_codes": duration_codes,
                "code_duration_total_scope": "union of complete retained original intervals per code/video, including unmatched situations",
                "code_duration_comparison_scope": "intersections of paired care windows; no event tolerance",
                "speech_scope": config.get("speech_scope", "all"),
                "speech_comparison_scopes": ["all", "pflegekind"],
                "speech_recipient_matching": "exact normalized start and end; independent care child per rater/situation",
                "paired_videos": [key for key, _, _ in pairs], "excluded_old_videos": excluded,
                "old_export": str(source_paths["old"]), "new_export": str(source_paths["new"]),
                "invalid_unselected_annotations_excluded": len(exclusions)}
    (output / "settings.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    speech_results = {"presence": speech_presence_scores, "timing": speech_timing_scores,
                      "coverage": speech_coverage_scores, "children": speech_children}
    report = make_report(config, file_rows, presence_scores, timing_scores, excluded, exclusions, speech_results, duration_scores)
    (output / "report.md").write_text(report, encoding="utf-8")
    report_tables = export_report_tables(report, output / "report_tables")
    return {"output_dir": output, "file_pairs": file_rows, "presence_scores": presence_scores,
            "timing_scores": timing_scores, "duration_scores": duration_scores,
            "speech": speech_results, "report_tables": report_tables}


def formatted(value):
    return "undefined" if value is None else f"{value:.3f}"


def report_value(value):
    return "nicht definiert" if value is None else formatted(value)


def report_pvalue(value):
    if value is None:
        return "nicht definiert"
    return "<0.001" if value < .001 else f"{value:.3f}"


def speech_label(scope):
    return {"all": "Alle Kindansprachen", "pflegekind": "Pflegekind-Sprache"}[scope]


def make_report(config, files, presence, timing, excluded, exclusions=(), speech=None, durations=None):
    overall = next(r for r in timing if r["code"] == "__overall__")
    lines = ["# Interrater-Analyse", "",
        f"Verglichen wurden {len(files)} Videopaare. {len(excluded)} Videos des alten Datensatzes "
        "ohne zweite Kodierung wurden ausgeschlossen. „Alt“ bezeichnet die erste, „neu“ die zweite kodierende Person.",
        f"Pflegesituationen: alt={sum(r['old_situations'] for r in files)}, "
        f"neu={sum(r['new_situations'] for r in files)}, zugeordnet={sum(r['matched_situations'] for r in files)}.",
        f"Sprachvariante für 5.3.1 in der Hauptauswertung: **{speech_label(config.get('speech_scope', 'all'))}** "
        f"(`speech_scope={config.get('speech_scope', 'all')}`). Die zusätzlichen Sprachauswertungen "
        "vergleichen stets alle Kindansprachen und ausdrücklich zugeordnete Pflegekind-Sprache.",
        f"{len(exclusions)} fehlerhafte Annotationen außerhalb der ausgewerteten beziehungsweise zwingend "
        "benötigten Codes wurden ausgeschlossen; siehe `excluded_annotations.csv`. Fehlerhafte ausgewählte "
        "Codes, Sprechintervalle oder Pflegesituationen führen zum Abbruch.",
        "", "## Code-Präsenz", "",
        "Für jeden ausgewählten Code wird sein Vorhandensein beziehungsweise Fehlen verglichen, unabhängig "
        "von der Anzahl seiner Wiederholungen. Ein Video oder eine zugeordnete beziehungsweise einseitige "
        "Pflegesituation bildet jeweils eine binäre Beobachtungseinheit. Bei einer einseitigen Situation "
        "gilt die fehlende Gegenseite als nicht vorhanden. Die Gesamtzeile auf Situationsebene fasst "
        "alle Kombinationen aus Situation und ausgewähltem Code zusammen; Kappa und Alpha beruhen dort "
        "auf diesen gepoolten Zählungen, nicht auf Mittelwerten der Einzelcodes. Gemeinsame Abwesenheiten "
        "und die Auswahl der Codes beeinflussen das Ergebnis. Mehrere Kombinationen können zum selben "
        "Video gehören; Konfidenzintervalle ziehen deshalb ganze Videos. Die Übereinstimmung wird als Anteil von 0 bis 1 dargestellt.", "",
        "| Ebene | Code | Beide vorhanden | Nur alt | Nur neu | Beide fehlend | Übereinstimmung | Kappa | Kappa p (zweiseitig) | Krippendorffs Alpha | Positive spezifische Übereinstimmung (positiver F1) | Negative spezifische Übereinstimmung |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in presence:
        level = {"video": "Video", "situation": "Pflegesituation"}[row["level"]]
        code = "Gesamt" if row["code"] == "__overall__" else row["code"]
        lines.append(f"| {level} | {code} | {row['both_present']} | {row['old_only']} | "
                     f"{row['new_only']} | {row['both_absent']} | {report_value(row['agreement'])} | "
                     f"{report_value(row['kappa'])} | {report_pvalue(row['kappa_pvalue_two_sided'])} | "
                     f"{report_value(row['krippendorff_alpha'])} | "
                     f"{report_value(row['positive_specific_agreement'])} | "
                     f"{report_value(row['negative_specific_agreement'])} |")
    lines += ["", "Kappa-p-Werte: asymptotischer zweiseitiger Normaltest von H₀: κ = 0 mit "
              "`statsmodels.stats.inter_rater.cohens_kappa` und der Varianz unter H₀. "
              "Die p-Werte sind nicht für multiples Testen korrigiert und setzen unabhängige "
              "Beobachtungseinheiten voraus. Bei nur zehn Videos ist die Normalapproximation unsicher; "
              "auf Situationsebene und bei gepoolten Codes berücksichtigt dieser Standardtest die "
              "Abhängigkeiten innerhalb eines Videos nicht. Die Video-Bootstrap-Intervalle bleiben "
              "davon getrennt. Bei undefiniertem Kappa oder einer Nullvarianz unter H₀ ist auch der "
              "Test nicht definiert. Ein kleiner p-Wert belegt keine ausreichend hohe Reliabilität. "
              "Quelle: [statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.cohens_kappa.html)."]
    situation_overall = next(row for row in presence if row["level"] == "situation" and row["code"] == "__overall__")
    lines += ["", "Für die Gesamtwerte auf Pflegesituationsebene (95%-Perzentilintervalle aus dem "
              f"Video-Bootstrap mit {config['bootstrap_replicates']} Wiederholungen):"]
    for metric, label in (("agreement", "Übereinstimmung"),
                          ("positive_specific_agreement", "Positive spezifische Übereinstimmung"),
                          ("negative_specific_agreement", "Negative spezifische Übereinstimmung"),
                          ("kappa", "Cohen’s Kappa"),
                          ("krippendorff_alpha", "Krippendorffs Alpha")):
        lines.append(f"- {label}: **{report_value(situation_overall[metric])}**, "
                     f"95%-Konfidenzintervall [{report_value(situation_overall[f'{metric}_ci_low'])}, "
                     f"{report_value(situation_overall[f'{metric}_ci_high'])}]; "
                     f"{situation_overall[f'{metric}_bootstrap_valid']} von {config['bootstrap_replicates']} "
                     "Wiederholungen definiert.")
    lines += ["", "Die Intervalle beschreiben die Unsicherheit unter dem Video-Bootstrap. "
              "Bei wenigen Videos können sie trotz vieler Wiederholungen instabil sein."]
    lines += ["", "## Zeitliche Ereignisübereinstimmung", "",
        f"Beginn und Ende dürfen jeweils um höchstens {config['tolerance_ms']} ms voneinander abweichen "
        "(einschließlich des Grenzwerts). Gleiche Codes werden innerhalb zugeordneter Situationen "
        "chronologisch eins zu eins abgeglichen.",
        f"Gesamt-F1 aus zusammengefassten Zählungen: **{report_value(overall['f1'])}**, "
        f"95%-Konfidenzintervall aus dem Video-Bootstrap "
        f"[{report_value(overall['f1_ci_low'])}, {report_value(overall['f1_ci_high'])}]. "
        f"Zugeordnet wurden {overall['matched_events']} Ereignisse; alt={overall['old_events']}, neu={overall['new_events']}.", "",
        "Die Standardabweichung beschreibt die Streuung der absoluten Abweichungen zugeordneter Ereignisse "
        "(Stichprobenstandardabweichung mit n − 1); bei weniger als zwei Zuordnungen ist sie nicht definiert. "
        "Sie berücksichtigt nur Ereignisse innerhalb der Toleranz.", "",
        "| Code | Ereignisse alt | Ereignisse neu | Zugeordnet | F1 | Mittlere absolute Anfangsabweichung (ms) | SD absolute Anfangsabweichung (ms) | Mittlere absolute Endabweichung (ms) | SD absolute Endabweichung (ms) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in timing:
        code = "Gesamt" if row["code"] == "__overall__" else row["code"]
        lines.append(f"| {code} | {row['old_events']} | {row['new_events']} | {row['matched_events']} | "
                     f"{report_value(row['f1'])} | {report_value(row['mean_abs_start_error_ms'])} | "
                     f"{report_value(row['sd_abs_start_error_ms'])} | {report_value(row['mean_abs_end_error_ms'])} | "
                     f"{report_value(row['sd_abs_end_error_ms'])} |")
    if speech:
        lines += ["", "## Pflegekind-Sprache und alle Kindansprachen", "",
            "Das Pflegekind wird je Person und Situation unabhängig bestimmt: Es ist der eindeutig "
            "zugeordnete Code aus 5.5.1–5.5.10 mit exakt dem Beginn und Ende der 6.1.1-Pflegesituation. "
            "Ein Sprechintervall zählt als Pflegekind-Sprache, wenn dieses Kind außerdem mit exakt "
            "dem Beginn und Ende des Sprechintervalls kodiert ist. Weitere gleichzeitig angesprochene "
            "Personen sind erlaubt. Kindnummern können sich zwischen den kodierenden Personen unterscheiden. "
            "Gruppenansprachen und Intervalle ohne passende Kindreferenz werden separat protokolliert und "
            "nicht als bestätigte Pflegekind-Sprache gewertet. Die Ereignistoleranz lockert diese exakte Zuordnung nicht.", "",
            "### Zuordnung der Sprechintervalle", "",
            "| Sprachvariante | Eingeschlossene Videos | Ausgeschlossene Videos | Intervalle alt | Intervalle neu | Zugeordnet | Ereignis-F1 |",
            "|---|---:|---:|---:|---:|---:|---:|"]
        for row in speech["timing"]:
            lines.append(f"| {speech_label(row['scope'])} | {row['videos_included']} | {row['videos_excluded']} | "
                         f"{row['old_events']} | {row['new_events']} | {row['matched_events']} | {report_value(row['f1'])} |")
        lines += ["", "Für den Sprechzeitvergleich wird ausschließlich die gemeinsame Zeit innerhalb "
                  "zugeordneter Pflegesituationen verwendet. Überlappende Intervalle werden vereinigt; "
                  "eine zeitliche Toleranz wird nicht angewandt. Nicht zugeordnete Situationen bleiben "
                  "im Präsenz- und Ereignisvergleich enthalten, haben jedoch kein gemeinsames Zeitfenster "
                  "für den Dauervergleich. Dauer-Dice = 2 × überlappende Sprechzeit / (alte + neue Sprechzeit). "
                  "Dieser Wert ist weniger empfindlich gegenüber der Aufteilung einer Sprechepisode in mehrere Äußerungen.", "",
            "### Gemeinsame Sprechzeit", "",
            "| Sprachvariante | Gemeinsame Beobachtungszeit (s) | Sprechzeit alt (s) | Sprechzeit neu (s) | Überlappung (s) | Dauer-Dice | Alte Sprechzeit durch neue abgedeckt |",
            "|---|---:|---:|---:|---:|---:|---:|"]
        for row in speech["coverage"]:
            lines.append(f"| {speech_label(row['scope'])} | {row['shared_observation_ms'] / 1000:.3f} | "
                         f"{row['old_speech_ms'] / 1000:.3f} | {row['new_speech_ms'] / 1000:.3f} | "
                         f"{row['overlap_ms'] / 1000:.3f} | {report_value(row['duration_dice'])} | "
                         f"{report_value(row['old_covered_by_new'])} |")
        lines += ["", "Präsenz, Kappa und Krippendorffs Alpha, Ereigniszuordnungen, Dauer-Dice und Jaccard, gerichtete "
                  "Abdeckungsanteile und Bootstrap-Konfidenzintervalle stehen in `speech_presence_scores.csv`, "
                  "`speech_timing_scores.csv` und `speech_coverage.csv`. `speech_recipients.csv` und "
                  "`speech_care_children.csv` dokumentieren die Filterentscheidungen. Fehlt eine eindeutige "
                  "Pflegekindzuordnung, wird das gesamte Video aus der separaten Pflegekind-Auswertung "
                  "ausgeschlossen; fehlende Information wird nicht als fehlende Sprache behandelt. Die "
                  "Videozahlen weisen diese Ausschlüsse aus. Bei `speech_scope=pflegekind` in der "
                  "Hauptauswertung führt eine fehlende Zuordnung stattdessen zum Abbruch, sofern 5.3.1 "
                  "ausgewertet wird. Sprechintervalle ohne passende Kindreferenz bleiben im Prüfprotokoll "
                  "sichtbar. Ein für eine Situation bestätigtes Pflegekind-Sprechintervall gilt nicht "
                  "automatisch auch für eine überlappende andere Situation."]
    if durations:
        lines += ["", "## Dauer der Codes", "",
            "Für die vollständigen Dauern werden die beibehaltenen Originalintervalle pro Code und Video "
            "vereinigt und anschließend über Videos aufsummiert. Grenzüberschreitende Ereignisse und nicht "
            "zugeordnete Situationen zählen mit; die Intervalle werden nicht auf Pflegesituationen begrenzt. "
            "Ohne zusätzliche Einstellung werden alle Codes aus `presence_codes` und `timing_codes` "
            "berücksichtigt. Mit `duration_codes` kann eine eigene Liste gewählt werden. Für 5.3.1 gilt "
            "die Sprachvariante der Hauptauswertung (`speech_scope`).", "",
            "Differenz = neu − alt; Veränderung (%) = 100 × Differenz / alt, bei einer alten Dauer von null "
            "nicht definiert. Die mittlere absolute Videodifferenz mittelt die absoluten Dauerabweichungen "
            "der einzelnen Videos, damit sich positive und negative Unterschiede nicht gegenseitig "
            "aufheben. Die Dauern im gemeinsamen Fenster und der Dauer-Dice verwenden dagegen die "
            "Schnittmengen zugeordneter Situationen, ohne Ereignistoleranz. Bei 6.1.1 stimmen diese gemeinsamen "
            "Dauern konstruktionsbedingt überein; unterschiedliche Situationsgrenzen zeigen sich in den "
            "vollständigen Dauern und den Grenz- beziehungsweise Ereignisvergleichen. Die Tabelle zeigt "
            "Sekunden; detaillierte Dauern und deren Konfidenzintervalle in den CSVs verwenden Millisekunden.", "",
            "| Code | Dauer alt (s) | Dauer neu (s) | Differenz (s) | Absolute Differenz (s) | Veränderung (%) | Mittlere absolute Videodifferenz (s) | Alt im gemeinsamen Fenster (s) | Neu im gemeinsamen Fenster (s) | Dauer-Dice |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for row in durations:
            lines.append(f"| {row['code']} | {row['old_duration_ms'] / 1000:.3f} | "
                         f"{row['new_duration_ms'] / 1000:.3f} | {row['duration_difference_ms'] / 1000:.3f} | "
                         f"{row['absolute_duration_difference_ms'] / 1000:.3f} | {report_value(row['duration_change_percent'])} | "
                         f"{row['mean_abs_video_difference_ms'] / 1000:.3f} | {row['old_shared_duration_ms'] / 1000:.3f} | "
                         f"{row['new_shared_duration_ms'] / 1000:.3f} | {report_value(row['duration_dice'])} |")
        lines += ["", "Die ungerundeten Kennwerte und Bootstrap-Konfidenzintervalle stehen in "
                  "`code_duration_scores.csv`, die Dauern pro Video in `code_durations_by_video.csv`. "
                  "Unterschiedliche Codes können gleichzeitig auftreten; ihre Dauern dürfen daher nicht "
                  "wie voneinander getrennte Beobachtungszeiten aufsummiert werden."]
        lines += ["", "### Signifikanz der Dauerunterschiede", "",
                  "Pro Code wird die vollständige Dauer je Video zwischen den beiden Personen gepaart "
                  "verglichen (Differenz = neu − alt). Der zweiseitige gepaarte Permutationstest verwendet "
                  "die mittlere vorzeichenbehaftete Videodifferenz als Teststatistik. Unter H₀ müssen die "
                  "Personenbezeichnungen innerhalb eines Videos austauschbar sein (symmetrische "
                  "Differenzen um null); die Videos werden als unabhängig vorausgesetzt. Mehrere "
                  "Situationen desselben Videos werden vorher zusammengefasst. Der Test benötigt keine "
                  "Normalverteilungsannahme. Auch Videos mit beidseitiger Abwesenheit zählen mit. "
                  "Bis 16 Videos werden alle 2^N Vertauschungen ausgewertet; darüber 65536 zufällige "
                  "Vertauschungen mit Startwert 42. Holm korrigiert über alle hier ausgewerteten "
                  "Dauercodes; signifikant bedeutet korrigiertes p < 0.05. Ein nicht signifikanter "
                  "Unterschied belegt keine Gleichwertigkeit oder zeitliche Übereinstimmung. "
                  "Bei abhängigen Videos derselben Person ist eine Analyse auf Personenebene erforderlich. "
                  "Quelle: [SciPy permutation_test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).", "",
                  "| Code | Videopaare | Paare mit Differenz ≠ 0 | Mittlere Differenz (s/Video) | 95%-Bootstrap-KI (s/Video) | p (zweiseitig) | p (Holm) | Signifikant (Holm) |",
                  "|---|---:|---:|---:|---|---:|---:|---|"]
        for row in durations:
            scale = row["videos"] * 1000
            low = row["duration_difference_ms_ci_low"] / scale
            high = row["duration_difference_ms_ci_high"] / scale
            lines.append(f"| {row['code']} | {row['duration_test_videos']} | "
                         f"{row['duration_test_nonzero_pairs']} | "
                         f"{row['mean_signed_duration_difference_ms'] / 1000:.3f} | "
                         f"[{low:.3f}, {high:.3f}] | {report_pvalue(row['duration_pvalue_two_sided'])} | "
                         f"{report_pvalue(row['duration_pvalue_holm'])} | "
                         f"{'ja' if row['duration_significant_holm'] else 'nein'} |")
    lines += ["", "## Definitionen und Reproduzierbarkeit", "",
        "- Beide kodierenden Personen werden symmetrisch behandelt; keine gilt als fehlerfreie Referenz.",
        "- Jede 6.1.1-Pflegesituation wird exportiert. Annotationen mit positiver Überlappung behalten ihre "
        "ursprünglichen, ungekürzten Zeitstempel. Setting- oder Pflegetypzuordnungen sind keine Voraussetzung. "
        "Eine bloße Berührung der Intervallgrenzen und Intervalle ohne Dauer haben keine positive Überlappung.",
        "- Verglichen werden vollständige numerische Code-IDs; Bezeichnungen werden ignoriert. Identische "
        "Kopien mit gleichem Code, Beginn und Ende werden nicht mehrfach gezählt. Ein Ereignis über mehrere "
        "Situationen zählt bei Video-Präsenz und Ereignisvergleich einmal, bei der Situationspräsenz in "
        "jeder Situation, der es zugeordnet ist.",
        "- Die Situationszuordnung maximiert zunächst die Anzahl chronologisch überlappender Paare, dann "
        "deren gesamte relative Überlappung (Schnittmenge geteilt durch Vereinigungsmenge). Abweichende "
        "Pflegetypen verhindern kein Paar. Die Ereigniszuordnung maximiert zuerst die Trefferzahl und "
        "minimiert danach die absoluten Grenzabweichungen. Die Zeilenposition `Sequence_Order` wird nicht "
        "verglichen; gleichzeitig auftretende unterschiedliche Codes bleiben unabhängig.",
        "- Übereinstimmung = (beide vorhanden + beide fehlend) / Beobachtungseinheiten. Kappa = "
        "(beobachtete − erwartete Übereinstimmung) / (1 − erwartete Übereinstimmung). Die erwartete "
        "Übereinstimmung beruht auf den binären Randhäufigkeiten beider Personen. Die Gesamtzeile "
        "auf Situationsebene verwendet die zusammengefassten binären Bewertungen aller ausgewählten Codes.",
        "- Krippendorffs Alpha wird nominal für dieselben binären Präsenzeinheiten pro Code berechnet: "
        "Alpha = 1 − D_o / D_e. Bei N Einheiten, m abweichenden Bewertungspaaren sowie n_1 vorhandenen "
        "und n_0 fehlenden Bewertungen über beide Personen gilt D_o = m / N und "
        "D_e = n_1 × n_0 / (N × (2N − 1)). Die erwartete Abweichung verwendet die gemeinsamen "
        "Kategoriehäufigkeiten mit Korrektur für endliche Stichproben. Negative Alpha-Werte sind möglich. "
        "Die Gesamtzeile auf Situationsebene verwendet die zusammengefassten Bewertungen aller Codes. "
        "Einseitige Situationen werden auch "
        "hier als Abwesenheit auf der Gegenseite gewertet; dies ist kein Alpha für die Segmentierung.",
        "- Positiver F1 = 2 × beide vorhanden / (2 × beide vorhanden + nur alt + nur neu). "
        "Dieser Wert entspricht bei zwei Personen der positiven spezifischen Übereinstimmung. "
        "Negative spezifische Übereinstimmung = 2 × beide fehlend / (2 × beide fehlend + nur alt + nur neu). "
        "Bei ausschließlich negativen beziehungsweise positiven Bewertungen ist die positive beziehungsweise "
        "negative spezifische Übereinstimmung nicht definiert. Gesamtwerte beruhen auf gepoolten "
        "Zählungen über alle ausgewählten Codes. Die CSVs enthalten beide Kennwerte mit Status, "
        "Bootstrap-Intervallen und Anzahl definierter Wiederholungen. "
        "Ereignis-F1 = 2 × zugeordnete Ereignisse / (alte + neue Ereignisse). Für den Ereignisvergleich "
        "werden keine künstlichen Zeitraster mit negativen Beobachtungen gebildet.",
        "- Der Gesamt-F1 verwendet zusammengefasste Zählungen (Mikro-Mittelung); `macro_f1` mittelt die "
        "definierten F1-Werte pro Code. Bei beidseitiger Abwesenheit ist F1 nicht definiert; bei identischen "
        "konstanten Bewertungen oder ohne Beobachtungseinheiten sind Kappa und Alpha nicht definiert. "
        "Die detaillierten CSVs enthalten dann leere "
        "Felder und Statusangaben; solche Werte gehen nicht in Makro-Mittelwerte ein.",
        "- Alpha sowie seine Video-Bootstrap-Konfidenzintervalle und die Anzahl definierter "
        "Wiederholungen stehen in `presence_scores.csv` und `speech_presence_scores.csv` unter "
        "`krippendorff_alpha`, `krippendorff_alpha_ci_low`, `krippendorff_alpha_ci_high` und "
        "`krippendorff_alpha_bootstrap_valid`.",
        f"- Die Konfidenzintervalle verwenden {config['bootstrap_replicates']} Bootstrap-Wiederholungen "
        f"mit ganzen Videos, dem Startwert {config['bootstrap_seed']} und den Perzentilen 2,5 % und 97,5 %. "
        "Situations- und Ereigniszeilen werden nicht unabhängig gezogen. Die CSVs nennen die Anzahl "
        "definierter Wiederholungen pro Kennwert. Undefinierte Wiederholungen werden ausgelassen; bei "
        "nur zehn Videos können die Intervalle instabil sein.",
        "- Die Kennwerte beziehen sich auf Annotationen, die Pflegesituationen überlappen, nicht auf die "
        "gesamte Videozeit. Die Situationsübereinstimmung hängt von der beschriebenen Überlappungszuordnung "
        "ab und ist kein eigenständiges Maß für Sequenzreihenfolge oder Segmentierungs-Kappa.",
        "- Korrigierte Sequenzen, Einzelentscheidungen, Ereignispaare, nicht zugeordnete Ereignisse, "
        "Code-Zusammenfassungen, Konfidenzintervalle und verwendete Einstellungen liegen neben diesem "
        "Bericht. Jede dargestellte Tabelle wird außerdem als eigene CSV unter `report_tables/` "
        "ausgegeben, mit denselben deutschen Spalten, Zeilen, Rundungen und Angaben „nicht definiert“. "
        "Die Dateinamen bleiben unverändert; die detaillierten Datendateien behalten ihre technischen "
        "Spaltennamen und numerische Genauigkeit. Zahlen verwenden weiterhin den Dezimalpunkt. "
        "Die ursprünglichen Analysedateien bleiben erhalten.",
        "", "Codes für den Präsenzvergleich: " + ", ".join(config["presence_codes"]) + ".",
        "Codes für den Ereignisvergleich: " + ", ".join(config["timing_codes"]) + ".", "",
        "Methodische Quellen: [Cohen's Kappa](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html), "
        "[Krippendorffs Alpha](https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf), "
        "[F1](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.f1_score.html).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--tolerance-ms", type=int)
    parser.add_argument("--output-dir", type=str)
    parser.add_argument("--speech-scope", choices=["all", "pflegekind"])
    args = parser.parse_args()
    try:
        config_path = args.config.resolve()
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if args.tolerance_ms is not None:
            config["tolerance_ms"] = args.tolerance_ms
        if args.output_dir is not None:
            config["output_dir"] = args.output_dir
        if args.speech_scope is not None:
            config["speech_scope"] = args.speech_scope
        validate_config(config)
        tolerance_source = "command-line override" if args.tolerance_ms is not None else "config file"
        print(f"Config: {config_path}", flush=True)
        print(f"Tolerance: {config['tolerance_ms']} ms ({tolerance_source})", flush=True)
        print(f"Main speech scope: {config.get('speech_scope', 'all')}", flush=True)
        result = run_check(config)
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Interrater check failed: {error}\n")
    overall = next(row for row in result["timing_scores"] if row["code"] == "__overall__")
    print(f"Compared {len(result['file_pairs'])} video pairs; timing F1={formatted(overall['f1'])}")
    print(f"Report: {result['output_dir'] / 'report.md'}")


if __name__ == "__main__":
    main()
