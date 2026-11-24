"""Plot German sentence embeddings in two dimensions, colored by annotated code."""

import csv
from collections import defaultdict
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import seaborn as sns
from matplotlib.lines import Line2D
from matplotlib.path import Path as MarkerPath


OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"
DATASET_PATH = OUTPUT_DIR / "zero_shot_dataset.csv"
FIGURE_PATH = OUTPUT_DIR / "zero_shot_sentence_umap"
MODEL_ID = "T-Systems-onsite/german-roberta-sentence-transformer-v2"
DEVICE = None  # Let Sentence Transformers select the device.
SEED = 42
N_NEIGHBORS = 20
MIN_DIST = 0.12
BATCH_SIZE = 32


def read_annotations(path):
    codes_by_sentence = defaultdict(set)
    with path.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if not {"sentence", "code"}.issubset(reader.fieldnames or []):
            raise ValueError("The dataset must contain sentence and code columns")
        for row in reader:
            sentence, code = row["sentence"], row["code"]
            if not sentence or not code:
                raise ValueError(f"Missing sentence or code at CSV line {reader.line_num}")
            codes_by_sentence[sentence].add(code)
    return codes_by_sentence


def project_sentences(sentences):
    from sentence_transformers import SentenceTransformer
    from umap import UMAP

    model = SentenceTransformer(MODEL_ID, device=DEVICE)
    embeddings = model.encode(
        sentences, batch_size=BATCH_SIZE, normalize_embeddings=True, show_progress_bar=True
    )
    return UMAP(
        n_components=2,
        n_neighbors=min(N_NEIGHBORS, len(sentences) - 1),
        min_dist=MIN_DIST,
        metric="cosine",
        init="random",
        random_state=SEED,
    ).fit_transform(embeddings)


def wedge_marker(index, count):
    start = 90 - 360 * (index + 1) / count
    end = 90 - 360 * index / count
    wedge = MarkerPath.wedge(start, end)
    # Invisible corners keep the marker scale identical for every wedge.
    return MarkerPath(
        np.vstack((wedge.vertices, [[-1, -1], [1, 1]])),
        np.append(wedge.codes, [MarkerPath.MOVETO, MarkerPath.MOVETO]),
    )


def plot_projection(coordinates, codes_by_sentence, figure_path):
    codes = sorted({code for labels in codes_by_sentence.values() for code in labels})
    colors = dict(zip(codes, sns.husl_palette(len(codes)), strict=True))
    groups = defaultdict(list)
    for point, labels in zip(coordinates, codes_by_sentence.values(), strict=True):
        for index, code in enumerate(sorted(labels)):
            groups[code, index, len(labels)].append(point)

    sns.set_theme(context="paper", style="white", font_scale=1.15, rc={"pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(13, 8.5), layout="constrained")
    for (code, index, count), points in groups.items():
        x, y = np.asarray(points).T
        ax.scatter(
            x, y, marker=wedge_marker(index, count), s=43, color=colors[code],
            linewidths=0.12, edgecolors="white", alpha=0.88,
        )

    legend = [
        Line2D([], [], marker="o", linestyle="none", color=colors[code], label=code, markersize=5)
        for code in codes
    ]
    ax.legend(
        handles=legend, title="Annotated code", loc="center left",
        bbox_to_anchor=(1.02, 0.5), ncols=2, frameon=False, fontsize=8,
    )
    ax.set(
        title=f"German sentence embeddings (n = {len(coordinates):,})",
        xlabel="UMAP 1", ylabel="UMAP 2",
    )
    ax.set_aspect("equal", adjustable="datalim")
    ax.margins(0.05)
    sns.despine(ax=ax)
    figure_path.parent.mkdir(parents=True, exist_ok=True)
    for extension in (".pdf", ".png"):
        fig.savefig(figure_path.with_suffix(extension), dpi=400, bbox_inches="tight")
    plt.close(fig)


def main():
    codes_by_sentence = read_annotations(DATASET_PATH)
    if len(codes_by_sentence) < 3:
        raise ValueError("At least three distinct sentences are required for UMAP")
    coordinates = project_sentences(list(codes_by_sentence))
    plot_projection(coordinates, codes_by_sentence, FIGURE_PATH)
    print(f"Saved the projection for {len(coordinates)} sentences as {FIGURE_PATH}.pdf and .png")


if __name__ == "__main__":
    main()
