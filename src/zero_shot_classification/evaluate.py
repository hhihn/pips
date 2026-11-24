"""Evaluate zero-shot predictions against the annotated labels for each sentence."""

import csv
from collections import Counter, defaultdict
from itertools import product
from math import nextafter
from pathlib import Path
from statistics import mean


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
DATASET_PATH = OUTPUT_DIR / "zero_shot_dataset.csv"
PREDICTIONS_PATH = OUTPUT_DIR / "zero_shot_predictions.csv"
REPORT_PATH = OUTPUT_DIR / "zero_shot_evaluation.txt"


def read_rows(path, fields):
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not set(fields).issubset(reader.fieldnames or []):
            raise ValueError(f"{path.name} must contain {', '.join(fields)}")
        for row in reader:
            if any(not (row[field] or "").strip() for field in fields):
                raise ValueError(f"{path.name}, line {reader.line_num}: missing required value")
            yield row


def find_optimal_threshold(truth, predictions):
    """Maximize exact label-set matches, breaking ties by highest threshold."""
    changes = Counter()
    for sentence, labels in truth.items():
        scores = predictions.get(sentence, {})
        lowest_true = min(scores.get(label, 0.0) for label in labels)
        highest_extra = max((score for label, score in scores.items() if label not in labels), default=0.0)
        # This sentence matches exactly for highest_extra <= threshold < lowest_true.
        if highest_extra < lowest_true:
            changes[highest_extra] += 1
            changes[lowest_true] -= 1

    threshold = 1.0
    matches = best_matches = 0
    for boundary in sorted(changes):
        # Before applying the change, evaluate the upper end of the preceding interval.
        if matches and matches >= best_matches:
            threshold = nextafter(boundary, 0.0)
            best_matches = matches
        matches += changes[boundary]

    true_count = sum(map(len, truth.values()))
    matched = retained = 0
    for sentence, scores in predictions.items():
        for label, score in scores.items():
            if score > threshold:
                retained += 1
                matched += label in truth[sentence]

    f1 = 2 * matched / (true_count + retained)
    precision = matched / retained if retained else 0.0
    recall = matched / true_count
    return threshold, f1, precision, recall


def build_report(truth, predictions):
    threshold, f1, precision, recall = find_optimal_threshold(truth, predictions)
    complete = exact = matched_count = true_count = 0
    missed_counts = Counter()
    extra_counts = Counter()
    mistake_pairs = Counter()
    correct_counts = Counter()
    minimum_scores = []

    for sentence, true_labels in truth.items():
        scores = {
            label: score for label, score in predictions.get(sentence, {}).items()
            if score > threshold
        }
        predicted_labels = set(scores)
        missing = true_labels - predicted_labels
        unexpected = predicted_labels - true_labels

        complete += not missing
        exact += not missing and not unexpected
        correct = len(true_labels & predicted_labels)
        correct_counts[correct] += 1
        matched_count += correct
        true_count += len(true_labels)
        missed_counts.update(missing)
        extra_counts.update(unexpected)
        mistake_pairs.update(product(missing, unexpected))
        if scores:
            minimum_scores.append(min(scores.values()))

    total = len(truth)
    average = f"{mean(minimum_scores):.4f}" if minimum_scores else "unavailable"
    lines = [
        f"Evaluation at the best threshold (keep scores strictly above {threshold})",
        f"Distinct sentences evaluated: {total}",
        f"Sentences with all true labels found: {complete}/{total} ({complete / total:.1%})",
        f"Sentences with an exact label-set match: {exact}/{total} ({exact / total:.1%})",
        f"True sentence-label pairs found: {matched_count}/{true_count} ({matched_count / true_count:.1%})",
        f"Sentences with no retained labels: {total - len(minimum_scores)}",
        f"Average lowest retained score: {average} across {len(minimum_scores)} sentences with predictions",
        "",
        "Correct predicted labels per sentence",
    ]
    for minimum in range(1, 11):
        count = sum(frequency for correct, frequency in correct_counts.items() if correct >= minimum)
        lines.append(f"At least {minimum} correct: {count}/{total} ({count / total:.1%})")

    lines.extend([
        "",
        "Threshold optimized for sentences with an exact label-set match",
        f"Best threshold (keep scores strictly above it): {threshold}",
        f"Micro-F1: {f1:.2%}",
        f"Micro-precision: {precision:.2%}",
        f"Micro-recall: {recall:.2%}",
        "The sweep uses the scores available in the predictions CSV.",
        "",
        "Possible label confusions",
        "Counts include every missing true label and unexpected predicted label on the same sentence.",
        "A sentence with several errors may contribute several pairs, so counts do not establish one-to-one substitutions.",
        "Missing true label\tUnexpected predicted label\tSentences\tShare of sentences missing the true label",
    ])
    for (missing, unexpected), count in sorted(
        mistake_pairs.items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"{missing}\t{unexpected}\t{count}\t{count / missed_counts[missing]:.1%}")
    if not mistake_pairs:
        lines.append("No sentences had both a missing and an unexpected label.")

    for heading, counts in (
        ("Missing true label\tSentences", missed_counts),
        ("Unexpected predicted label\tSentences", extra_counts),
    ):
        lines.extend(["", heading])
        lines.extend(
            f"{label}\t{count}"
            for label, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        )
    return "\n".join(lines) + "\n"


def main():
    if not PREDICTIONS_PATH.is_file():
        raise SystemExit(f"Run predict.py first to generate {PREDICTIONS_PATH}")

    truth = defaultdict(set)
    for row in read_rows(DATASET_PATH, ("sentence", "true_label")):
        truth[row["sentence"]].add(row["true_label"])
    if not truth:
        raise ValueError(f"{DATASET_PATH.name} contains no annotations")

    predictions = defaultdict(dict)
    for row in read_rows(PREDICTIONS_PATH, ("sentence", "predicted_label", "prediction_score")):
        sentence, label = row["sentence"], row["predicted_label"]
        if sentence not in truth:
            raise ValueError(f"{PREDICTIONS_PATH.name} contains a sentence absent from {DATASET_PATH.name}")
        score = float(row["prediction_score"])
        if not 0 <= score <= 1:
            raise ValueError(f"Prediction scores must be between 0 and 1, got {score}")
        if label in predictions[sentence]:
            raise ValueError(f"{PREDICTIONS_PATH.name} contains a duplicate sentence-label prediction")
        predictions[sentence][label] = score

    report = build_report(truth, predictions)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report, end="")
    print(f"Saved evaluation to {REPORT_PATH}")


if __name__ == "__main__":
    main()
