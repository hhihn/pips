import pandas as pd
import logging
from pathlib import Path

if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

logger = logging.getLogger(__name__)

ANALYSIS_ROOT = Path("csv_analysen")
THEME_DIR = ANALYSIS_ROOT / "konsistenz"
THEME_DIR.mkdir(parents=True, exist_ok=True)

input_file = ANALYSIS_ROOT / "cooccurrence" / "out_paths_cooccurrence_same_window.csv"

df = pd.read_csv(str(input_file))

fk_term = "FK führt Hdlg. für Kind aus"

pos_terms = [
    "FK führt Pflegehandlung von hinten durch",
    "FK führt Pflegehandlung von der Seite durch",
    "FK führt Pflegehandlung von vorne durch",
]

mask_fk = df["bundle_label"].str.contains(fk_term, na=False, regex=False)

mask_pos = pd.Series(False, index=df.index)
for term in pos_terms:
    mask_pos = mask_pos | df["bundle_label"].str.contains(term, na=False, regex=False)

# A) Position vorhanden, aber FK führt Hdlg. NICHT
df_A = df[mask_pos & ~mask_fk]

# B) FK führt Hdlg. vorhanden, aber keine Position
df_B = df[mask_fk & ~mask_pos]

logger.info("==============================")
logger.info("A) Position (hinten/seite/vorne) OHNE FK führt Hdlg.")
logger.info("==============================")
logger.info("\n%s", df_A[["bundle_key", "bundle_label", "count"]])

logger.info("==============================")
logger.info("B) FK führt Hdlg. OHNE Position (hinten/seite/vorne)")
logger.info("==============================")
logger.info("\n%s", df_B[["bundle_key", "bundle_label", "count"]])

out_a = THEME_DIR / "filter_A_position_ohne_fk.csv"
out_b = THEME_DIR / "filter_B_fk_ohne_position.csv"
df_A.to_csv(str(out_a), index=False)
df_B.to_csv(str(out_b), index=False)

logger.info("Dateien gespeichert:")
logger.info("- %s", out_a)
logger.info("- %s", out_b)
