"""Export annotated Segment and Code pairs for zero-shot classification."""

import argparse
import csv
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CODE_NUMBER = re.compile(r"^\d+(?:\.\d+)*\.?(?:\s+|$)")


def read_annotations(path):
    frame = pd.read_excel(path, usecols=["Segment", "Code"], dtype=str, keep_default_na=False)
    for segment, code in frame[["Segment", "Code"]].itertuples(index=False, name=None):
        sentence = segment.strip()
        parts = [CODE_NUMBER.sub("", part.strip()) for part in code.split(">")]
        label = parts[-1]
        if sentence and label:
            dimension, aspekt, facette = (parts + ["", ""])[:3]
            yield sentence, label, dimension, aspekt, facette, label


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=PROJECT_ROOT / "data")
    parser.add_argument(
        "--output", type=Path, default=PROJECT_ROOT / "output" / "zero_shot_dataset.csv"
    )
    args = parser.parse_args()

    paths = sorted(
        path for path in args.data_dir.glob("*_transformed.xlsx")
        if path.is_file() and not path.name.startswith("~$")
    )
    if not paths:
        parser.error(f"No *_transformed.xlsx workbooks found in {args.data_dir}")

    annotations = [row for path in paths for row in read_annotations(path)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as output:
        writer = csv.writer(output)
        writer.writerow(["sentence", "true_label", "dimension", "aspekt", "facette", "code"])
        writer.writerows(annotations)

    label_count = len({row[1] for row in annotations})
    print(f"Wrote {len(annotations)} annotations with {label_count} distinct labels to {args.output}")


if __name__ == "__main__":
    main()
