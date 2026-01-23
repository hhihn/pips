import pandas as pd
import json
import re

# === Konfiguration ===
INPUT_XLSX = "../data/codes.xlsx"
OUTPUT_JSON = "output.json"
COLUMN_INDEX = 0  # erste Spalte

# === Excel laden ===
df = pd.read_excel(INPUT_XLSX)

result = {}

for raw in df.iloc[:, COLUMN_INDEX].dropna():
    parts = [p.strip() for p in str(raw).split(">")]

    if len(parts) < 3:
        continue

    # Teil nach dem ersten ">"
    first_text_part = parts[1]
    # Teil nach dem letzten ">"
    last_text_part = parts[-1]

    # Code + Text trennen
    def split_code_text(s):
        match = re.match(r"([\d\.]+)\s+(.*)", s)
        if match:
            return match.group(1), match.group(2)
        return None, s

    _, first_text = split_code_text(first_text_part)
    last_code, last_text = split_code_text(last_text_part)

    if last_code is None:
        continue

    result[last_code] = f"{first_text}: {last_text}"

# === JSON speichern ===
with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print(f"{len(result)} Einträge nach {OUTPUT_JSON} geschrieben.")
