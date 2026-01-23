# Sunburst für typische Reihenfolgen (Übergangsmuster) aus deinen Sequenzen
# - bildet pro (Filename,id,target) eine "Zustandssequenz" (zeitlich geordnet)
# - fasst parallele Codes zu Frames zusammen
# - mappt Frames -> STATE (hier: nur Phase 6.1.2/6.1.3/6.1.4; leicht erweiterbar)
# - zählt Pfade (k Schritte) und visualisiert sie als Sunburst
#
# Voraussetzungen:
#   pip install plotly pandas
#
# Input-DF: muss Spalten haben: Filename, Sequence_Code, Sequence_Start, Sequence_End, id
# Zeiten sind wie "0:00:29,6" (Komma als Dezimal)
#
import re
import numpy as np
import pandas as pd
import plotly.express as px

PHASE_CODES = {"6.1.2", "6.1.3", "6.1.4"}
PHASE_PRIORITY = {"6.1.2": 0, "6.1.3": 1, "6.1.4": 2}

def parse_time_to_seconds(s: str) -> float:
    """'H:MM:SS,ms' -> seconds (float)."""
    if pd.isna(s):
        return np.nan
    s = str(s).strip().replace('"', '')
    # allow comma decimal
    s = s.replace(",", ".")
    # H:MM:SS.xxx
    parts = s.split(":")
    if len(parts) != 3:
        raise ValueError(f"Unexpected time format: {s}")
    h = int(parts[0])
    m = int(parts[1])
    sec = float(parts[2])
    return h * 3600 + m * 60 + sec

def extract_code_and_target(seq_code: str):
    """
    '6.1.2 PK' -> ('6.1.2','PK')
    '2.2.3.14 AK' -> ('2.2.3.14','AK')
    """
    if pd.isna(seq_code):
        return None, None
    s = str(seq_code).strip().replace('"', '')
    m = re.match(r"^(\d+(?:\.\d+)*)\s+(PK|AK)$", s)
    if not m:
        # fallback: try split last token
        parts = s.split()
        if len(parts) >= 2 and parts[-1] in ("PK", "AK"):
            return parts[0], parts[-1]
        return s, None
    return m.group(1), m.group(2)

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[["code", "target"]] = df["Sequence_Code"].apply(
        lambda x: pd.Series(extract_code_and_target(x))
    )
    df["start_s"] = df["Sequence_Start"].apply(parse_time_to_seconds)
    df["end_s"] = df["Sequence_End"].apply(parse_time_to_seconds)
    # safety
    df = df.dropna(subset=["Filename", "id", "code", "start_s", "end_s"])
    df.loc[df["end_s"] < df["start_s"], ["start_s", "end_s"]] = df.loc[
        df["end_s"] < df["start_s"], ["end_s", "start_s"]
    ].values
    return df

def build_frames(df_case: pd.DataFrame):
    """
    df_case: rows for ONE case (same Filename,id,target).
    Returns list of (t_start, t_end, frozenset(active_codes)).
    A frame is a minimal interval where set of active codes stays constant.
    """
    times = sorted(set(df_case["start_s"]).union(set(df_case["end_s"])))
    frames = []
    for t0, t1 in zip(times[:-1], times[1:]):
        if t1 <= t0:
            continue
        active = df_case[(df_case["start_s"] <= t0) & (df_case["end_s"] >= t1)]["code"]
        if not active.empty:
            frames.append((t0, t1, frozenset(active.tolist())))
    return frames

def frame_to_state_phase_only(codes):
    """Map a set of active codes to a single STATE = phase code (6.1.2/6.1.3/6.1.4)."""
    phases = [c for c in codes if c in PHASE_CODES]
    if not phases:
        return None
    return sorted(phases, key=lambda x: PHASE_PRIORITY[x])[0]

def state_sequence_for_case(df_case: pd.DataFrame, state_fn=frame_to_state_phase_only):
    """Frames -> sequence of states; consecutive duplicates are collapsed."""
    frames = build_frames(df_case)
    seq = []
    for _, _, codes in frames:
        st = state_fn(codes)
        if st is None:
            continue
        if not seq or seq[-1] != st:
            seq.append(st)
    return seq

def sequences_from_df(df: pd.DataFrame, target="PK", state_fn=frame_to_state_phase_only):
    """
    Build sequences for each (Filename,id,target). Returns list of dicts:
      {"Filename":..., "id":..., "target":..., "seq":[...]}
    """
    out = []
    for (fn, case_id, targ), g in df.groupby(["Filename", "id", "target"], dropna=False):
        if target is not None and targ != target:
            continue
        seq = state_sequence_for_case(g, state_fn=state_fn)
        if len(seq) >= 1:
            out.append({"Filename": fn, "id": case_id, "target": targ, "seq": seq})
    return out

def paths_k_steps(seq, k=4, add_end=True):
    """
    Turns a sequence into one path of length k (root->...).
    If shorter: pad with END.
    If longer: take first k by default (you can also build sliding windows if you want).
    """
    path = seq[:k]
    if add_end:
        # make all paths length k by padding with END
        while len(path) < k:
            path.append("END")
    return path

def build_sunburst_table(seqs, k=4, mode="first_path"):
    """
    mode:
      - "first_path": use first k states of each sequence (typische Abläufe ab Start)
      - "sliding": count all sliding windows of length k inside each sequence (lokale Muster)
    Returns df with columns level_1..level_k and value=count
    """
    rows = []
    for item in seqs:
        s = item["seq"]
        if mode == "sliding":
            if len(s) == 0:
                continue
            if len(s) < k:
                rows.append(paths_k_steps(s, k=k, add_end=True))
            else:
                for i in range(0, len(s) - k + 1):
                    rows.append(s[i:i+k])
        else:
            rows.append(paths_k_steps(s, k=k, add_end=True))

    if not rows:
        return pd.DataFrame()

    df_paths = pd.DataFrame(rows, columns=[f"level_{i}" for i in range(1, k+1)])
    df_counts = df_paths.value_counts().reset_index(name="count")
    return df_counts

def plot_sunburst(df_counts: pd.DataFrame, title="Sunburst", max_depth=None):
    """
    df_counts: columns level_1..level_k + count
    """
    if df_counts.empty:
        raise ValueError("df_counts ist leer – keine Pfade gefunden.")
    path_cols = [c for c in df_counts.columns if c.startswith("level_")]
    fig = px.sunburst(
        df_counts,
        path=path_cols,
        values="count",
        title=title,
        maxdepth=max_depth
    )
    fig.update_traces(insidetextorientation="radial")
    fig.show()

# ---------------------------
# Anwendung: (1) Datei-spezifisch, (2) global gemittelt
# ---------------------------

df_raw = pd.read_csv("extracted_sequences.csv")  # <- echte Datei
df = preprocess(df_raw)

# 1) Sequenzen aus allen Fällen (z.B. nur PK)
seqs_all = sequences_from_df(df, target="PK", state_fn=frame_to_state_phase_only)

# 2a) Sunburst "über alles" (jeder Fall zählt 1 Pfad) = global
df_counts_all = build_sunburst_table(seqs_all, k=4, mode="first_path")
plot_sunburst(df_counts_all, title="Global: typische Start-Reihenfolgen (k=4) – PK", max_depth=4)

# 2b) Alternativ: lokale Muster als Sliding Window
# df_counts_all_local = build_sunburst_table(seqs_all, k=3, mode="sliding")
# plot_sunburst(df_counts_all_local, title="Global: lokale Übergangsmuster (Sliding, k=3) – PK", max_depth=3)

# 3) Sunburst pro Datei (Filename) – gleiche Logik, aber gefiltert
def sunburst_per_filename(df: pd.DataFrame, filename: str, target="PK", k=4, mode="first_path"):
    seqs = sequences_from_df(df[df["Filename"] == filename], target=target, state_fn=frame_to_state_phase_only)
    df_counts = build_sunburst_table(seqs, k=k, mode=mode)
    plot_sunburst(df_counts, title=f"{filename}: Reihenfolgen (k={k}, {mode}) – {target}", max_depth=k)

# Beispiel:
sunburst_per_filename(df, "11-P-4_transformed.xlsx", target="PK", k=4, mode="first_path")
