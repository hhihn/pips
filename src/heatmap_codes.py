import seaborn as sns
from matplotlib import pyplot as plt
import pandas as pd


def time_to_seconds(time_str: str) -> float:
    """Convert time string like '0:00:29,6' to seconds."""
    if not isinstance(time_str, str) or not time_str.strip():
        return 0.0
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            h, m, s = map(float, parts)
            return h * 3600 + m * 60 + s
        elif len(parts) == 2:
            m, s = map(float, parts)
            return m * 60 + s
    except ValueError:
        pass
    return 0.0


def create_code_heatmap(df: pd.DataFrame, save_path: str = None):
    """
    Create a heatmap showing code occurrence across all situations.
    """
    # Extract base code
    df_copy = df.copy()
    df_copy["base_code"] = df_copy["Sequence_Code"].str.replace(
        " PK| AK", "", regex=True
    )

    # Create pivot table: situations x codes
    pivot = df_copy.groupby(["Filename", "base_code"]).size().unstack(fill_value=0)

    # Convert to binary (present/absent)
    pivot_binary = (pivot > 0).astype(int)

    # Sort codes logically
    sorted_codes = sorted(
        pivot_binary.columns, key=lambda x: [int(p) for p in x.split(".")]
    )
    pivot_binary = pivot_binary[sorted_codes]

    # Create figure
    fig, ax = plt.subplots(figsize=(16, max(8, len(pivot_binary) * 0.3)))

    sns.heatmap(
        pivot_binary,
        cmap="YlOrRd",
        cbar_kws={"label": "Vorhanden"},
        ax=ax,
        linewidths=0.5,
        linecolor="white",
    )

    ax.set_xlabel("Code", fontsize=11)
    ax.set_ylabel("Situation ID", fontsize=11)
    ax.set_title("Code-Vorkommen in Pflegesituationen", fontsize=14, fontweight="bold")

    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.yticks(fontsize=8)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")

    plt.show()
    return fig


def create_phase_duration_boxplot(df: pd.DataFrame, save_path: str = None):
    """
    Create boxplot showing duration distribution by phase (6.1.x codes).
    """
    df_copy = df.copy()
    df_copy["start_sec"] = df_copy["Sequence_Start"].apply(time_to_seconds)
    df_copy["end_sec"] = df_copy["Sequence_End"].apply(time_to_seconds)
    df_copy["duration"] = df_copy["end_sec"] - df_copy["start_sec"]
    df_copy["base_code"] = df_copy["Sequence_Code"].str.replace(
        " PK| AK", "", regex=True
    )

    # Filter for phase codes
    phase_codes = ["6.1.1", "6.1.2", "6.1.3", "6.1.4"]
    phase_df = df_copy[df_copy["base_code"].isin(phase_codes)]

    # Create labels
    phase_labels = {
        "6.1.1": "Gesamt",
        "6.1.2": "Transition\nvorher",
        "6.1.3": "Pflege-\nhandlung",
        "6.1.4": "Transition\nnachher",
    }
    phase_df["phase_label"] = phase_df["base_code"].map(phase_labels)

    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))

    colors = ["#E8E8E8", "#FFE4B5", "#98FB98", "#DDA0DD"]

    sns.boxplot(
        data=phase_df,
        x="phase_label",
        y="duration",
        palette=colors,
        ax=ax,
        order=[
            "Gesamt",
            "Transition\nvorher",
            "Pflege-\nhandlung",
            "Transition\nnachher",
        ],
    )

    ax.set_xlabel("Phase", fontsize=11)
    ax.set_ylabel("Dauer (Sekunden)", fontsize=11)
    ax.set_title("Dauer der Pflegephasen", fontsize=14, fontweight="bold")

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches="tight")

    plt.show()
    return fig


df = pd.read_csv("extracted_sequences.csv")

print("1. Creating code heatmap...")
create_code_heatmap(df, save_path="heatmap_codes.png")
