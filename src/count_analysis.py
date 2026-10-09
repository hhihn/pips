"""Häufigkeiten von FK-Ausrichtung und Körperkontakt nach Pflegesituation.

Die Analyse unterscheidet die Pflegesituationen anhand der Sequenzcodes
6.2.1 (Nase putzen) und 6.2.2 (Gesicht abwischen).  Berücksichtigt werden nur
Orientierungen bzw. Kontakte, die zeitlich mit einem solchen Handlungsintervall
überlappen.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
import warnings

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns


sns.set_theme(style="whitegrid", font="DejaVu Sans", context="talk")
plt.rcParams["axes.grid.axis"] = "x"

SITUATIONS = {
    "6.2.1": "Nase putzen",
    "6.2.2": "Gesicht abwischen",
}
ORIENTATION_CODES = {
    "6.4.3": "von vorn",
    "6.4.4": "seitlich",
    "6.4.5": "von hinten",
}
@dataclass(frozen=True)
class CodeCategory:
    """Definition einer Kategorie innerhalb einer Balkengruppe.

    ``codes`` werden standardmäßig alternativ interpretiert: Ein Ereignis mit
    einem dieser Codes wird gezählt. Für zusammengesetzte Kategorien kann
    ``require_same_interval`` gesetzt werden; dann müssen alle Codes mit
    identischem Start- und Endzeitpunkt vorliegen. ``exclude_overlapping_codes``
    schließt ein Ereignis aus, sobald einer dieser Codes zeitlich überlappt.
    """

    codes: tuple[str, ...]
    require_same_interval: bool = False
    exclude_overlapping_codes: tuple[str, ...] = ()


# Diese Konfiguration kann an ``run_analysis(..., code_groups=...)`` übergeben
# werden. Die Kurzform ``{"Kategorie": "6.4.3"}`` bzw. eine Code-Liste ist
# ebenfalls erlaubt. Sie zählt jedes passende Ereignis genau einmal.
CODE_GROUPS = {
    "Orientierung FK": {
        label: CodeCategory((code,)) for code, label in ORIENTATION_CODES.items()
    },
    "Art des Kontakts": {
        "Halten und Berührung durch Pflegegegenstand": CodeCategory(
            ("2.2.3.14", "2.2.3.4"), require_same_interval=True
        ),
        "Berührung durch Pflegegegenstand ohne Halten": CodeCategory(
            ("2.2.3.14",), exclude_overlapping_codes=("2.2.3.4",)
        ),
    },
    "Kind Handlungen": {
        "K führt Pflegehandlung eigenständig durch": CodeCategory(("6.5.3",)),
        "K führt Pflege-Vor/Nachbereitung eigenständig durch": CodeCategory(("6.5.4",)),
    }
}
DISPLAY_LABELS = {
    "Halten und Berührung durch Pflegegegenstand": "Halten und\nBerührung durch\nPflegegegenstand",
    "Berührung durch Pflegegegenstand ohne Halten": "Berührung durch\nPflegegegenstand\nohne Halten",
    "K führt Pflegehandlung eigenständig durch": "K führt Pflegehandlung\neigenständig durch",
    "K führt Pflege-Vor/Nachbereitung eigenständig durch": "K führt Pflege-Vor/Nachbereitung\neigenständig durch"
}


def _normalise_code_groups(
    code_groups: Mapping[str, Mapping[str, CodeCategory | str | Iterable[str]]],
) -> dict[str, dict[str, CodeCategory]]:
    """Normalisiert die kompakte öffentliche Konfiguration zu ``CodeCategory``."""
    result: dict[str, dict[str, CodeCategory]] = {}
    for group, categories in code_groups.items():
        if not categories:
            raise ValueError(f"Die Gruppe {group!r} enthält keine Kategorien.")
        result[group] = {}
        for label, definition in categories.items():
            if isinstance(definition, CodeCategory):
                category = definition
            elif isinstance(definition, str):
                category = CodeCategory((definition,))
            else:
                category = CodeCategory(tuple(definition))
            if not category.codes:
                raise ValueError(f"Die Kategorie {label!r} enthält keine Codes.")
            result[group][label] = CodeCategory(
                tuple(extract_code_prefix(code) for code in category.codes),
                category.require_same_interval,
                tuple(extract_code_prefix(code) for code in category.exclude_overlapping_codes),
            )
    return result


def _normalise_situations(situations: Mapping[str, str]) -> dict[str, str]:
    if not situations:
        raise ValueError("Es muss mindestens eine Auswertungssituation angegeben werden.")
    return {extract_code_prefix(code): label for code, label in situations.items()}


def extract_code_prefix(code: str) -> str:
    """Entfernt Zusatztexte wie ``PK`` von einem Sequenzcode."""
    if not isinstance(code, str):
        return "OTHER"
    parts = re.findall(r"\d+", code)
    return ".".join(parts) if parts else "OTHER"


def parse_time_to_seconds(value: str) -> float:
    if pd.isna(value) or not isinstance(value, str):
        return 0.0
    parts = value.strip().replace(",", ".").split(":")
    if len(parts) == 3:
        hours, minutes, seconds = map(float, parts)
        return hours * 3600 + minutes * 60 + seconds
    if len(parts) == 2:
        minutes, seconds = map(float, parts)
        return minutes * 60 + seconds
    return float(parts[0])


def intervals_overlap(a_start, a_end, b_start, b_end) -> bool:
    return max(a_start, b_start) < min(a_end, b_end)


def load_sequences(csv_path: str | Path) -> pd.DataFrame:
    """Lädt und normalisiert die für die Auswertung benötigten Spalten."""
    df = pd.read_csv(csv_path)
    df["CodePrefix"] = df["Sequence_Code"].map(extract_code_prefix)
    df["start_sec"] = df["Sequence_Start"].map(parse_time_to_seconds)
    df["end_sec"] = df["Sequence_End"].map(parse_time_to_seconds)
    return df


def _situation_intervals(df: pd.DataFrame, situations: Mapping[str, str]) -> pd.DataFrame:
    """Eindeutige Handlungsintervalle, einschließlich AK-Situationsmarkern."""
    return df.loc[df["CodePrefix"].isin(_normalise_situations(situations))].drop_duplicates(
        subset=["Filename", "CodePrefix", "start_sec", "end_sec"]
    ).reset_index(drop=True)


def warn_on_mixed_situations(df: pd.DataFrame, situations: Mapping[str, str]) -> None:
    """Warnt, wenn eine Auswertungseinheit Nase und Gesicht enthält."""
    situation_rows = df[df["CodePrefix"].isin(_normalise_situations(situations))]
    mixed = situation_rows.groupby("id")["CodePrefix"].nunique()
    mixed_ids = mixed[mixed > 1].index.tolist()
    if mixed_ids:
        message = (
            "Achtung: In folgenden id kommen mehrere Auswertungssituationen vor: "
            f"{', '.join(map(str, mixed_ids))}. Die Handlungsintervalle werden dennoch "
            "getrennt ausgewertet."
        )
        warnings.warn(message, UserWarning, stacklevel=2)


def _overlaps_situation(row: pd.Series, situation: pd.Series) -> bool:
    return intervals_overlap(
        row["start_sec"], row["end_sec"], situation["start_sec"], situation["end_sec"]
    )


def _same_interval_codes(event: pd.Series, rows: pd.DataFrame) -> set[str]:
    """Liefert alle Codes, die genau dasselbe Intervall wie ``event`` belegen."""
    same_interval = rows[
        (rows["start_sec"] == event["start_sec"]) & (rows["end_sec"] == event["end_sec"])
    ]
    return set(same_interval["CodePrefix"])


def _matches_category(event: pd.Series, rows: pd.DataFrame, category: CodeCategory) -> bool:
    if event["CodePrefix"] not in category.codes:
        return False
    # Bei einer zusammengesetzten Kategorie ist der erste Code das gezählte
    # Leit-Ereignis. So wird ein gemeinsames Intervall nicht doppelt gezählt.
    if category.require_same_interval and event["CodePrefix"] != category.codes[0]:
        return False
    if category.require_same_interval and not set(category.codes).issubset(
        _same_interval_codes(event, rows)
    ):
        return False
    return not any(
        intervals_overlap(event["start_sec"], event["end_sec"], other["start_sec"], other["end_sec"])
        for _, other in rows[rows["CodePrefix"].isin(category.exclude_overlapping_codes)].iterrows()
    )


def extract_raw_counts(
    df: pd.DataFrame,
    situations: Mapping[str, str] = SITUATIONS,
    code_groups: Mapping[str, Mapping[str, CodeCategory | str | Iterable[str]]] = CODE_GROUPS,
) -> pd.DataFrame:
    """Erzeugt eine Zeile pro gezählter Sequenz für die spätere Weiterverarbeitung."""
    rows: list[dict] = []
    normalised_groups = _normalise_code_groups(code_groups)
    normalised_situations = _normalise_situations(situations)
    for situation_index, (_, situation) in enumerate(
        _situation_intervals(df, situations).iterrows()
    ):
        same_id = df[
            (df["id"] == situation["id"])
            & (df["Filename"] == situation["Filename"])
            & ~df["Sequence_Code"].str.contains(" AK", na=False)
        ]
        base = {
            "Situation_Index": situation_index,
            "Situation": normalised_situations[situation["CodePrefix"]],
            "Situation_Code": situation["CodePrefix"],
            "id": situation["id"],
            "Filename": situation["Filename"],
            "Situation_Start": situation["Sequence_Start"],
            "Situation_End": situation["Sequence_End"],
        }

        for group, categories in normalised_groups.items():
            for label, category in categories.items():
                for _, event in same_id[same_id["CodePrefix"].isin(category.codes)].iterrows():
                    if _overlaps_situation(event, situation) and _matches_category(
                        event, same_id, category
                    ):
                        rows.append(
                            base | {
                                "Gruppe": group,
                                "Code": " + ".join(category.codes),
                                "Kategorie": label,
                                "Sequence_Start": event["Sequence_Start"],
                                "Sequence_End": event["Sequence_End"],
                            }
                        )

    return pd.DataFrame(
        rows,
        columns=[
            "Situation_Index", "Situation", "Situation_Code", "id", "Filename", "Situation_Start",
            "Situation_End", "Gruppe", "Code", "Kategorie", "Sequence_Start", "Sequence_End",
        ],
    )


def extract_situation_counts(
    df: pd.DataFrame,
    situations: Mapping[str, str] = SITUATIONS,
    code_groups: Mapping[str, Mapping[str, CodeCategory | str | Iterable[str]]] = CODE_GROUPS,
    *,
    raw_data: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Eine Zeile pro Handlungsintervall, mit Gruppierung und Kategorieanzahlen.

    Auch Intervalle ohne passende Ereignisse bleiben mit Nullwerten erhalten.
    Die Spaltennamen kombinieren Gruppe und Kategorie, damit gleiche Labels
    in unterschiedlichen Codegruppen getrennt ausgewertet werden können.
    """
    normalised_situations = _normalise_situations(situations)
    groups = _normalise_code_groups(code_groups)
    intervals = _situation_intervals(df, situations)
    result = intervals[["Filename", "id", "Sequence_Start", "Sequence_End"]].rename(
        columns={"Sequence_Start": "Situation_Start", "Sequence_End": "Situation_End"}
    )
    result.insert(0, "Situation_Index", range(len(intervals)))
    result["Situation_Code"] = intervals["CodePrefix"]
    result["Situation"] = intervals["CodePrefix"].map(normalised_situations)
    if raw_data is None:
        raw_data = extract_raw_counts(df, situations, code_groups)
    for group, categories in groups.items():
        for label in categories:
            counts = raw_data.loc[
                (raw_data["Gruppe"] == group) & (raw_data["Kategorie"] == label)
            ].groupby("Situation_Index").size()
            result[f"{group}: {label}"] = (
                result["Situation_Index"].map(counts).fillna(0).astype(int)
            )
    return result


def _categories(code_groups: Mapping[str, Mapping[str, object]]) -> list[str]:
    return [label for group in code_groups.values() for label in group]


def _safe_filename(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def plot_situation(
    raw_data: pd.DataFrame,
    situation: str,
    output_dir: Path,
    code_groups: Mapping[str, Mapping[str, CodeCategory | str | Iterable[str]]] = CODE_GROUPS,
) -> Path:
    """Erstellt ein Diagramm mit den nebeneinanderliegenden Gruppen einer Situation."""
    categories = _categories(code_groups)
    group_order = list(code_groups)
    subset = raw_data[raw_data["Situation"] == situation]
    counts = (
        subset.groupby(["Gruppe", "Kategorie"], observed=False)
        .size()
        .unstack(fill_value=0)
        .reindex(index=group_order, columns=categories, fill_value=0)
    )

    ax = counts.plot(
        kind="bar", stacked=True, figsize=(11, 6), colormap="Set2", edgecolor="black"
    )
    ax.legend_.remove()
    ax.grid(axis="x", visible=False)
    for bar_index, group in enumerate(counts.index):
        cumulative = 0
        for category in counts.columns:
            value = counts.loc[group, category]
            if value:
                ax.text(
                    bar_index,
                    cumulative + value / 2,
                    DISPLAY_LABELS.get(category, category),
                    ha="center",
                    va="center",
                    fontsize=10,
                )
                cumulative += value
    ax.set_ylabel("Häufigkeiten")
    ax.set_xlabel("")
    ax.set_title(situation)
    ax.set_xticklabels(counts.index, rotation=0)
    plt.tight_layout()
    output_path = output_dir / f"stacked_bar_{_safe_filename(situation)}.png"
    ax.figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(ax.figure)
    return output_path


def plot_situation_comparison(
    raw_data: pd.DataFrame,
    output_dir: Path,
    situations: Mapping[str, str] = SITUATIONS,
    code_groups: Mapping[str, Mapping[str, CodeCategory | str | Iterable[str]]] = CODE_GROUPS,
) -> Path:
    """Vergleicht alle übergebenen Situationen innerhalb jeder Gruppe."""
    categories = _categories(code_groups)
    group_order = list(code_groups)
    situation_labels = list(_normalise_situations(situations).values())
    counts = (
        raw_data.groupby(["Gruppe", "Situation", "Kategorie"], observed=False)
        .size()
        .reindex(
            pd.MultiIndex.from_product(
                [group_order, situation_labels, categories],
                names=["Gruppe", "Situation", "Kategorie"],
            ),
            fill_value=0,
        )
    )

    palette = plt.get_cmap("Set2").colors
    colors = {category: palette[index % len(palette)] for index, category in enumerate(categories)}
    group_centers = range(len(group_order))
    width = min(0.8 / len(situation_labels), 0.4)
    offsets = {
        situation: (index - (len(situation_labels) - 1) / 2) * width
        for index, situation in enumerate(situation_labels)
    }
    fig, ax = plt.subplots(figsize=(12, 7))

    for group_index, group in enumerate(group_order):
        for situation in situation_labels:
            bar_x = group_index + offsets[situation]
            cumulative = 0
            for category in categories:
                value = counts.loc[(group, situation, category)]
                if not value:
                    continue
                ax.bar(bar_x, value, width=width, bottom=cumulative, color=colors[category], edgecolor="black")
                ax.text(
                    bar_x,
                    cumulative + value / 2,
                    DISPLAY_LABELS.get(category, category),
                    ha="center",
                    va="center",
                    fontsize=9,
                )
                cumulative += value
            ax.text(
                bar_x,
                -0.08,
                situation,
                transform=ax.get_xaxis_transform(),
                ha="center",
                va="top",
                fontsize=11,
            )

    ax.set_xticks(list(group_centers), group_order)
    ax.set_ylabel("Häufigkeiten")
    ax.set_title("Vergleich der Auswertungssituationen")
    ax.grid(axis="x", visible=False)
    fig.tight_layout()
    output_path = output_dir / "stacked_bar_nase_und_gesicht.png"
    fig.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.show()
    plt.close(fig)
    return output_path


def run_analysis(
    csv_path: str | Path,
    output_dir: str | Path | None = None,
    *,
    situations: Mapping[str, str] = SITUATIONS,
    code_groups: Mapping[str, Mapping[str, CodeCategory | str | Iterable[str]]] = CODE_GROUPS,
) -> pd.DataFrame:
    """Führt eine konfigurierbare Häufigkeitsauswertung aus.

    ``count_analysis_situation_counts.csv`` enthält ein Handlungsintervall pro
    Zeile und eine numerische Spalte pro Kategorie. ``Situation`` dient als
    Gruppierungsvariable, ``Situation_Code`` enthält den zugehörigen Code.
    Die Rückgabe bleibt die ereignisweise Rohdatentabelle.

    Beispiel::

        run_analysis(
            "sequenzen.csv",
            situations={"6.2.1": "Nase putzen", "6.2.2": "Gesicht abwischen"},
            code_groups={"Orientierung": {"von vorn": "6.4.3", "seitlich": "6.4.4"}},
        )
    """
    csv_path = Path(csv_path)
    output_dir = Path(output_dir) if output_dir else csv_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    df = load_sequences(csv_path)
    warn_on_mixed_situations(df, situations)
    raw_data = extract_raw_counts(df, situations, code_groups)
    raw_data.to_csv(output_dir / "count_analysis_raw_data.csv", index=False)
    situation_counts = extract_situation_counts(
        df, situations, code_groups, raw_data=raw_data
    )
    situation_counts.to_csv(
        output_dir / "count_analysis_situation_counts.csv", index=False, encoding="utf-8-sig"
    )
    for situation in situations.values():
        plot_situation(raw_data, situation, output_dir, code_groups)
    plot_situation_comparison(raw_data, output_dir, situations, code_groups)
    return raw_data


if __name__ == "__main__":
    run_analysis(Path(__file__).with_name("extracted_sequences.csv"))
