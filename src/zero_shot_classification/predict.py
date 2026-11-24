"""Predict labels above a score threshold with facebook/bart-large-mnli."""

import csv
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODEL_ID = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
INPUT_PATH = PROJECT_ROOT / "output/zero_shot_dataset.csv"
OUTPUT_PATH = PROJECT_ROOT / "output/zero_shot_predictions.csv"
THRESHOLD = 0.0
BATCH_SIZE = 32
DEVICE = "auto"  # "auto", "cpu", "mps", or a CUDA device such as "cuda:0"

# Choose fields in the order they should appear in the model's candidate labels.
LABEL_FIELDS = ("code",)
LABEL_SEPARATOR = " > "
MAX_LABEL_CHARS = 100
AVAILABLE_LABEL_FIELDS = {"dimension", "aspekt", "facette", "code"}


def load_classifier(device):
    import torch
    from transformers import pipeline

    if device == "auto":
        if torch.cuda.is_available():
            device = "cuda"
        elif torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"
    print(f"Loading classifier on {device}", flush=True)
    return pipeline("zero-shot-classification", model=MODEL_ID, device=device)


def build_candidates(rows):
    if not LABEL_FIELDS or not set(LABEL_FIELDS).issubset(AVAILABLE_LABEL_FIELDS):
        raise ValueError("LABEL_FIELDS must select from dimension, aspekt, facette, and code")

    codes_by_candidate = {}
    for row in rows:
        full_label = LABEL_SEPARATOR.join(row[field] for field in LABEL_FIELDS if row[field])
        candidate = full_label[-MAX_LABEL_CHARS:]
        code = row["code"]
        if candidate:
            codes_by_candidate.setdefault(candidate, set()).add(code)
    if not codes_by_candidate:
        raise ValueError("The selected LABEL_FIELDS contain no candidate label text")
    return codes_by_candidate


def predict_sentences(classifier, sentences, codes_by_candidate, batch_size, threshold):
    labels = sorted(codes_by_candidate)
    for start in range(0, len(sentences), batch_size):
        batch = sentences[start:start + batch_size]
        results = classifier(
            batch, candidate_labels=labels, multi_label=True, batch_size=batch_size
        )
        for sentence, result in zip(batch, results, strict=True):
            scores_by_code = {}
            for candidate, score in zip(result["labels"], result["scores"], strict=True):
                if score > threshold:
                    for code in sorted(codes_by_candidate[candidate]):
                        scores_by_code[code] = max(score, scores_by_code.get(code, score))
            for code, score in scores_by_code.items():
                yield sentence, code, score
        print(f"Classified {start + len(batch)}/{len(sentences)} unique sentences", flush=True)


def main():
    if BATCH_SIZE < 1:
        raise ValueError("BATCH_SIZE must be at least 1")
    if not 0.0 <= THRESHOLD <= 1.0:
        raise ValueError("THRESHOLD must be between 0 and 1")
    if INPUT_PATH.resolve() == OUTPUT_PATH.resolve() or (
        OUTPUT_PATH.exists() and INPUT_PATH.exists() and OUTPUT_PATH.samefile(INPUT_PATH)
    ):
        raise ValueError("OUTPUT_PATH must point to a different file than INPUT_PATH")

    with INPUT_PATH.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        required_fields = {"sentence", "code", *LABEL_FIELDS}
        missing_fields = required_fields.difference(reader.fieldnames or [])
        if missing_fields:
            raise ValueError(f"Input CSV is missing columns: {', '.join(sorted(missing_fields))}")
        rows = list(reader)
    if not rows or any(not (row[field] or "").strip() for row in rows for field in ("sentence", "code")):
        raise ValueError("Input CSV must contain rows with non-empty sentences and codes")

    codes_by_candidate = build_candidates(rows)
    sentences = list(dict.fromkeys(row["sentence"] for row in rows))
    classifier = load_classifier(DEVICE)
    predictions = list(
        predict_sentences(classifier, sentences, codes_by_candidate, BATCH_SIZE, THRESHOLD)
    )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["sentence", "predicted_label", "prediction_score"])
        writer.writerows(predictions)

    print(
        f"Wrote {len(predictions)} predictions above {THRESHOLD} "
        f"from {len(sentences)} sentences and {len(codes_by_candidate)} candidate labels to {OUTPUT_PATH}"
    )


if __name__ == "__main__":
    main()
