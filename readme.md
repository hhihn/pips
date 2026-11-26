# Analysis of care situations within PIPS

This repository contains code used to study care situations within the PIPS research project. The workflow extracts coded care situations from MAXQDA Excel exports and uses the resulting sequences for optimal matching analysis (OMA). The interrater agreement analysis reads both raters’ Excel exports directly.

## Requirements

The examples assume Python 3.10 or later and a virtual environment at `.venv/`. Run the commands from the repository root.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install pandas numpy openpyxl scipy scikit-learn \
  matplotlib seaborn plotly statsmodels pytest
```

Install `xlrd` as well if you use older `.xls` files.

## 1. Extract data

Place the first rater’s Excel files directly in `data/`. The first worksheet must contain at least the `Code`, `Anfang`, and `Ende` columns. The transformation keeps the last entry of each MAXQDA code path.

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

Pass the input directory explicitly. By default, `detect_codes_within.py` reads from `data/interrater_data_raw/transformed/`. The [pipeline runner](run_pipeline.py) uses that default, while the subsequent sequence ordering step reads from `data/transformed/analysis_results/`. Close the chart windows opened by the frequency analysis to continue to the next step.

| Step | Output |
| --- | --- |
| Transformation | Excel files in `data/transformed/` |
| Sequence extraction | `sequence_analysis.csv` and `analysis_summary.txt` in `data/transformed/analysis_results/` |
| Sequence ordering | `src/extracted_sequences.csv` for OMA and frequency analysis |
| Frequency analysis | `src/count_analysis_situation_counts.csv`, raw data, and plots in `src/` |
| Tabular view | `src/übersicht_situationen_länge_pro_datei.csv` and the corresponding Excel file |

## 2. Run optimal matching analysis (OMA)

OMA reads `src/extracted_sequences.csv`. By default, it uses one-second time windows and a sequence representation that collapses consecutive identical states (`dss`). The display names for the codes come from `src/oma/output.json`. [OMA.py](src/oma/OMA.py)

```sh
(
  cd src/oma
  ../../.venv/bin/python -B OMA.py
)
```

Results go to `src/oma/oma_output/`. They include the distance matrix `oma_distance_matrix.csv`, the heatmap `oma_distance_heatmap.html`, cluster assignments in `cluster_labels.csv`, and tables of cluster prototypes, code frequencies, and care types.

The scripts `export_cluster_code_presence.py` and `export_jasp_oma_dataset.py` produce additional exports. For the consolidated export, run the duration analysis after OMA. It reads the cluster assignments, the ordered sequences, and the `analysis_summary.txt` file from sequence extraction.

```sh
(
  cd src/oma
  ../../.venv/bin/python -B cluster_code_length_ttest.py
)
```

## 3. Update speech durations and consolidate the data

The consolidated export requires the situation counts, `src/oma/oma_output/cluster_code_duration_observations.csv` from the duration analysis, and the cleaned overview in `data/`. The cleaned overview contains the selected rows and is provided separately.

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview 'data/sauber_übersicht_situationen_länge_pro_datei.csv' \
  --dry-run
```

Review the changes, rerun the command without `--dry-run`, and then consolidate the data.

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview 'data/sauber_übersicht_situationen_länge_pro_datei.csv'
.venv/bin/python -B src/consolidate_csv.py
```

The refresh preserves the selected rows, their order, and all other cells in the cleaned overview. It identifies the child receiving care by finding a unique code from `5.5.1` through `5.5.10` whose start and end exactly match the `6.1.1` care situation. A `5.3.1` speech interval counts when a reference to that child has the same start and end as the speech interval. Other simultaneous recipients are allowed.

Speech intervals are clipped to phase boundaries and merged within each phase to avoid double counting. Each overlapping phase counts the speech time within its own window. Total speech duration is calculated separately over the entire situation. The overview uses milliseconds, and the consolidated export uses seconds. Consolidation writes `src/consolidated_first_round.csv` and `src/consolidated_data.csv`.

## 4. Measure interrater agreement

Place the first rater’s Excel files directly in `data/` and the second rater’s directly in `data/interrater_data_raw/`. The files in the second directory determine which videos to compare. The script pairs files by name and extracts all `6.1.1` care situations and their overlapping annotations for both raters.

```sh
.venv/bin/python -B src/interrater_check.py
```

The configuration has separate lists for presence and timing codes. The `tolerance_ms` value applies to the start and end of each event independently. The checked-in value is 60,000 ms. You can override it for a single run. [config/interrater.json](config/interrater.json)

```sh
.venv/bin/python -B src/interrater_check.py \
  --tolerance-ms 1000 --output-dir output/interrater_1000ms
```

By default, the script writes the report, CSV tables, and newly extracted sequences to `output/interrater/`. It analyzes all speech coded as `5.3.1` and speech explicitly addressed to the child receiving care. The [interrater analysis guide](README_INTERRATER.md) explains file pairing, metrics, and output files.

## Tests

```sh
.venv/bin/python -B -m pytest -p no:cacheprovider \
  src/tests/test_interrater_check.py src/tests/test_interrater_speech.py \
  src/tests/test_speech_durations.py src/tests/test_consolidated_csv.py
```
