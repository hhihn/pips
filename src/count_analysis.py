import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import re

sns.set_theme(style="whitegrid", font="DejaVu Sans", context="talk")
plt.rcParams["axes.grid.axis"] = "x"


# ---------------- helpers ----------------
def extract_code_prefix(code: str, level: int | None = None) -> str:
    if not isinstance(code, str):
        return "OTHER"
    parts = re.findall(r"\d+", code)
    if not parts:
        return "OTHER"
    if level is None or level >= len(parts):
        return ".".join(parts)
    return ".".join(parts[:level])


def parse_time_to_seconds(t: str) -> float:
    if pd.isna(t) or not isinstance(t, str):
        return 0.0
    t = t.strip().replace(",", ".")
    parts = t.split(":")
    if len(parts) == 3:
        h, m, s = map(float, parts)
        return h * 3600 + m * 60 + s
    if len(parts) == 2:
        m, s = map(float, parts)
        return m * 60 + s
    return float(parts[0])


def intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


# ---------------- core analysis ----------------
def stacked_occurrence_plot(
    csv_path: str,
    codes: list[list],
    group_labels: list[str],
    code_labels_de: dict,
    code_labels_en: dict,
    language: str = "de",
):
    """language='de' oder 'en'"""
    if language not in ["de", "en"]:
        raise ValueError("language must be 'de' or 'en'")

    if len(codes) != len(group_labels):
        raise ValueError("codes and group_labels must have same length")

    # die Labels je nach Sprache wählen
    code_labels = code_labels_de if language == "de" else code_labels_en

    # ---------------- load data ----------------
    df = pd.read_csv(csv_path)
    df.drop(df[df["Sequence_Code"].str.contains(" AK", na=False)].index, inplace=True)
    df["CodePrefix"] = df["Sequence_Code"].apply(extract_code_prefix)
    df["start_sec"] = df["Sequence_Start"].apply(parse_time_to_seconds)
    df["end_sec"] = df["Sequence_End"].apply(parse_time_to_seconds)

    stacked_data = []
    for group_idx, code_group in enumerate(codes):
        group_label = (
            group_labels[group_idx] if language == "de" else group_labels_en[group_idx]
        )
        exclude_map = {}
        for item in code_group:
            if isinstance(item, list):
                a, b = item
                exclude_map.setdefault(a, []).append(b)
        for code_spec in code_group:
            if isinstance(code_spec, str):
                total_count = 0
                excluded_partners = exclude_map.get(code_spec, [])
                for fid, sub_id in df.groupby("id"):
                    a_rows = sub_id[sub_id["CodePrefix"] == code_spec]
                    if a_rows.empty:
                        continue
                    if not excluded_partners:
                        total_count += len(a_rows)
                        continue
                    b_rows = sub_id[sub_id["CodePrefix"].isin(excluded_partners)]
                    for _, a in a_rows.iterrows():
                        if b_rows.empty:
                            total_count += 1
                        else:
                            if not any(
                                intervals_overlap(
                                    a["start_sec"],
                                    a["end_sec"],
                                    b["start_sec"],
                                    b["end_sec"],
                                )
                                for _, b in b_rows.iterrows()
                            ):
                                total_count += 1
                stacked_data.append(
                    {
                        "Group": group_label,
                        "Code": code_labels.get(code_spec, code_spec),
                        "Cout": total_count,
                    }
                )
            elif isinstance(code_spec, list):
                code_a, code_b = code_spec
                co_counts = []
                for fid, sub_id in df.groupby("id"):
                    a_rows = sub_id[sub_id["CodePrefix"] == code_a]
                    b_rows = sub_id[sub_id["CodePrefix"] == code_b]
                    if a_rows.empty or b_rows.empty:
                        co_counts.append(0)
                        continue
                    count = sum(
                        (a["start_sec"] == b["start_sec"])
                        and (a["end_sec"] == b["end_sec"])
                        for _, a in a_rows.iterrows()
                        for _, b in b_rows.iterrows()
                    )
                    co_counts.append(count)
                mean_count = sum(co_counts) if co_counts else 0
                stacked_data.append(
                    {
                        "Group": group_label,
                        "Code": code_labels.get(
                            tuple(code_spec), " + ".join(code_spec)
                        ),
                        "Cout": mean_count,
                    }
                )

    plot_df = pd.DataFrame(stacked_data)
    pivot = plot_df.pivot_table(
        index="Group",
        columns="Code",
        values="Cout",
        aggfunc="sum",
        fill_value=0,
    )

    if language == "de":
        pivot = pivot.reindex(group_labels)
    else:
        pivot = pivot.reindex(group_labels_en)

    ax = pivot.plot(
        kind="bar",
        stacked=True,
        figsize=(11, 6),
        colormap="Set2",
        edgecolor="black",
    )

    ax.legend_.remove()
    ax.grid(axis="x", visible=False)

    for bar_idx, group in enumerate(pivot.index):
        cumulative = 0
        for code in pivot.columns:
            value = pivot.loc[group, code]
            if value <= 0:
                continue
            ax.text(
                bar_idx,
                cumulative + value / 2,
                code,
                ha="center",
                va="center",
                fontsize=11,
                rotation=0,
            )
            cumulative += value

    if language == "de":
        ax.set_ylabel("Häufigkeiten")
    else:
        ax.set_ylabel("Frequencies")

    ax.set_xlabel("")
    ax.set_title("")
    ax.set_yticks([10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 110, 120, 130, 140, 150])
    plt.xticks(rotation=0)
    plt.tight_layout()
    plt.show()


# ---------------- example run ----------------
if __name__ == "__main__":
    csv_file = "extracted_sequences.csv"
    codes = [
        ["6.4.3", "6.4.4", "6.4.5"],
        [["2.2.3.14", "2.2.3.4"], "2.2.3.14"],
        #    ["2.2.4.2", "2.2.4.3"],
    ]

    group_labels = [
        "Körperliche Ausrichtung FK",
        "Typ Körperkontakt",
        #      "Art Körperkontakt",
    ]
    group_labels_en = [
        "Physical orientation\nCaregiver",
        "Type of body contact",
        #     "Kind of body contact",
    ]

    code_labels_de = {
        "6.4.1": "fordert zur PH auf",
        "6.4.2": "fordert zur VB/NB auf",
        "6.4.3": "von vorn",
        "6.4.4": "seitlich",
        "6.4.5": "von hinten",
        "2.2.3.14": "Berührung durch\nPflege-\ngegenstand\nohne Halten",
        ("2.2.3.14", "2.2.3.4"): "Halten und\nBerührung\ndurch Pflege-\ngegenstand",
        "2.2.4.2": "neutral",
        "2.2.4.3": "unsanft",
    }

    code_labels_en = {
        "6.4.1": "call to CS",
        "6.4.2": "call to prep",
        "6.4.3": "from the front",
        "6.4.4": "sideways",
        "6.4.5": "from behind",
        "2.2.3.14": "Touch by care\nitem\nwithout holding",
        ("2.2.3.14", "2.2.3.4"): "Holding and\ntouch by\ncare item",
        "2.2.4.2": "neutral",
        "2.2.4.3": "rough",
    }

    stacked_occurrence_plot(
        csv_file,
        codes,
        group_labels,
        code_labels_de,
        code_labels_en,
        language="de",
    )
