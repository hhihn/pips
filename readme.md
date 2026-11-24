
# pattern analysis
# pattern analysis

## 1. daten transformieren
starte [transform_data.py](transform_data.py), welches die daten in /data/ in ein auswertbares format transformiert und in /data/transformed
speichert

## 2. daten aufbereiten
starte [detect_codes_within.py](src/detect_codes_within.py), welches die daten in /data/transformed/ auf die gesuchten sequenzen analysiert und die
ergebnisse in [sequence_analysis.csv](data/transformed/analysis_results/sequence_analysis.csv) speichert

starte [analyse_order.py](src/analyse_order.py) das die sequenzen analyisert und in [extracted_sequences.csv](src/extracted_sequences.csv) 
speichert

## 3. daten auswerten
[count_analysis.py](src/count_analysis.py) erstellt das stacked bar diagram mit den 
häufigkeiten der körperberührung

[create_row_view.py](src/create_row_view.py) erstellt tabellenansicht der daten

## 4. Sprechdauern zum Pflegekind aktualisieren

Die fünf Sprechdauern verwenden denselben Pflegekindfilter: Die Codierung
`5.5.1`–`5.5.10` muss zeitlich exakt zur Pflegesituation `6.1.1` passen.
Ein Sprechintervall `5.3.1` zählt nur, wenn dieses Pflegekind mit identischen
Start- und Endzeiten codiert ist. Weitere Adressaten dürfen gleichzeitig
codiert sein. Fehlende oder mehrdeutige Pflegekindzuordnungen führen zum Abbruch.

Alle Abschnitte jeder Phase werden berücksichtigt. Grenzüberschreitende
Äußerungen zählen mit ihren tatsächlichen Zeitanteilen. Doppelte und
überlappende Intervalle innerhalb eines Wertes werden einmal gezählt.
Überlappen unterschiedliche Phasen, zählt jede Phase ihre eigene Sprechzeit;
Lücken bleiben ohne Phasenzuordnung. Deshalb muss die Phasensumme nicht der
Gesamtsprechdauer entsprechen. Gesamtsprechdauer und Gesamtproportion werden
direkt innerhalb von `6.1.1` berechnet.

Aus dem Projektverzeichnis zunächst die Änderungen prüfen:

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview data/sauber_übersicht_situationen_länge_pro_datei.csv \
  --dry-run
```

Anschließend die bereinigte Übersicht aktualisieren und den Export regenerieren:

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview data/sauber_übersicht_situationen_länge_pro_datei.csv
.venv/bin/python -B src/consolidate_csv.py
.venv/bin/python -B -m pytest -p no:cacheprovider \
  src/tests/test_speech_durations.py src/tests/test_consolidated_csv.py
```

`--input PATH` erlaubt eine andere Sequenzdatei. Der Aktualisierungsmodus erhält
die Zeilenauswahl, Reihenfolge und übrigen Zellen der bereinigten Übersicht.
Die Übersicht enthält Millisekunden, der konsolidierte Export Sekunden.
Phasen mit Länge null erhalten eine leere Proportion. Der Prüfbericht nennt
Änderungen je Zeile, Phasenüberlappungen und Lücken. Der Bericht der durchgeführten
Korrektur liegt in `output/speech_duration_refresh_report.txt`.

Eine deutsche Schritt-für-Schritt-Anleitung zur Dateivorbereitung,
Interrater-Analyse und Pflegekind-Sprache steht in
[README_INTERRATER_DE.md](README_INTERRATER_DE.md).

## Interrater agreement

From the project directory, regenerate complete care-window sequences and compare
the 10 videos annotated by both raters:

```sh
.venv/bin/python -B src/interrater_check.py
```

Edit [config/interrater.json](config/interrater.json) to set the independent
`presence_codes` and `timing_codes` lists of exact numeric code IDs. Labels are
ignored; `5.5.1` never matches `5.5.10`. `tolerance_ms` controls the allowed
difference **at both start and end**, inclusive.
Override it for a separate run with:

```sh
.venv/bin/python -B src/interrater_check.py \
  --tolerance-ms 1000 --output-dir output/interrater_1000ms
```

Configuration paths are relative to the repository. `--config` accepts another
JSON file. Defaults work from any working directory when invoking the script by
its absolute path.

The roster comes from the Excel files directly in `data/interrater_data_raw/`;
matching older files are read directly from `data/`. Unrated older videos are
excluded, Excel lock files are ignored, and missing or ambiguous counterparts
stop the check. The original processed CSVs are not used: the old processed
subset omits four paired videos, and previous extraction omitted annotations.

Corrected extraction exports every `6.1.1` care situation and every annotation
with positive overlap, retaining full original timestamps. It does not require
a setting or care-type match. Situations are aligned one-to-one by chronological
overlap, maximizing pair count and then total intersection-over-union. Missing
situations are retained as disagreements. Duplicate exported copies of an event
are counted once. Malformed selected annotations and care windows stop the run;
malformed annotations outside both code lists are excluded with an explicit
audit. The current old `2-P-1` file contains four such reversed intervals.

Results are saved under [output/interrater/](output/interrater/):

- `report.md`: German-language results, definitions, and limitations.
- `report_tables/`: one CSV per table displayed in `report.md`, with the same
  German headers and labels, row order, rounded values, and `nicht definiert`
  cells. Technical column names in the detailed data CSVs remain unchanged. Filenames are
  numbered in report order: `01_code_presence.csv`, `02_event_timing.csv`,
  `03_speech_event_matching.csv`, `04_shared_speech_time_coverage.csv`, and
  `05_code_durations.csv`.
  The detailed score CSVs below retain their full numeric precision.
- `presence_scores.csv`: presence agreement, Cohen's kappa, and positive F1 per
  code, separately at video and care-situation level; pooled agreement and
  micro/macro F1 are also included. `presence_details.csv` records each decision.
- `timing_scores.csv` and `timing_by_video.csv`: event counts, one-to-one matches,
  timing F1, and mean absolute errors for matched boundaries.
- `code_duration_scores.csv` and `code_durations_by_video.csv`: per-code union
  durations of complete retained original intervals, signed/absolute changes,
  percentage changes relative to the old duration, and mean absolute video
  differences. Shared-window durations, Dice/Jaccard, and aggregate video-bootstrap
  intervals are also included. Detailed durations use milliseconds; the report
  and its table CSV use seconds. Default codes are the union of the two main
  lists; optional `duration_codes` selects a separate list. Different codes can
  overlap and their durations must not be treated as disjoint recording time.
- `event_matches.csv`: every matched or unmatched selected occurrence, its
  situation memberships, and signed timestamp differences (`new - old`, in ms).
- `file_pairs.csv`, `situation_pairs.csv`, `excluded_annotations.csv`, and
  `settings.json`: pairing, exclusions, and effective settings.
- `sequences/old/sequence_analysis.csv` and
  `sequences/new/sequence_analysis.csv`: regenerated sequences. Timestamp fields
  retain source spelling; durations and numeric error fields use milliseconds.

Presence treats each selected code as present/absent per unit. Timing matches
identical codes chronologically within aligned situations, maximizing match
count before minimizing boundary error. An occurrence cannot be reused, even
when it overlaps multiple situations. Simultaneous different codes are independent;
CSV row positions are not compared. Timing F1 is
`2 * matched / (old events + new events)`; neither rater is a gold standard.
Aggregate confidence intervals resample whole videos (2,000 replicates, seed 42).
Undefined scores remain blank with status fields; joint absence does not create
perfect timing scores. Kappa is code-specific and can be undefined for constant
ratings. The Markdown report and CSVs document denominators and valid bootstrap
replicate counts. These scores concern annotations overlapping care situations,
not the full video timeline or a separate sequence-order reliability score.

### Pflegekind-directed speech

Every run also compares `5.3.1` using two separate scopes: `all` and `pflegekind`,
independently of the main code lists. The Pflegekind scope applies the same
recipient filter to **both** raters:

1. Identify each situation's care child from the unique `5.5.1`–`5.5.10` code
   with exactly the `6.1.1` situation's start and end. Child numbers are resolved
   separately for each rater; they need not match across raters.
2. Include a speech interval only if that child has a reference with exactly
   the same start and end as the speech. Additional simultaneous recipients are
   allowed. Group-only references and unlinked speech are not confirmed
   Pflegekind speech and are excluded from that scope.

Recipient matching uses exact normalized timestamps, independently of the event
matching tolerance. A broad care-child annotation merely overlapping speech
does not identify that utterance's recipient. Qualifying speech keeps its
original timestamps and only the situation memberships for which it qualifies.

The primary presence, timing, event-matching, and code-duration files
use all speech by default. To filter their selected `5.3.1` entries, add
`"speech_scope": "pflegekind"` to `config/interrater.json`, or use:

```sh
.venv/bin/python -B src/interrater_check.py \
  --speech-scope pflegekind --output-dir output/interrater_pflegekind
```

Other codes retain their normal behavior. Both speech scopes are always saved
separately, regardless of the primary setting:

- `speech_presence_scores.csv` and `speech_presence_details.csv`: presence and
  kappa for each scope at video/situation level.
- `speech_timing_scores.csv`, `speech_timing_by_video.csv`, and
  `speech_event_matches.csv`: one-to-one event comparisons for each scope.
- `speech_coverage.csv`: per-video and pooled union durations, overlap,
  duration Dice/Jaccard, directional coverage, and aggregate bootstrap intervals.
  Durations use milliseconds and only shared time in aligned care windows;
  intervals are clipped for this calculation only, and overlap counts once.
  This comparison uses no timestamp tolerance. Unmatched situations remain in
  event/presence comparisons but have no shared duration window.
- `speech_care_children.csv` and `speech_recipients.csv`: identified care
  children, exact recipient references, and per-situation inclusion decisions.

Duration Dice is `2 * overlapping speech time / (old speech time + new speech
time)`. It helps distinguish speech detection from splitting the same episode
into several utterances. Jointly absent speech has undefined Dice, not perfect
agreement. Group references may include the Pflegekind; their exclusion means
its involvement is not explicitly confirmed, not that it was uninvolved.

If a care child is missing or ambiguous, the separate Pflegekind comparison
excludes that whole video and reports its availability and exclusion counts;
it does not count the missing information as absent speech. Primary
`speech_scope=pflegekind` instead fails clearly when `5.3.1` is selected and any
care-child assignment is unresolved. Malformed speech annotations stop the
check even if `5.3.1` is outside the main lists, because the separate speech
comparison always uses it. Input JSON files are never rewritten.

The original extraction mode remains the default. To use corrected extraction
independently, with strict validation of **all** annotations:

```sh
.venv/bin/python -B src/detect_codes_within.py \
  --input-dir data/interrater_data_raw \
  --output-dir output/care_overlap \
  --sequence-scope care-overlap
```

Run the relevant tests with:

```sh
.venv/bin/python -B -m pytest -p no:cacheprovider \
  src/tests/test_interrater_check.py \
  src/tests/test_interrater_speech.py \
  src/tests/test_speech_durations.py src/tests/test_consolidated_csv.py
```

## 1. daten transformieren
starte [transform_data.py](transform_data.py), welches die daten in /data/ in ein auswertbares format transformiert und in /data/transformed
speichert

## 2. daten aufbereiten
starte [detect_codes_within.py](src/detect_codes_within.py), welches die daten in /data/transformed/ auf die gesuchten sequenzen analysiert und die
ergebnisse in [sequence_analysis.csv](data/transformed/analysis_results/sequence_analysis.csv) speichert

starte [analyse_order.py](src/analyse_order.py) das die sequenzen analyisert und in [extracted_sequences.csv](src/extracted_sequences.csv) 
speichert

## 3. daten auswerten
[count_analysis.py](src/count_analysis.py) erstellt das stacked bar diagram mit den 
häufigkeiten der körperberührung

[create_row_view.py](src/create_row_view.py) erstellt tabellenansicht der daten

## 4. Sprechdauern zum Pflegekind aktualisieren

Die fünf Sprechdauern verwenden denselben Pflegekindfilter: Die Codierung
`5.5.1`–`5.5.10` muss zeitlich exakt zur Pflegesituation `6.1.1` passen.
Ein Sprechintervall `5.3.1` zählt nur, wenn dieses Pflegekind mit identischen
Start- und Endzeiten codiert ist. Weitere Adressaten dürfen gleichzeitig
codiert sein. Fehlende oder mehrdeutige Pflegekindzuordnungen führen zum Abbruch.

Alle Abschnitte jeder Phase werden berücksichtigt. Grenzüberschreitende
Äußerungen zählen mit ihren tatsächlichen Zeitanteilen. Doppelte und
überlappende Intervalle innerhalb eines Wertes werden einmal gezählt.
Überlappen unterschiedliche Phasen, zählt jede Phase ihre eigene Sprechzeit;
Lücken bleiben ohne Phasenzuordnung. Deshalb muss die Phasensumme nicht der
Gesamtsprechdauer entsprechen. Gesamtsprechdauer und Gesamtproportion werden
direkt innerhalb von `6.1.1` berechnet.

Aus dem Projektverzeichnis zunächst die Änderungen prüfen:

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview data/sauber_übersicht_situationen_länge_pro_datei.csv \
  --dry-run
```

Anschließend die bereinigte Übersicht aktualisieren und den Export regenerieren:

```sh
.venv/bin/python -B src/create_row_view.py \
  --refresh-overview data/sauber_übersicht_situationen_länge_pro_datei.csv
.venv/bin/python -B src/consolidate_csv.py
.venv/bin/python -B -m pytest -p no:cacheprovider \
  src/tests/test_speech_durations.py src/tests/test_consolidated_csv.py
```

`--input PATH` erlaubt eine andere Sequenzdatei. Der Aktualisierungsmodus erhält
die Zeilenauswahl, Reihenfolge und übrigen Zellen der bereinigten Übersicht.
Die Übersicht enthält Millisekunden, der konsolidierte Export Sekunden.
Phasen mit Länge null erhalten eine leere Proportion. Der Prüfbericht nennt
Änderungen je Zeile, Phasenüberlappungen und Lücken. Der Bericht der durchgeführten
Korrektur liegt in `output/speech_duration_refresh_report.txt`.
