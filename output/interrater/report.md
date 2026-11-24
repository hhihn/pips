# Interrater-Analyse

Verglichen wurden 10 Videopaare. 58 Videos des alten Datensatzes ohne zweite Kodierung wurden ausgeschlossen. „Alt“ bezeichnet die erste, „neu“ die zweite kodierende Person.
Pflegesituationen: alt=13, neu=12, zugeordnet=12.
Sprachvariante für 5.3.1 in der Hauptauswertung: **Alle Kindansprachen** (`speech_scope=all`). Die zusätzlichen Sprachauswertungen vergleichen stets alle Kindansprachen und ausdrücklich zugeordnete Pflegekind-Sprache.
4 fehlerhafte Annotationen außerhalb der ausgewerteten beziehungsweise zwingend benötigten Codes wurden ausgeschlossen; siehe `excluded_annotations.csv`. Fehlerhafte ausgewählte Codes, Sprechintervalle oder Pflegesituationen führen zum Abbruch.

## Code-Präsenz

Für jeden ausgewählten Code wird sein Vorhandensein beziehungsweise Fehlen verglichen, unabhängig von der Anzahl seiner Wiederholungen. Ein Video oder eine zugeordnete beziehungsweise einseitige Pflegesituation bildet jeweils eine binäre Beobachtungseinheit. Bei einer einseitigen Situation gilt die fehlende Gegenseite als nicht vorhanden. Die Gesamtzeile auf Situationsebene fasst alle Kombinationen aus Situation und ausgewähltem Code zusammen; Kappa und Alpha beruhen dort auf diesen gepoolten Zählungen, nicht auf Mittelwerten der Einzelcodes. Gemeinsame Abwesenheiten und die Auswahl der Codes beeinflussen das Ergebnis. Mehrere Kombinationen können zum selben Video gehören; Konfidenzintervalle ziehen deshalb ganze Videos. Die Übereinstimmung wird als Anteil von 0 bis 1 dargestellt.

| Ebene | Code | Beide vorhanden | Nur alt | Nur neu | Beide fehlend | Übereinstimmung | Kappa | Kappa p (zweiseitig) | Krippendorffs Alpha | Positive spezifische Übereinstimmung (positiver F1) | Negative spezifische Übereinstimmung |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Video | 2.2.3.4 | 8 | 0 | 2 | 0 | 0.800 | 0.000 | nicht definiert | -0.056 | 0.889 | 0.000 |
| Video | 2.2.3.14 | 10 | 0 | 0 | 0 | 1.000 | nicht definiert | nicht definiert | nicht definiert | 1.000 | nicht definiert |
| Video | 6.4.3 | 2 | 1 | 0 | 7 | 0.900 | 0.737 | 0.016 | 0.747 | 0.800 | 0.933 |
| Video | 6.4.4 | 6 | 0 | 0 | 4 | 1.000 | 1.000 | 0.002 | 1.000 | 1.000 | 1.000 |
| Video | 6.4.5 | 3 | 2 | 0 | 5 | 0.800 | 0.600 | 0.038 | 0.604 | 0.750 | 0.833 |
| Video | Gesamt | 29 | 3 | 2 | 16 | 0.900 | nicht definiert | nicht definiert | nicht definiert | 0.921 | 0.865 |
| Pflegesituation | 2.2.3.4 | 10 | 0 | 2 | 1 | 0.846 | 0.435 | 0.057 | 0.432 | 0.909 | 0.500 |
| Pflegesituation | 2.2.3.14 | 12 | 1 | 0 | 0 | 0.923 | 0.000 | nicht definiert | 0.000 | 0.960 | 0.000 |
| Pflegesituation | 6.4.3 | 2 | 2 | 0 | 9 | 0.846 | 0.581 | 0.021 | 0.583 | 0.667 | 0.900 |
| Pflegesituation | 6.4.4 | 6 | 1 | 2 | 4 | 0.769 | 0.530 | 0.053 | 0.545 | 0.800 | 0.727 |
| Pflegesituation | 6.4.5 | 3 | 2 | 0 | 8 | 0.846 | 0.649 | 0.012 | 0.653 | 0.750 | 0.889 |
| Pflegesituation | Gesamt | 33 | 6 | 4 | 22 | 0.846 | 0.684 | <0.001 | 0.686 | 0.868 | 0.815 |

Kappa-p-Werte: asymptotischer zweiseitiger Normaltest von H₀: κ = 0 mit `statsmodels.stats.inter_rater.cohens_kappa` und der Varianz unter H₀. Die p-Werte sind nicht für multiples Testen korrigiert und setzen unabhängige Beobachtungseinheiten voraus. Bei nur zehn Videos ist die Normalapproximation unsicher; auf Situationsebene und bei gepoolten Codes berücksichtigt dieser Standardtest die Abhängigkeiten innerhalb eines Videos nicht. Die Video-Bootstrap-Intervalle bleiben davon getrennt. Bei undefiniertem Kappa oder einer Nullvarianz unter H₀ ist auch der Test nicht definiert. Ein kleiner p-Wert belegt keine ausreichend hohe Reliabilität. Quelle: [statsmodels](https://www.statsmodels.org/stable/generated/statsmodels.stats.inter_rater.cohens_kappa.html).

Für die Gesamtwerte auf Pflegesituationsebene (95%-Perzentilintervalle aus dem Video-Bootstrap mit 2000 Wiederholungen):
- Übereinstimmung: **0.846**, 95%-Konfidenzintervall [0.688, 0.980]; 2000 von 2000 Wiederholungen definiert.
- Positive spezifische Übereinstimmung: **0.868**, 95%-Konfidenzintervall [0.699, 0.984]; 2000 von 2000 Wiederholungen definiert.
- Negative spezifische Übereinstimmung: **0.815**, 95%-Konfidenzintervall [0.667, 0.968]; 2000 von 2000 Wiederholungen definiert.
- Cohen’s Kappa: **0.684**, 95%-Konfidenzintervall [0.376, 0.953]; 2000 von 2000 Wiederholungen definiert.
- Krippendorffs Alpha: **0.686**, 95%-Konfidenzintervall [0.376, 0.954]; 2000 von 2000 Wiederholungen definiert.

Die Intervalle beschreiben die Unsicherheit unter dem Video-Bootstrap. Bei wenigen Videos können sie trotz vieler Wiederholungen instabil sein.

## Zeitliche Ereignisübereinstimmung

Beginn und Ende dürfen jeweils um höchstens 60000 ms voneinander abweichen (einschließlich des Grenzwerts). Gleiche Codes werden innerhalb zugeordneter Situationen chronologisch eins zu eins abgeglichen.
Gesamt-F1 aus zusammengefassten Zählungen: **0.743**, 95%-Konfidenzintervall aus dem Video-Bootstrap [0.679, 0.822]. Zugeordnet wurden 68 Ereignisse; alt=113, neu=70.

Die Standardabweichung beschreibt die Streuung der absoluten Abweichungen zugeordneter Ereignisse (Stichprobenstandardabweichung mit n − 1); bei weniger als zwei Zuordnungen ist sie nicht definiert. Sie berücksichtigt nur Ereignisse innerhalb der Toleranz.

| Code | Ereignisse alt | Ereignisse neu | Zugeordnet | F1 | Mittlere absolute Anfangsabweichung (ms) | SD absolute Anfangsabweichung (ms) | Mittlere absolute Endabweichung (ms) | SD absolute Endabweichung (ms) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 6.1.1 | 13 | 12 | 12 | 0.960 | 1333.333 | 1579.605 | 5725.000 | 8738.954 |
| 6.1.2 | 12 | 9 | 9 | 0.857 | 1633.333 | 1774.119 | 355.556 | 441.902 |
| 6.1.3 | 13 | 12 | 12 | 0.960 | 416.667 | 507.818 | 416.667 | 540.763 |
| 6.1.4 | 11 | 11 | 10 | 0.909 | 430.000 | 592.640 | 5820.000 | 9383.650 |
| 5.3.1 | 64 | 26 | 25 | 0.556 | 1228.000 | 1850.567 | 1752.000 | 2522.585 |
| Gesamt | 113 | 70 | 68 | 0.743 | 1039.706 | 1517.474 | 2630.882 | 5640.161 |

## Pflegekind-Sprache und alle Kindansprachen

Das Pflegekind wird je Person und Situation unabhängig bestimmt: Es ist der eindeutig zugeordnete Code aus 5.5.1–5.5.10 mit exakt dem Beginn und Ende der 6.1.1-Pflegesituation. Ein Sprechintervall zählt als Pflegekind-Sprache, wenn dieses Kind außerdem mit exakt dem Beginn und Ende des Sprechintervalls kodiert ist. Weitere gleichzeitig angesprochene Personen sind erlaubt. Kindnummern können sich zwischen den kodierenden Personen unterscheiden. Gruppenansprachen und Intervalle ohne passende Kindreferenz werden separat protokolliert und nicht als bestätigte Pflegekind-Sprache gewertet. Die Ereignistoleranz lockert diese exakte Zuordnung nicht.

### Zuordnung der Sprechintervalle

| Sprachvariante | Eingeschlossene Videos | Ausgeschlossene Videos | Intervalle alt | Intervalle neu | Zugeordnet | Ereignis-F1 |
|---|---:|---:|---:|---:|---:|---:|
| Alle Kindansprachen | 10 | 0 | 64 | 26 | 25 | 0.556 |
| Pflegekind-Sprache | 10 | 0 | 50 | 25 | 24 | 0.640 |

Für den Sprechzeitvergleich wird ausschließlich die gemeinsame Zeit innerhalb zugeordneter Pflegesituationen verwendet. Überlappende Intervalle werden vereinigt; eine zeitliche Toleranz wird nicht angewandt. Nicht zugeordnete Situationen bleiben im Präsenz- und Ereignisvergleich enthalten, haben jedoch kein gemeinsames Zeitfenster für den Dauervergleich. Dauer-Dice = 2 × überlappende Sprechzeit / (alte + neue Sprechzeit). Dieser Wert ist weniger empfindlich gegenüber der Aufteilung einer Sprechepisode in mehrere Äußerungen.

### Gemeinsame Sprechzeit

| Sprachvariante | Gemeinsame Beobachtungszeit (s) | Sprechzeit alt (s) | Sprechzeit neu (s) | Überlappung (s) | Dauer-Dice | Alte Sprechzeit durch neue abgedeckt |
|---|---:|---:|---:|---:|---:|---:|
| Alle Kindansprachen | 194.000 | 71.700 | 86.600 | 59.100 | 0.747 | 0.824 |
| Pflegekind-Sprache | 194.000 | 60.600 | 78.500 | 51.800 | 0.745 | 0.855 |

Präsenz, Kappa und Krippendorffs Alpha, Ereigniszuordnungen, Dauer-Dice und Jaccard, gerichtete Abdeckungsanteile und Bootstrap-Konfidenzintervalle stehen in `speech_presence_scores.csv`, `speech_timing_scores.csv` und `speech_coverage.csv`. `speech_recipients.csv` und `speech_care_children.csv` dokumentieren die Filterentscheidungen. Fehlt eine eindeutige Pflegekindzuordnung, wird das gesamte Video aus der separaten Pflegekind-Auswertung ausgeschlossen; fehlende Information wird nicht als fehlende Sprache behandelt. Die Videozahlen weisen diese Ausschlüsse aus. Bei `speech_scope=pflegekind` in der Hauptauswertung führt eine fehlende Zuordnung stattdessen zum Abbruch, sofern 5.3.1 ausgewertet wird. Sprechintervalle ohne passende Kindreferenz bleiben im Prüfprotokoll sichtbar. Ein für eine Situation bestätigtes Pflegekind-Sprechintervall gilt nicht automatisch auch für eine überlappende andere Situation.

## Dauer der Codes

Für die vollständigen Dauern werden die beibehaltenen Originalintervalle pro Code und Video vereinigt und anschließend über Videos aufsummiert. Grenzüberschreitende Ereignisse und nicht zugeordnete Situationen zählen mit; die Intervalle werden nicht auf Pflegesituationen begrenzt. Ohne zusätzliche Einstellung werden alle Codes aus `presence_codes` und `timing_codes` berücksichtigt. Mit `duration_codes` kann eine eigene Liste gewählt werden. Für 5.3.1 gilt die Sprachvariante der Hauptauswertung (`speech_scope`).

Differenz = neu − alt; Veränderung (%) = 100 × Differenz / alt, bei einer alten Dauer von null nicht definiert. Die mittlere absolute Videodifferenz mittelt die absoluten Dauerabweichungen der einzelnen Videos, damit sich positive und negative Unterschiede nicht gegenseitig aufheben. Die Dauern im gemeinsamen Fenster und der Dauer-Dice verwenden dagegen die Schnittmengen zugeordneter Situationen, ohne Ereignistoleranz. Bei 6.1.1 stimmen diese gemeinsamen Dauern konstruktionsbedingt überein; unterschiedliche Situationsgrenzen zeigen sich in den vollständigen Dauern und den Grenz- beziehungsweise Ereignisvergleichen. Die Tabelle zeigt Sekunden; detaillierte Dauern und deren Konfidenzintervalle in den CSVs verwenden Millisekunden.

| Code | Dauer alt (s) | Dauer neu (s) | Differenz (s) | Absolute Differenz (s) | Veränderung (%) | Mittlere absolute Videodifferenz (s) | Alt im gemeinsamen Fenster (s) | Neu im gemeinsamen Fenster (s) | Dauer-Dice |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2.2.3.4 | 54.100 | 55.000 | 0.900 | 0.900 | 1.664 | 1.090 | 52.700 | 53.000 | 0.878 |
| 2.2.3.14 | 64.900 | 53.300 | -11.600 | 11.600 | -17.874 | 1.160 | 58.200 | 51.300 | 0.932 |
| 6.4.3 | 9.000 | 4.300 | -4.700 | 4.700 | -52.222 | 0.510 | 6.000 | 4.300 | 0.757 |
| 6.4.4 | 37.900 | 44.500 | 6.600 | 6.600 | 17.414 | 1.020 | 34.900 | 42.400 | 0.831 |
| 6.4.5 | 15.200 | 9.500 | -5.700 | 5.700 | -37.500 | 0.690 | 15.200 | 9.300 | 0.710 |
| 6.1.1 | 246.400 | 233.200 | -13.200 | 13.200 | -5.357 | 7.620 | 194.000 | 194.000 | 1.000 |
| 6.1.2 | 116.500 | 115.200 | -1.300 | 1.300 | -1.116 | 2.190 | 107.000 | 107.800 | 0.976 |
| 6.1.3 | 68.600 | 66.800 | -1.800 | 1.800 | -2.624 | 1.240 | 63.300 | 64.500 | 0.941 |
| 6.1.4 | 61.200 | 51.300 | -9.900 | 9.900 | -16.176 | 6.610 | 23.500 | 21.900 | 0.943 |
| 5.3.1 | 93.100 | 98.100 | 5.000 | 5.000 | 5.371 | 4.280 | 71.700 | 86.600 | 0.747 |

Die ungerundeten Kennwerte und Bootstrap-Konfidenzintervalle stehen in `code_duration_scores.csv`, die Dauern pro Video in `code_durations_by_video.csv`. Unterschiedliche Codes können gleichzeitig auftreten; ihre Dauern dürfen daher nicht wie voneinander getrennte Beobachtungszeiten aufsummiert werden.

### Signifikanz der Dauerunterschiede

Pro Code wird die vollständige Dauer je Video zwischen den beiden Personen gepaart verglichen (Differenz = neu − alt). Der zweiseitige gepaarte Permutationstest verwendet die mittlere vorzeichenbehaftete Videodifferenz als Teststatistik. Unter H₀ müssen die Personenbezeichnungen innerhalb eines Videos austauschbar sein (symmetrische Differenzen um null); die Videos werden als unabhängig vorausgesetzt. Mehrere Situationen desselben Videos werden vorher zusammengefasst. Der Test benötigt keine Normalverteilungsannahme. Auch Videos mit beidseitiger Abwesenheit zählen mit. Bis 16 Videos werden alle 2^N Vertauschungen ausgewertet; darüber 65536 zufällige Vertauschungen mit Startwert 42. Holm korrigiert über alle hier ausgewerteten Dauercodes; signifikant bedeutet korrigiertes p < 0.05. Ein nicht signifikanter Unterschied belegt keine Gleichwertigkeit oder zeitliche Übereinstimmung. Bei abhängigen Videos derselben Person ist eine Analyse auf Personenebene erforderlich. Quelle: [SciPy permutation_test](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.permutation_test.html).

| Code | Videopaare | Paare mit Differenz ≠ 0 | Mittlere Differenz (s/Video) | 95%-Bootstrap-KI (s/Video) | p (zweiseitig) | p (Holm) | Signifikant (Holm) |
|---|---:|---:|---:|---|---:|---:|---|
| 2.2.3.4 | 10 | 9 | 0.090 | [-0.790, 1.170] | 0.906 | 1.000 | nein |
| 2.2.3.14 | 10 | 8 | -1.160 | [-2.310, -0.280] | 0.008 | 0.078 | nein |
| 6.4.3 | 10 | 3 | -0.470 | [-1.370, 0.040] | 0.500 | 1.000 | nein |
| 6.4.4 | 10 | 6 | 0.660 | [-0.290, 2.120] | 0.531 | 1.000 | nein |
| 6.4.5 | 10 | 4 | -0.570 | [-1.470, 0.100] | 0.375 | 1.000 | nein |
| 6.1.1 | 10 | 10 | -1.320 | [-8.541, 4.800] | 0.762 | 1.000 | nein |
| 6.1.2 | 10 | 10 | -0.130 | [-1.860, 1.650] | 0.883 | 1.000 | nein |
| 6.1.3 | 10 | 8 | -0.180 | [-1.550, 1.150] | 0.656 | 1.000 | nein |
| 6.1.4 | 10 | 10 | -0.990 | [-8.890, 5.060] | 0.861 | 1.000 | nein |
| 5.3.1 | 10 | 10 | 0.500 | [-3.150, 3.610] | 0.811 | 1.000 | nein |

## Definitionen und Reproduzierbarkeit

- Beide kodierenden Personen werden symmetrisch behandelt; keine gilt als fehlerfreie Referenz.
- Jede 6.1.1-Pflegesituation wird exportiert. Annotationen mit positiver Überlappung behalten ihre ursprünglichen, ungekürzten Zeitstempel. Setting- oder Pflegetypzuordnungen sind keine Voraussetzung. Eine bloße Berührung der Intervallgrenzen und Intervalle ohne Dauer haben keine positive Überlappung.
- Verglichen werden vollständige numerische Code-IDs; Bezeichnungen werden ignoriert. Identische Kopien mit gleichem Code, Beginn und Ende werden nicht mehrfach gezählt. Ein Ereignis über mehrere Situationen zählt bei Video-Präsenz und Ereignisvergleich einmal, bei der Situationspräsenz in jeder Situation, der es zugeordnet ist.
- Die Situationszuordnung maximiert zunächst die Anzahl chronologisch überlappender Paare, dann deren gesamte relative Überlappung (Schnittmenge geteilt durch Vereinigungsmenge). Abweichende Pflegetypen verhindern kein Paar. Die Ereigniszuordnung maximiert zuerst die Trefferzahl und minimiert danach die absoluten Grenzabweichungen. Die Zeilenposition `Sequence_Order` wird nicht verglichen; gleichzeitig auftretende unterschiedliche Codes bleiben unabhängig.
- Übereinstimmung = (beide vorhanden + beide fehlend) / Beobachtungseinheiten. Kappa = (beobachtete − erwartete Übereinstimmung) / (1 − erwartete Übereinstimmung). Die erwartete Übereinstimmung beruht auf den binären Randhäufigkeiten beider Personen. Die Gesamtzeile auf Situationsebene verwendet die zusammengefassten binären Bewertungen aller ausgewählten Codes.
- Krippendorffs Alpha wird nominal für dieselben binären Präsenzeinheiten pro Code berechnet: Alpha = 1 − D_o / D_e. Bei N Einheiten, m abweichenden Bewertungspaaren sowie n_1 vorhandenen und n_0 fehlenden Bewertungen über beide Personen gilt D_o = m / N und D_e = n_1 × n_0 / (N × (2N − 1)). Die erwartete Abweichung verwendet die gemeinsamen Kategoriehäufigkeiten mit Korrektur für endliche Stichproben. Negative Alpha-Werte sind möglich. Die Gesamtzeile auf Situationsebene verwendet die zusammengefassten Bewertungen aller Codes. Einseitige Situationen werden auch hier als Abwesenheit auf der Gegenseite gewertet; dies ist kein Alpha für die Segmentierung.
- Positiver F1 = 2 × beide vorhanden / (2 × beide vorhanden + nur alt + nur neu). Dieser Wert entspricht bei zwei Personen der positiven spezifischen Übereinstimmung. Negative spezifische Übereinstimmung = 2 × beide fehlend / (2 × beide fehlend + nur alt + nur neu). Bei ausschließlich negativen beziehungsweise positiven Bewertungen ist die positive beziehungsweise negative spezifische Übereinstimmung nicht definiert. Gesamtwerte beruhen auf gepoolten Zählungen über alle ausgewählten Codes. Die CSVs enthalten beide Kennwerte mit Status, Bootstrap-Intervallen und Anzahl definierter Wiederholungen. Ereignis-F1 = 2 × zugeordnete Ereignisse / (alte + neue Ereignisse). Für den Ereignisvergleich werden keine künstlichen Zeitraster mit negativen Beobachtungen gebildet.
- Der Gesamt-F1 verwendet zusammengefasste Zählungen (Mikro-Mittelung); `macro_f1` mittelt die definierten F1-Werte pro Code. Bei beidseitiger Abwesenheit ist F1 nicht definiert; bei identischen konstanten Bewertungen oder ohne Beobachtungseinheiten sind Kappa und Alpha nicht definiert. Die detaillierten CSVs enthalten dann leere Felder und Statusangaben; solche Werte gehen nicht in Makro-Mittelwerte ein.
- Alpha sowie seine Video-Bootstrap-Konfidenzintervalle und die Anzahl definierter Wiederholungen stehen in `presence_scores.csv` und `speech_presence_scores.csv` unter `krippendorff_alpha`, `krippendorff_alpha_ci_low`, `krippendorff_alpha_ci_high` und `krippendorff_alpha_bootstrap_valid`.
- Die Konfidenzintervalle verwenden 2000 Bootstrap-Wiederholungen mit ganzen Videos, dem Startwert 42 und den Perzentilen 2,5 % und 97,5 %. Situations- und Ereigniszeilen werden nicht unabhängig gezogen. Die CSVs nennen die Anzahl definierter Wiederholungen pro Kennwert. Undefinierte Wiederholungen werden ausgelassen; bei nur zehn Videos können die Intervalle instabil sein.
- Die Kennwerte beziehen sich auf Annotationen, die Pflegesituationen überlappen, nicht auf die gesamte Videozeit. Die Situationsübereinstimmung hängt von der beschriebenen Überlappungszuordnung ab und ist kein eigenständiges Maß für Sequenzreihenfolge oder Segmentierungs-Kappa.
- Korrigierte Sequenzen, Einzelentscheidungen, Ereignispaare, nicht zugeordnete Ereignisse, Code-Zusammenfassungen, Konfidenzintervalle und verwendete Einstellungen liegen neben diesem Bericht. Jede dargestellte Tabelle wird außerdem als eigene CSV unter `report_tables/` ausgegeben, mit denselben deutschen Spalten, Zeilen, Rundungen und Angaben „nicht definiert“. Die Dateinamen bleiben unverändert; die detaillierten Datendateien behalten ihre technischen Spaltennamen und numerische Genauigkeit. Zahlen verwenden weiterhin den Dezimalpunkt. Die ursprünglichen Analysedateien bleiben erhalten.

Codes für den Präsenzvergleich: 2.2.3.4, 2.2.3.14, 6.4.3, 6.4.4, 6.4.5.
Codes für den Ereignisvergleich: 6.1.1, 6.1.2, 6.1.3, 6.1.4, 5.3.1.

Methodische Quellen: [Cohen's Kappa](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.cohen_kappa_score.html), [Krippendorffs Alpha](https://www.asc.upenn.edu/sites/default/files/2021-03/Computing%20Krippendorff%27s%20Alpha-Reliability.pdf), [F1](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.f1_score.html).
