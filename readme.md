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