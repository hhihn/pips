import json
from typing import List, Tuple, Dict

# -------------------------------------------------------------------
# 1) Labeling (dein Mapping)
# -------------------------------------------------------------------
LABEL_MAP: Dict[str, str] = {
    # innen / Auslöser
    "2.1.2.3": "FK benennt Ziel",
    "6.5.1": "Kindliches Signal",
    # mitte
    "6.4.2": "Aufforderung Vorb.",
    "6.5.4": "Verbale Begleitung",
    # außen
    "2.1.3.1": "FK führt Hdlg. aus",
    "6.5.3": "K führt Hdlg aus",
    "6.4.3": "FK von vorn",
    "6.4.4": "FK von der Seite",
    "6.4.5": "FK von hinten",
    # außenring
    "2.1.3.5": "Unterstützung nur verbal",
    "2.2.3.14": "KK Objektbezug",
    "2.2.3.4": "KK Halten",
    "2.1.3.1 & 6.4.3": "FK führt Hdlg. von vorn aus",
    "2.1.3.1 & 6.4.4": "FK führt Hdlg. von der Seite aus",
    "2.1.3.1 & 6.4.5": "FK führt Hdlg. von Hinten aus",
    "2.1.3.1 & 2.2.3.4": "FK führt Hdlg. und hält Kind fest",
    "2.2.3.4 & 2.2.3.14": "KK Halten + Objektbezug",
    "2.1.3.1 & 2.2.3.14": "FK führt Hdlg. aus + Objektbezug",
}

labels = json.load(open("../output.json", "r"))
for key, label in LABEL_MAP.items():
    LABEL_MAP[key] = labels.get(key, label)

print(json.dumps(LABEL_MAP, indent=2, ensure_ascii=False))
PLACEHOLDER_OTHER = "Andere"


# -------------------------------------------------------------------
# 2) Prioritätsliste
# -------------------------------------------------------------------
PRIO_GROUPS: List[Tuple[str, List[str]]] = [
    ("innen", ["2.1.2.3", "6.5.1"]),
    ("mitte", ["6.4.2", "6.5.4"]),
    ("aussen", ["2.1.3.1", "6.5.3", "6.4.3", "6.4.4", "6.4.5"]),
    ("aussenring", ["2.1.3.5", "2.2.3.14", "2.2.3.4"]),
]

CODE_TO_PRIO = {}
for gi, (_gname, codes) in enumerate(PRIO_GROUPS):
    for ci, c in enumerate(codes):
        CODE_TO_PRIO[c] = (gi, ci)

GROUP_NAME_TO_CODES: Dict[str, set] = {name: set(codes) for name, codes in PRIO_GROUPS}

# Kombi-Regeln (innerhalb exakt gleicher (start,end)-Bundles)
COMBO_RULES: List[Tuple[Tuple[str, str], str]] = [
    (("2.1.3.1", "6.4.3"), "2.1.3.1 & 6.4.3"),
    (("2.1.3.1", "6.4.4"), "2.1.3.1 & 6.4.4"),
    (("2.1.3.1", "6.4.5"), "2.1.3.1 & 6.4.5"),
    (("2.1.3.1", "2.2.3.14"), "2.1.3.1 & 2.2.3.14"),
    (("2.1.3.1", "2.2.3.4"), "2.1.3.1 & 2.2.3.4"),
    (("2.2.3.4", "2.2.3.14"), "2.2.3.4 & 2.2.3.14"),
]
COMBO_RULES_KEYS = [l[0][0] for l in COMBO_RULES]

ALLOWED_CODES = set(CODE_TO_PRIO.keys()).union(set(COMBO_RULES_KEYS))
COMBO_RULES_KEYS = [l[0][1] for l in COMBO_RULES]
ALLOWED_CODES.union(COMBO_RULES_KEYS)

# Welche Tokens zählen als "Action vorhanden?" (sonst Pfad verwerfen)
ACTING_CODES = {
    "2.1.3.1",  # "FK führt Hdlg. für Kind aus"
    "6.5.3",  # K führt Pflegehandlung eigenständig durch
    "2.1.3.1 & 6.4.3",  # FK führt Pflegehandlung von vorne durch
    "2.1.3.1 & 6.4.4",  # FK führt Pflegehandlung von der Seite durch
    "2.1.3.1 & 6.4.5",  # FK führt Pflegehandlung von hinten durch
    "2.1.3.1 & 2.2.3.4",  # halten
    "2.2.3.4 & 2.2.3.14",  # halten & über Gegenstand vermittelte Berührung
    "2.1.3.1 & 2.2.3.14",  # über Gegenstand vermittelte Berührung
}
