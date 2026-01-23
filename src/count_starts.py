import pandas as pd
import matplotlib.pyplot as plt
from collections import Counter


def parse_time_to_seconds(t: str) -> float:
    """Konvertiert 'mm:ss,ms' oder 'hh:mm:ss,ms' nach Sekunden."""
    if pd.isna(t) or not isinstance(t, str):
        return 0.0
    t = t.replace(",", ".")
    parts = [float(x) for x in t.split(":")]
    if len(parts) == 3:
        h, m, s = parts
        return h * 3600 + m * 60 + s
    if len(parts) == 2:
        m, s = parts
        return m * 60 + s
    return parts[0]


def find_most_common_start_combinations(csv_path: str, top_n: int = 10):
    """
    Liest eine CSV, findet pro Datei die ersten zwei Sequenzen,
    die während 6.1.1 PK auftreten, und zählt die häufigsten Kombinationen.
    """
    df = pd.read_csv(csv_path)
    # Zeitspalten in Sekunden umwandeln und sortieren
    df["start_sec"] = df["Sequence_Start"].apply(parse_time_to_seconds)
    df["end_sec"] = df["Sequence_End"].apply(parse_time_to_seconds)
    df = df.sort_values(["Filename", "start_sec"]).reset_index(drop=True)

    combos = []

    # Gruppieren nach Datei oder id
    group_col = "id" if "id" in df.columns else "Filename"
    for fid, sub in df.groupby(group_col):
        # alle 6.1.1 PK - Intervalle
        six_rows = sub[sub["Sequence_Code"] == "6.1.1 PK"]
        if six_rows.empty:
            continue
        for _, six in six_rows.iterrows():
            s_start, s_end = six["start_sec"], six["end_sec"]
            # alle Ereignisse, die während 6.1.1 passieren (außer 6.1.1 selbst)
            inside = sub[
                (sub["start_sec"] >= s_start)
                & (sub["end_sec"] <= s_end)
                & (sub["Sequence_Code"] != "6.1.1 PK")
                ].sort_values("start_sec")

            if len(inside) >= 2:
                first_two = inside.head(2)["Sequence_Code"].tolist()
                # entferne evtl. ' PK' am Ende, falls nicht gewünscht
                first_two = [c.replace(" PK", "") for c in first_two]
                combos.append(tuple(first_two))

    # Häufigkeiten
    freq = Counter(combos)
    if not freq:
        print("Keine Startkombinationen gefunden.")
        return

    top = freq.most_common(top_n)
    labels = [f"{a}\n{b}" for (a, b), _ in top]
    values = [v for _, v in top]

    # Visualisierung
    plt.figure(figsize=(8, 6))
    bars = plt.barh(range(len(top)), values, color="skyblue", edgecolor="black")
    plt.yticks(range(len(top)), labels, fontsize=11)
    plt.xlabel("Anzahl (über alle Dateien)", fontsize=12)
    plt.ylabel("Erste 2 Codes während 6.1.1", fontsize=12)
    plt.title("Häufigste Anfangskombinationen (während 6.1.1)", fontsize=14)
    for bar, val in zip(bars, values):
        plt.text(bar.get_width() + 0.1, bar.get_y() + bar.get_height() / 2,
                 str(val), va='center', fontsize=11)
    plt.tight_layout()
    plt.show()
    return freq


# Beispielaufruf
if __name__ == "__main__":
    csv_file = "extracted_sequences.csv"
    freq = find_most_common_start_combinations(csv_file)
    print(freq.most_common(10))