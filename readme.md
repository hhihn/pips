# PIPS – Analyse von Pflegesituationen

PIPS extrahiert codierte Pflegesituationen aus MAXQDA-Excel-Exporten. Die extrahierten Sequenzen dienen als Grundlage für die Optimal-Matching-Analyse (OMA). Die Interrater-Analyse liest die Excel-Exporte beider Personen direkt ein.

## Voraussetzungen

Die Beispiele setzen Python 3.10 oder neuer und eine virtuelle Umgebung unter `.venv/` voraus. Die Befehlsblöcke werden vom Projektverzeichnis aus gestartet.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install pandas numpy openpyxl scipy scikit-learn \
  matplotlib seaborn plotly statsmodels pytest
```

Für ältere `.xls`-Dateien zusätzlich `xlrd` installieren.

## 1. Daten extrahieren

Die Excel-Dateien der ersten kodierenden Person liegen direkt in `data/`. Das erste Tabellenblatt enthält mindestens die Spalten `Code`, `Anfang` und `Ende`. Beim Transformieren bleibt jeweils der letzte Eintrag des MAXQDA-Codepfads erhalten.

```sh
.venv/bin/python -B transform_data.py
(
  cd src
  ../.venv/bin/python -B detect_codes_within.py --input-dir ../data/transformed
  ../.venv/bin/python -B analyse_order.py
  ../.venv/bin/python -B count_analysis.py
  ../.venv/bin/python -B create_row_view.py
)
```

Der explizite Eingabepfad ist wichtig. `detect_codes_within.py` verwendet ohne `--input-dir` derzeit `data/interrater_data_raw/transformed/`. Der vorhandene [Pipeline-Runner](run_pipeline.py) übernimmt diesen Standardpfad, während die anschließende Sequenzordnung aus `data/transformed/analysis_results/` liest. Die Häufigkeitsanalyse öffnet Diagrammfenster, die vor dem nächsten Schritt geschlossen werden müssen.

| Schritt | Ausgabe |
| --- | --- |
| Transformation | Excel-Dateien unter `data/transformed/` |
| Sequenzextraktion | `sequence_analysis.csv` und `analysis_summary.txt` unter `data/transformed/analysis_results/` |
| Sequenzordnung | `src/extracted_sequences.csv` für OMA und Häufigkeitsanalyse |
| Häufigkeitsanalyse | `src/count_analysis_situation_counts.csv`, Rohdaten und Diagramme unter `src/` |
| Tabellenansicht | `src/übersicht_situationen_länge_pro_datei.csv` und die entsprechende Excel-Datei |

## 2. Optimal-Matching-Analyse (OMA)

OMA liest `src/extracted_sequences.csv`. Die Einstellungen in `src/oma/OMA.py` verwenden standardmäßig Ein-Sekunden-Zeitfenster und eine Sequenzdarstellung, die aufeinanderfolgende identische Zustände zusammenfasst (`dss`). `src/oma/output.json` liefert die Anzeigenamen der Codes. [OMA.py](src/oma/OMA.py)

```sh
(
  cd src/oma
  ../../.venv/bin/python -B OMA.py
)
```

Die Ergebnisse liegen in `src/oma/oma_output/`. Dazu gehören die Distanzmatrix `oma_distance_matrix.csv`, die Heatmap `oma_distance_heatmap.html`, Clusterzuordnungen in `cluster_labels.csv` sowie Tabellen zu Clusterprototypen, Codehäufigkeiten und Pflegetypen.

Die Skripte `export_cluster_code_presence.py` und `export_jasp_oma_dataset.py` erzeugen zusätzliche Auswertungsdateien. Für den konsolidierten Export wird nach OMA die Daueranalyse benötigt. Sie liest die Clusterzuordnungen, die geordneten Sequenzen und `analysis_summary.txt` aus der Extraktion.

```sh
(
  cd src/oma
  ../../.venv/bin/python -B cluster_code_length_ttest.py
)
```

## 3. Sprechdauern aktualisieren und Daten zusammenführen

Für den konsolidierten Export werden die Situationszählungen, `src/oma/oma_output/cluster_code_duration_observations.csv` aus der Daueranalyse und die bereinigte Übersicht unter `data/` benötigt. Die bereinigte Übersicht enthält die ausgewählten Zeilen und wird separat bereitgestellt.

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview 'data/sauber_übersicht_situationen_länge_pro_datei.csv' \
  --dry-run
```

Nach Prüfung der Änderungen denselben Befehl ohne `--dry-run` ausführen und anschließend die Daten zusammenführen.

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview 'data/sauber_übersicht_situationen_länge_pro_datei.csv'
.venv/bin/python -B src/consolidate_csv.py
```

Die Aktualisierung erhält die Zeilenauswahl, Reihenfolge und übrigen Zellen der bereinigten Übersicht. Das Pflegekind wird über eine eindeutige Codierung `5.5.1` bis `5.5.10` mit exakt den Grenzen der Situation `6.1.1` bestimmt. Ein Sprechintervall `5.3.1` zählt bei einem zeitlich exakt passenden Verweis auf dieses Kind. Weitere gleichzeitige Adressaten sind zulässig.

Sprechintervalle werden an Phasengrenzen zugeschnitten und innerhalb jeder Phase ohne Doppelzählung summiert. Überlappende Phasen zählen ihre jeweilige Sprechzeit. Die Gesamtsprechdauer wird separat im gesamten Situationsfenster berechnet. Die Übersicht enthält Millisekunden, der konsolidierte Export Sekunden. Die Zusammenführung schreibt `src/consolidated_first_round.csv` und `src/consolidated_data.csv`.

## 4. Interrater-Übereinstimmung

Die erste Person liefert die Excel-Dateien direkt unter `data/`, die zweite direkt unter `data/interrater_data_raw/`. Die Dateien im zweiten Ordner bestimmen die Auswahl der Videos. Das Skript ordnet die Paare anhand der Dateinamen zu und extrahiert für beide Personen alle Situationen `6.1.1` mit ihren zeitlich überlappenden Annotationen.

```sh
.venv/bin/python -B src/interrater_check.py
```

Die Konfiguration enthält getrennte Listen für Präsenz- und Timingcodes. `tolerance_ms` gilt jeweils für Anfang und Ende eines Ereignisses. Der eingecheckte Wert beträgt 60.000 ms. Eine abweichende Toleranz lässt sich für einen einzelnen Lauf setzen. [config/interrater.json](config/interrater.json)

```sh
.venv/bin/python -B src/interrater_check.py \
  --tolerance-ms 1000 --output-dir output/interrater_1000ms
```

Der Standardlauf schreibt den Bericht, CSV-Tabellen und neu extrahierte Sequenzen nach `output/interrater/`. Das Skript wertet Sprache sowohl insgesamt als auch mit Pflegekindbezug aus. Die Anleitung beschreibt die Dateipaarung, Kennzahlen und Berichtsdateien im Detail. [Interrater-Anleitung](README_INTERRATER_DE.md)

## Tests

```sh
.venv/bin/python -B -m pytest -p no:cacheprovider \
  src/tests/test_interrater_check.py src/tests/test_interrater_speech.py \
  src/tests/test_speech_durations.py src/tests/test_consolidated_csv.py
```
