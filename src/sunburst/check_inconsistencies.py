import pandas as pd

input_file = "out_paths_cooccurrence_same_window.csv"

df = pd.read_csv(input_file)

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

print("\n==============================")
print("A) Position (hinten/seite/vorne) OHNE FK führt Hdlg.")
print("==============================")
print(df_A[["bundle_key", "bundle_label", "count"]])

print("\n==============================")
print("B) FK führt Hdlg. OHNE Position (hinten/seite/vorne)")
print("==============================")
print(df_B[["bundle_key", "bundle_label", "count"]])

df_A.to_csv("filter_A_position_ohne_fk.csv", index=False)
df_B.to_csv("filter_B_fk_ohne_position.csv", index=False)

print("\nDateien gespeichert:")
print(" - filter_A_position_ohne_fk.csv")
print(" - filter_B_fk_ohne_position.csv")
