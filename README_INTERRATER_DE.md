# Anleitung zur Interrater-Analyse

Diese Anleitung beschreibt die Vorbereitung der Kodierungen, den Vergleich
zweier kodierender Personen und die Auswertung der Pflegekind-Sprache. Sie
ergänzt die ersten Verarbeitungsschritte in [readme.md](readme.md).

Verglichen werden nur Videos, die beide Personen kodiert haben. Im aktuellen
Datensatz sind das zehn Videos mit jeweils 13 kodierten Pflegesituationen pro
Person. Weitere Videos dürfen im Ordner der ersten Person liegen; sie werden
ohne zweite Kodierung nicht in den Vergleich aufgenommen.

## 1. Voraussetzungen und Ausgangsdateien

Alle folgenden Befehle werden im **Hauptverzeichnis des Projekts** ausgeführt,
also dort, wo `readme.md`, `data/` und `src/` liegen. Die Beispiele verwenden die
vorhandene Python-Umgebung `.venv`. Benötigt werden `pandas`, `numpy` und
`openpyxl` sowie `statsmodels` für den zweiseitigen Standardtest von Cohen’s
Kappa gegen null; für ältere `.xls`-Dateien zusätzlich `xlrd`.

Die Kodierungen müssen als Excel-Dateien vorliegen. Das erste Tabellenblatt
muss mindestens diese Spalten enthalten:

| Spalte | Inhalt | Beispiel |
|---|---|---|
| `Code` | Numerischer Code mit Bezeichnung; auch ein vollständiger Codepfad ist möglich | `6.1.1 Pflegesituation` |
| `Anfang` | Beginn des kodierten Intervalls | `0:00:30,8` |
| `Ende` | Ende des kodierten Intervalls | `0:00:39,0` |

Die ursprünglichen Kodierungen und Zeitangaben beibehalten. Zeitangaben mit
Komma oder Punkt als Dezimaltrennzeichen werden unterstützt. Eine
Pflegesituation wird über `6.1.1` erkannt; `5.4.3 Pflegesituation` ist ein
anderer Code und ersetzt diese Situationskodierung nicht.

### Dateien ablegen und zuordnen

Die Dateien der ersten Person liegen direkt in `data/`, die Dateien der
zweiten Person direkt in `data/interrater_data_raw/`:

```text
data/
├── 24-P-1_transformed.xlsx
├── 33-P-1_transformed.xlsx
├── weitere Dateien der ersten Person …
└── interrater_data_raw/
    ├── 24-P-1_transformed_IR.xlsx
    └── 33-P-1_transformed_IR.xlsx
```

Der gemeinsame Videoname stellt die Verbindung her. Beispielsweise gehören
`24-P-1_transformed.xlsx` und `24-P-1_transformed_IR.xlsx` zusammen. Zusätze wie
`_K1` oder `_K2` bleiben Bestandteil der Identität und dürfen nicht beliebig
entfernt werden.

Der Ordner der zweiten Person bestimmt die Auswahl der zu vergleichenden
Videos. Für jede dort abgelegte Excel-Datei muss eine eindeutig zuordenbare
Datei der ersten Person vorhanden sein. Unterordner werden nicht durchsucht.
Die automatische Zuordnung entfernt nur die erwarteten Endungen `_IR` und
`_transformed` vom Dateinamen. Excel-Sperrdateien mit `~$` am Anfang werden vom
Interrater-Check ignoriert.

## 2. Dateien vorbereiten: bisheriger und direkter Ablauf

### Bisheriger Ablauf aus readme.md

Die Hauptanleitung beschreibt zunächst die Transformation mit
[transform_data.py](transform_data.py). Dabei bleibt von einem Codepfad nur
der letzte Eintrag erhalten, beispielsweise:

```text
6 Pflege > 6.1 Pflegekontext > 6.1.1 Pflegesituation
→ 6.1.1 Pflegesituation
```

Um beide Ordner ausdrücklich zu verarbeiten, ohne den im Skript hinterlegten
Ordner ändern zu müssen:

```sh
.venv/bin/python -B -c "from transform_data import process_folder; process_folder('data')"
.venv/bin/python -B -c "from transform_data import process_folder; process_folder('data/interrater_data_raw')"
```

Die Ausgaben liegen anschließend in `data/transformed/` beziehungsweise
`data/interrater_data_raw/transformed/`. Die Eingabedateien bleiben erhalten.
Geöffnete Excel-Dateien vor diesem Vorbereitungsschritt schließen, damit keine
Sperrdateien mitverarbeitet werden.

Der zweite Schritt der Hauptanleitung ist die Sequenzextraktion mit
[src/detect_codes_within.py](src/detect_codes_within.py). Der bisherige
Verarbeitungsmodus lässt sich für beide Datensätze ausdrücklich aufrufen:

```sh
.venv/bin/python -B src/detect_codes_within.py \
  --input-dir data/transformed \
  --output-dir data/transformed/analysis_results \
  --sequence-scope legacy

.venv/bin/python -B src/detect_codes_within.py \
  --input-dir data/interrater_data_raw/transformed \
  --output-dir data/interrater_data_raw/transformed/analysis_results \
  --sequence-scope legacy
```

Dabei entsteht unter anderem jeweils `sequence_analysis.csv`. Die weiteren
Skripte der Hauptanleitung, etwa `analyse_order.py`, sind für deren jeweilige
Folgeauswertungen vorgesehen und werden für den Interrater-Check nicht benötigt.

**Für den aktuellen Interrater-Vergleich sind diese beiden manuellen
Vorbereitungsschritte optional.** Der bisherige Extraktionsmodus kann
Annotationen verlieren, wenn Intervallgrenzen voneinander abweichen. Außerdem
enthält `data/processed/sequence_analysis.csv` derzeit nur sechs der zehn
erneut kodierten Videos. Diese vorhandenen CSVs werden deshalb nicht als
Eingabe des Interrater-Checks verwendet.

### Direkter Ablauf für die Interrater-Analyse

[src/interrater_check.py](src/interrater_check.py) liest die Excel-Dateien aus
Schritt 1 direkt ein. Das Skript entfernt Codepfade selbst und erzeugt für
beide Personen vollständige Sequenzdateien im Ergebnisordner.

Dabei wird jede `6.1.1`-Pflegesituation berücksichtigt. Eine Annotation gehört
zu einer Situation, wenn sie diese zeitlich mit positiver Dauer überlappt.
Auch grenzüberschreitende Annotationen werden mit ihren ursprünglichen
Zeitstempeln erhalten. Ein passender `5.4.*`-Settingcode oder `6.2.*`-Pflegetyp
ist keine Voraussetzung dafür, dass die Situation exportiert wird.

Für eine neue Interrater-Auswertung genügt somit:

1. Excel-Dateien beider Personen wie in Schritt 1 ablegen.
2. Die Einstellungen in Schritt 3 prüfen.
3. Den Interrater-Check wie in Schritt 4 starten.

## 3. Codes und Toleranz festlegen

Die Einstellungen stehen in [config/interrater.json](config/interrater.json).
Die beiden Codelisten können unterschiedlich sein:

| Einstellung | Bedeutung |
|---|---|
| `old_input_dir` | Ordner mit den Excel-Dateien der ersten Person |
| `new_input_dir` | Ordner mit den Excel-Dateien der zweiten Person; bestimmt die Videoauswahl |
| `output_dir` | Zielordner für Berichte und CSV-Dateien |
| `presence_codes` | Codes, für die Vorhandensein beziehungsweise Fehlen verglichen wird |
| `timing_codes` | Codes, deren einzelne Intervalle zeitlich verglichen werden |
| `duration_codes` | Optional: eigene Codeliste für den Dauervergleich; ohne Angabe werden die Codes aus beiden Hauptlisten verwendet |
| `tolerance_ms` | Maximal zulässige Abweichung jeweils für Beginn und Ende, in Millisekunden |
| `speech_scope` | Optional: `all` oder `pflegekind` für `5.3.1` in den Hauptauswertungen; ohne Angabe gilt `all` |
| `bootstrap_replicates` | Anzahl der Wiederholungen für die Konfidenzintervalle |
| `bootstrap_seed` | Startwert des Zufallsgenerators für reproduzierbare Konfidenzintervalle |

Ein vollständiges **Beispiel** mit einer Toleranz von einer Sekunde:

```json
{
  "old_input_dir": "data",
  "new_input_dir": "data/interrater_data_raw",
  "output_dir": "output/interrater",
  "presence_codes": ["2.2.3.4", "2.2.3.14", "6.4.3", "6.4.4", "6.4.5"],
  "timing_codes": ["6.1.1", "6.1.2", "6.1.3", "6.1.4", "5.3.1"],
  "speech_scope": "all",
  "tolerance_ms": 1000,
  "bootstrap_replicates": 2000,
  "bootstrap_seed": 42
}
```

Das Beispiel ist keine automatische Änderung der vorhandenen Konfiguration.
Die Toleranz und die Codes müssen entsprechend der fachlichen Fragestellung
gewählt werden. Nur vollständige numerische Codes eintragen, keine
Bezeichnungen oder Platzhalter wie `5.5.*`. `5.5.1` und `5.5.10` sind
unterschiedliche Codes. Beide Codelisten müssen mindestens einen Eintrag
enthalten.

Bei der Toleranz auf die Einheit achten:

| `tolerance_ms` | Zeitliche Abweichung je Grenze |
|---:|---|
| `100` | 0,1 Sekunden |
| `500` | 0,5 Sekunden |
| `1000` | 1 Sekunde |
| `60000` | 60 Sekunden |

Bei `500` wird ein Intervall nur dann zeitlich zugeordnet, wenn sowohl der
Beginn als auch das Ende um höchstens 500 Millisekunden abweichen. Eine große
Toleranz kann Unterschiede in der Segmentierung nicht beseitigen: Ein langes
Intervall wird weiterhin höchstens einem kurzen Intervall zugeordnet.

## 4. Analyse ausführen

Die eingestellten Eingaben verarbeiten und alle Ergebnisse neu erstellen:

```sh
.venv/bin/python -B src/interrater_check.py
```

Am Anfang der Konsolenausgabe stehen der tatsächlich verwendete
Konfigurationspfad, die wirksame Toleranz und die Sprachvariante der
Hauptauswertung. Am Ende wird der Pfad zu `report.md` ausgegeben.

Eine andere Toleranz für einen getrennten Lauf verwenden:

```sh
.venv/bin/python -B src/interrater_check.py \
  --tolerance-ms 1000 \
  --output-dir output/interrater_1000ms
```

In den Hauptauswertungen nur explizit zugeordnete Pflegekind-Sprache für
`5.3.1` verwenden:

```sh
.venv/bin/python -B src/interrater_check.py \
  --speech-scope pflegekind \
  --output-dir output/interrater_pflegekind
```

Eine andere Konfigurationsdatei verwenden:

```sh
.venv/bin/python -B src/interrater_check.py --config config/interrater.json
```

Kommandozeilenargumente überschreiben die entsprechenden JSON-Einstellungen
nur für diesen Lauf. Das Skript schreibt die Eingabe-JSON **nicht** zurück.
Änderungen an der Konfiguration vor dem Start speichern. Relative
Ordnerangaben in der Konfiguration beziehen sich auf das Projektverzeichnis.

Die Ausgabedateien im gewählten Zielordner werden bei einem erneuten Lauf
überschrieben. Für Varianten mit anderen Einstellungen deshalb jeweils einen
eigenen `output_dir` verwenden. Die ursprünglichen Excel-Dateien und die
vorhandenen Dateien in `data/processed/` bleiben erhalten.

## 5. Was wird verglichen?

### Gemeinsame Situationen und wiederholte Ereignisse

Pflegesituationen werden innerhalb desselben Videos anhand ihrer zeitlichen
Überlappung chronologisch einander zugeordnet. Zunächst wird die größtmögliche
Anzahl von Paaren gesucht; bei gleich vielen Paaren wird die größere gesamte
relative Überlappung bevorzugt. Unterschiedliche Pflegetypen verhindern keine
Zuordnung. Die Ereignistoleranz aus `tolerance_ms` begrenzt diese
Situationszuordnung nicht.

Nicht zugeordnete Situationen bleiben in der Präsenz- und Ereignisauswertung
enthalten. Bei der Präsenz gilt die fehlende Gegenseite als nicht vorhanden.
Bei der Ereignisauswertung bleiben die darin enthaltenen Ereignisse ohne
Gegenstück.

Gleiche Codes können mehrfach vorkommen. Ereignisse werden deshalb anhand
ihrer Zeitstempel und ihres Situationsbezugs verglichen, nicht anhand ihrer
CSV-Zeilennummer. Jedes Ereignis kann höchstens einmal zugeordnet werden.
Identische Kopien mit gleichem Video, Code, Beginn und Ende werden nicht
mehrfach gezählt. Gleichzeitig auftretende unterschiedliche Codes bleiben
eigenständige Annotationen.

### Vorhandensein der Codes

Für jeden Eintrag in `presence_codes` wird geprüft, ob beide Personen den Code
gefunden haben, und zwar getrennt pro Video und pro zugeordnetem oder
einseitigem Situationsabschnitt. Die Anzahl seiner Wiederholungen spielt bei
dieser binären Betrachtung keine Rolle.

Ausgegeben werden die Fälle „beide vorhanden“, „nur erste Person“, „nur zweite
Person“ und „beide nicht vorhanden“, die prozentuale Übereinstimmung, Cohen's
Kappa, nominales Krippendorffs Alpha und der positive F1-Wert. Die Gesamtzeile
auf Situationsebene fasst die binären Bewertungen über alle ausgewählten Codes
zusammen; Kappa und Alpha werden daraus neu berechnet. Ihre 95%-Intervalle und
die Anzahl definierter Bootstrap-Wiederholungen stehen auch im Bericht. Die
Gesamtzeile auf Videoebene enthält kein gepooltes Kappa oder Alpha.

Die positive spezifische Übereinstimmung ist 2 × beide vorhanden geteilt durch
2 × beide vorhanden + nur erste + nur zweite Person und entspricht hier dem
positiven F1-Wert. Die negative spezifische Übereinstimmung verwendet im Zähler
und Nenner stattdessen 2 × beide nicht vorhanden. Ist der jeweilige Nenner null,
ist der Wert nicht definiert. Beide Kennwerte stehen mit Video-Bootstrap-Intervallen
pro Code und für die gepoolten Gesamtzählungen in den Präsenz-CSVs und im Bericht.

### Zeitliche Übereinstimmung einzelner Ereignisse

Für `timing_codes` werden gleiche Codes innerhalb zugeordneter Situationen
chronologisch eins zu eins abgeglichen. Sowohl Beginn als auch Ende müssen
innerhalb der eingestellten Toleranz liegen. Zunächst wird die größtmögliche
Anzahl von Treffern gesucht; anschließend werden die Grenzabweichungen
minimiert.

```text
Ereignis-F1 = 2 × zugeordnete Ereignisse / (Ereignisse erste Person + Ereignisse zweite Person)
```

Keine Person wird dabei als fehlerfreie Referenz behandelt. Zusätzlich werden
die mittleren absoluten Abweichungen von Beginn und Ende für die zugeordneten
Ereignisse ausgegeben.

### Dauer der ausgewählten Codes

Zusätzlich wird die Dauer jedes ausgewählten Codes für beide Personen
berechnet. Ohne zusätzliche Einstellung werden alle Codes aus
`presence_codes` und `timing_codes` berücksichtigt, gemeinsame Einträge nur
einmal. Eine eigene Liste lässt sich beispielsweise mit
`"duration_codes": ["6.1.1", "6.1.3", "5.3.1"]` festlegen. Auch diese Liste
muss vollständige, eindeutige numerische Codes enthalten und darf nicht leer sein.

Die Auswertung unterscheidet zwei Zeitbezüge:

- **Vollständige kodierte Dauer:** Alle für die Analyse beibehaltenen
  Originalintervalle des Codes werden pro Video vereinigt und anschließend
  über die Videos aufsummiert. Doppelte oder überlappende Intervalle desselben
  Codes zählen nur einmal. Die Intervalle werden nicht auf die Pflegesituation
  begrenzt; grenzüberschreitende Ereignisse und Ereignisse in nicht zugeordneten
  Situationen zählen mit. Annotationen ohne Überlappung mit einer
  Pflegesituation wurden bereits bei der Auswahl der Analysedaten ausgeschlossen.
- **Dauer in der gemeinsamen Beobachtungszeit:** Für den zeitlichen
  Überlappungsvergleich werden die Intervalle nur innerhalb der Schnittmengen
  zugeordneter Pflegesituationen betrachtet. Daraus entstehen Dauer-Dice und
  Jaccard. Die Ereignistoleranz wird dafür nicht verwendet.

Gerade bei `6.1.1` müssen diese Werte getrennt gelesen werden: Innerhalb der
gemeinsamen Situationszeit stimmen die Situationsdauern konstruktionsbedingt
überein. Unterschiedliche Situationsgrenzen zeigen sich dagegen in den
vollständigen Dauern und in den Ereignis- beziehungsweise Grenzvergleichen.

Bericht und CSV-Dateien zeigen die alte und neue Dauer, die Differenz
`neu − alt`, deren Absolutbetrag und die prozentuale Veränderung
`100 × (neu − alt) / alt`. Bei einer alten Dauer von null ist die prozentuale
Veränderung undefiniert. Zusätzlich wird die mittlere absolute
Dauerabweichung pro Video ausgegeben. Dadurch bleibt sichtbar, wenn sich
positive und negative Abweichungen in der Gesamtsumme gegenseitig aufheben.

Die Tabelle im Bericht zeigt Sekunden; die detaillierten Dateien
`code_duration_scores.csv` und `code_durations_by_video.csv` verwenden
Millisekunden. Die Zusammenfassung enthält außerdem Konfidenzintervalle aus
der Wiederholungsziehung ganzer Videos. Für `5.3.1` gilt bei diesen
Code-Dauern die gewählte Hauptvariante `speech_scope`. Unterschiedliche Codes
können gleichzeitig auftreten; ihre Dauern sind daher nicht ohne Weiteres
zu einer gesamten Beobachtungszeit addierbar.

## 6. Alle Kindansprachen und Pflegekind-Sprache unterscheiden

Für `5.3.1` werden bei jedem Lauf zusätzlich zwei Varianten berechnet,
unabhängig davon, ob der Code in den Hauptlisten steht:

| Variante | Berücksichtigte Intervalle |
|---|---|
| `all` | Alle `5.3.1`-Intervalle, die Pflegesituationen überlappen |
| `pflegekind` | Nur Intervalle mit einer expliziten zeitgleichen Referenz auf das jeweilige Pflegekind |

Die Pflegekind-Variante wendet denselben Filter auf **beide** Personen an:

1. Das Pflegekind ist das eindeutig zuordenbare Kind aus `5.5.1` bis
   `5.5.10`, dessen Referenz exakt denselben Beginn und dasselbe Ende wie die
   `6.1.1`-Pflegesituation hat.
2. Ein `5.3.1`-Sprechintervall zählt als Pflegekind-Sprache, wenn dieses Kind
   zusätzlich mit exakt dem Beginn und Ende des Sprechintervalls kodiert ist.

Eine Kindreferenz über die gesamte Pflegesituation reicht daher nicht aus,
um jedes darin liegende Sprechintervall als Pflegekind-Sprache zu werten.
Die Zuordnung erfolgt je Person und Situation getrennt. Die Kindnummer muss
zwischen den Personen nicht identisch sein.

Beispiel für eine ausdrücklich zugeordnete Ansprache:

| Code | Anfang | Ende | Bedeutung |
|---|---|---|---|
| `6.1.1` | `0:00:30,0` | `0:01:00,0` | Pflegesituation |
| `5.5.1` | `0:00:30,0` | `0:01:00,0` | Pflegekind dieser Situation |
| `5.3.1` | `0:00:35,0` | `0:00:37,0` | Sprechintervall |
| `5.5.1` | `0:00:35,0` | `0:00:37,0` | Ansprache ausdrücklich mit diesem Kind verknüpft |

Weitere gleichzeitig angesprochene Personen sind erlaubt. Eine ausschließlich
auf die Gruppe bezogene Referenz bestätigt die Beteiligung des Pflegekindes
nicht ausdrücklich. Gruppenansprachen und Sprechintervalle ohne passende
Kindreferenz werden deshalb separat protokolliert und nicht als bestätigte
Pflegekind-Sprache gewertet. Das bedeutet nicht, dass das Pflegekind
tatsächlich unbeteiligt war.

Die Kindreferenzen werden **exakt** anhand normalisierter Zeitstempel
zugeordnet. Die Ereignistoleranz von beispielsweise 1000 Millisekunden lockert
diese Zuordnungsregel nicht.

Ohne `speech_scope` gilt in den Hauptauswertungen `all`. Mit
`"speech_scope": "pflegekind"` oder `--speech-scope pflegekind` wird auch
`5.3.1` in den Hauptauswertungen entsprechend gefiltert. Andere Codes sind
davon nicht betroffen. Die zusätzlichen Sprachausgaben enthalten weiterhin
beide Varianten.

### Sprechzeit und Überlappung statt nur Ereignisanzahl

Eine Person kann mehrere einzelne Äußerungen markieren, während die andere
Person dieselbe Episode als ein längeres Intervall kodiert. Ein Ereignis-F1
allein bildet diese unterschiedliche Segmentierung nur eingeschränkt ab.
Deshalb berechnet das Skript zusätzlich die zeitliche Abdeckung.

Für diese Berechnung wird nur die gemeinsame Beobachtungszeit verwendet:
die Schnittmenge der Zeitfenster zugeordneter Pflegesituationen. Innerhalb
dieser Fenster werden überlappende Sprechintervalle pro Person vereinigt.
Zeit wird dadurch nicht doppelt gezählt. Nur für diese Dauerberechnung werden
Intervalle auf das gemeinsame Zeitfenster begrenzt; die exportierten
Ereigniszeitstempel bleiben unverändert.

```text
Dauer-Dice = 2 × überlappende Sprechzeit / (Sprechzeit erste Person + Sprechzeit zweite Person)
```

Zusätzlich werden Jaccard sowie beide gerichteten Abdeckungsanteile
ausgegeben: Wie viel der alten Sprechzeit deckt die neue Kodierung ab und
umgekehrt? Eine hohe Abdeckung der alten Sprechzeit kann mit zusätzlicher
Sprechzeit in der neuen Kodierung einhergehen. Sie ist deshalb kein
symmetrischer Übereinstimmungswert.

Die Dauerberechnung verwendet keine Ereignistoleranz. Nicht zugeordnete
Situationen besitzen kein gemeinsames Beobachtungsfenster und gehen nicht in
diese Dauerwerte ein; ihre Ereignisse bleiben jedoch in den Präsenz- und
Ereignisvergleichen enthalten.

## 7. Ergebnisse finden und lesen

Bei der Standardeinstellung stehen die Ergebnisse in
[output/interrater/](output/interrater/). Zunächst
[report.md](output/interrater/report.md) lesen und anschließend die passenden
CSV-Dateien verwenden.

### Eine CSV-Datei pro Berichtstabelle

Diese Dateien entsprechen den dargestellten Tabellen in `report.md`:

| Datei unter `output/interrater/report_tables/` | Inhalt |
|---|---|
| `01_code_presence.csv` | Vorhandensein der ausgewählten Codes pro Video und Situation |
| `02_event_timing.csv` | Zeitliche Zuordnung der ausgewählten Ereigniscodes |
| `03_speech_event_matching.csv` | Ereignisvergleich für `all` und `pflegekind` |
| `04_shared_speech_time_coverage.csv` | Gemeinsame Beobachtungszeit und Sprechzeitüberlappung beider Sprachvarianten |
| `05_code_durations.csv` | Vollständige Code-Dauern, Abweichungen und Dauervergleich innerhalb gemeinsamer Beobachtungszeit |

Bericht und Tabellenausgaben werden auf Deutsch erzeugt. Die Dateinamen bleiben
unverändert. Die Tabellenausgaben übernehmen die deutschen Spalten und
Bezeichnungen, Reihenfolge, Rundung und Angaben „nicht definiert“ aus dem
Bericht. Die detaillierten Datendateien behalten ihre technischen Spaltennamen.
Für weitere Berechnungen die
detaillierten Dateien verwenden, die ungerundete Kennwerte enthalten.

### Detaillierte Ergebnisse und Prüfdateien

| Datei oder Dateigruppe | Zweck |
|---|---|
| `presence_scores.csv`, `presence_details.csv` | Kennwerte und einzelne Präsenzentscheidungen der Hauptauswertung |
| `timing_scores.csv`, `timing_by_video.csv` | Ereigniskennwerte der Hauptauswertung, insgesamt und pro Video |
| `code_duration_scores.csv`, `code_durations_by_video.csv` | Vollständige und gemeinsame Code-Dauern, Differenzen und Dauer-Dice, insgesamt und pro Video |
| `event_matches.csv` | Zugeordnete und nicht zugeordnete Ereignisse mit Zeitdifferenzen |
| `speech_presence_scores.csv`, `speech_presence_details.csv` | Präsenz und Kappa für beide Sprachvarianten |
| `speech_timing_scores.csv`, `speech_timing_by_video.csv`, `speech_event_matches.csv` | Ereignisvergleiche für beide Sprachvarianten |
| `speech_coverage.csv` | Sprechdauern, Überlappung, Dice, Jaccard und gerichtete Abdeckung pro Video und insgesamt |
| `speech_care_children.csv` | Erkanntes Pflegekind je Person und Situation oder Grund einer fehlenden Zuordnung |
| `speech_recipients.csv` | Empfängerreferenzen und Filterentscheidung je Sprechintervall und Situation |
| `file_pairs.csv` | Verglichene Dateipaare und Anzahl der Situationen |
| `situation_pairs.csv` | Zuordnung der Situationen anhand der Zeitfenster |
| `excluded_annotations.csv` | Fehlerhafte, ausgeschlossene Annotationen außerhalb der zwingend benötigten Codes |
| `settings.json` | Tatsächlich verwendete Einstellungen und Angaben zur Datenauswahl |
| `sequences/old/sequence_analysis.csv` | Für diesen Lauf neu erzeugte Sequenzen der ersten Person |
| `sequences/new/sequence_analysis.csv` | Für diesen Lauf neu erzeugte Sequenzen der zweiten Person |

Die detaillierten Dauern und numerischen Zeitdifferenzen sind in
**Millisekunden** angegeben. Die Dauer- und Sprechzeittabellen im Bericht
verwenden **Sekunden**. In den Dateien mit Ereignispaaren gilt für vorzeichenbehaftete
Differenzen: `neue Zeit − alte Zeit`. Die mit `mean_abs_` bezeichneten
Abweichungen sind dagegen absolute Werte.

Bei `speech_coverage.csv` enthält `video=__overall__` die zusammengefassten
Ergebnisse. Dort stehen auch die Konfidenzintervalle. Bei den Hauptkennwerten
werden Gesamt-F1-Werte aus aufsummierten Zählungen gebildet; `macro_f1`
mittelt die definierten F1-Werte der einzelnen Codes.

Die CSV-Dateien verwenden UTF-8, Kommas als Feldtrennzeichen und Punkte als
Dezimaltrennzeichen. In einer deutsch eingestellten Tabellenkalkulation bei
Bedarf über den CSV-Import öffnen und diese Formate auswählen.

## 8. Fehlende Werte und typische Rückfragen

**Warum ist Kappa leer oder „nicht definiert“, obwohl beide Personen übereinstimmen?**
Wenn beide Personen einen Code immer oder nie vergeben, ist Kappa wegen der
konstanten Bewertungen nicht definiert. Die beobachtete Übereinstimmung ist
dennoch ablesbar. Leere Kennwerte nicht automatisch durch null ersetzen.

**Warum gibt es keinen Ereignis-F1 oder Dauer-Dice bei beidseitiger Abwesenheit?**
Ohne positive Ereignisse beziehungsweise Sprechzeit fehlt der Nenner. Der
Wert bleibt undefiniert. Beidseitige Abwesenheit zählt dagegen beim binären
Präsenzvergleich als Übereinstimmung.

**Was passiert bei fehlendem oder mehrdeutigem Pflegekind?**
Die separate Pflegekind-Auswertung schließt das gesamte betroffene Video aus
und weist `videos_excluded` beziehungsweise eine nicht verfügbare Zuordnung
aus. Fehlende Information wird nicht als fehlende Sprache gewertet. Ist
`speech_scope=pflegekind` für die Hauptauswertung gewählt und `5.3.1` dort
ausgewählt, stoppt der Lauf mit einer Fehlermeldung.

**Warum steht „no 5.4 parent found“ in einer Sequenzdatei?**
Es gibt keinen passenden Settingcode. Die korrigierte Interrater-Extraktion
kann die `6.1.1`-Situation trotzdem auswerten. Die Meldung allein bedeutet
nicht, dass keine Sequenz gefunden wurde.

**Welche fehlerhaften Intervalle führen zum Abbruch?**
Ungültige Zeitangaben oder umgekehrte Intervalle bei ausgewählten Codes,
`6.1.1` und dem zusätzlich ausgewerteten Sprechcode `5.3.1` stoppen die
Analyse. Fehlerhafte Annotationen außerhalb dieser benötigten Codes werden
mit Fundstelle in `excluded_annotations.csv` protokolliert und ausgelassen.
Im aktuellen alten Datensatz gibt es vier solche umgekehrten Intervalle in
`2-P-1`; die Originaldatei wird nicht automatisch korrigiert.

**Warum scheint eine Einstellung nach dem Lauf wieder verändert?**
`config/interrater.json` ist die Eingabe und wird nur gelesen.
`output/interrater/settings.json` ist eine neu erzeugte Ergebnisdatei. Nur die
Eingabe dauerhaft bearbeiten. Außerdem prüfen, ob die Startkonfiguration im
Terminal oder in der Entwicklungsumgebung ein Argument wie
`--tolerance-ms 1000` enthält. Dieses hat für den Lauf Vorrang. Die
Konsolenausgabe zeigt den verwendeten Konfigurationspfad und die wirksame
Toleranz.

**Wie werden die Konfidenzintervalle berechnet?**
Es werden ganze Videos mit Zurücklegen gezogen, nicht einzelne CSV-Zeilen.
Dadurch bleiben die zusammengehörigen Situationen und Ereignisse eines Videos
gemeinsam. Voreingestellt sind 2000 Wiederholungen und ein fester Startwert.
Die Grenzen sind die 2,5- und 97,5-Perzentile der definierten Ergebnisse. Die
CSV-Dateien nennen, wie viele Wiederholungen für den jeweiligen Kennwert
definiert waren. Bei nur zehn Videos entsprechend vorsichtig interpretieren.

## 9. Technische Prüfung

Die zugehörigen Tests lassen sich aus dem Hauptverzeichnis starten:

```sh
.venv/bin/python -B -m pytest -p no:cacheprovider \
  src/tests/test_interrater_check.py \
  src/tests/test_interrater_speech.py \
  src/tests/test_speech_durations.py \
  src/tests/test_consolidated_csv.py
```

Für die fachliche Interpretation getrennt betrachten: Wurde derselbe Code
gefunden, wurden dieselben einzelnen Ereignisse abgegrenzt und wurde dieselbe
Sprechzeit erfasst? Gerade bei `5.3.1` können Unterschiede in der
Empfängerauswahl und in der Segmentierung zu unterschiedlichen Ergebnissen
dieser drei Vergleiche führen.
