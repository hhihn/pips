#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Liest eine CSV mit Spalten:
  Filename, Sequence_Code, Sequence_Start, Sequence_End, id

Findet pro Filename alle Code-Kombinationen, die parallel auftreten,
definiert als: exakt gleicher Sequence_Start UND Sequence_End.

Erzeugt:
1) Ausgabe pro Parallel-Gruppe (optional)
2) Eine *globale* Liste aller einzigartigen Paare (A,B), wobei (A,B)==(B,A)
   -> Duplikate werden entfernt (auch "beidseitig").

Optional:
- --min_size N: nur Gruppen mit mindestens N Codes ausgeben (Default 2)
- --ignore_codes: Komma-separierte Codes (z.B. 6.1.1,6.1.2) ignorieren
- --show_groups: zusätzlich komplette Gruppen (als Liste) ausgeben
- --out_pairs_csv: speichert die eindeutigen Paare als CSV
"""

import argparse
import csv
import itertools
from collections import defaultdict
from typing import Dict, List, Tuple, Set


def norm_code(s: str) -> str:
    """'6.4.5 PK' -> '6.4.5' (nimmt erstes Token)."""
    s = (s or "").strip()
    return s.split()[0] if s else ""


def norm_time(s: str) -> str:
    """Entfernt Anführungszeichen/Whitespace, lässt String sonst unverändert."""
    return (s or "").strip().strip('"')


def canon_pair(a: str, b: str) -> Tuple[str, str]:
    """Kanonische (unordered) Darstellung eines Paares."""
    return (a, b) if a <= b else (b, a)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--csv_path", default="extracted_sequences.csv", help="Pfad zur CSV"
    )
    ap.add_argument(
        "--min_size", type=int, default=2, help="Min. Gruppengröße für Ausgabe"
    )
    ap.add_argument(
        "--ignore_codes",
        default="6.1.1, 2.1.2.3, 2.2.3.14",
        help="Komma-separierte Code-Liste, die ignoriert werden soll (z.B. '6.1.1,6.1.2')",
    )
    ap.add_argument(
        "--show_groups",
        action="store_true",
        help="Zusätzlich komplette Parallel-Gruppen (nicht nur Paare) ausgeben",
    )
    ap.add_argument(
        "--out_pairs_csv",
        default="",
        help="Optional: Pfad, um eindeutige Paare als CSV zu speichern (Spalten: code_a, code_b)",
    )
    args = ap.parse_args()

    ignore = {c.strip() for c in args.ignore_codes.split(",") if c.strip()}

    # groups[(filename, start, end)] = [code1, code2, ...]
    groups: Dict[Tuple[str, str, str], List[str]] = defaultdict(list)

    with open("extracted_sequences.csv", "r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        required = {"Filename", "Sequence_Code", "Sequence_Start", "Sequence_End"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise SystemExit(f"CSV missing required columns: {sorted(missing)}")

        for row in reader:
            filename = (row.get("Filename") or "").strip()
            code = norm_code(row.get("Sequence_Code") or "")
            start = norm_time(row.get("Sequence_Start") or "")
            end = norm_time(row.get("Sequence_End") or "")

            if not filename or not code or not start or not end:
                continue
            if code in ignore:
                continue

            groups[(filename, start, end)].append(code)

    # Globale Sammlung eindeutiger Paare (unordered)
    unique_pairs: Set[Tuple[str, str]] = set()

    total_groups_printed = 0
    total_group_pairs_printed = 0

    # Ausgabe pro Gruppe + Sammeln der globalen Paare
    for filename, start, end in sorted(groups.keys()):
        codes = groups[(filename, start, end)]
        uniq = sorted(set(codes))  # doppelte Codes innerhalb Gruppe entfernen

        if len(uniq) < args.min_size:
            continue

        # alle Paare dieser Gruppe sammeln
        group_pairs = [canon_pair(a, b) for a, b in itertools.combinations(uniq, 2)]
        for p in group_pairs:
            unique_pairs.add(p)

        if args.show_groups:
            total_groups_printed += 1
            print(f"\n=== {filename} | {start} - {end} | n={len(uniq)} ===")
            print("GROUP:", uniq)
            for a, b in group_pairs:
                print(f"  ({a}, {b})")
                total_group_pairs_printed += 1

    # Gesamtliste (einmalig, beidseitig dedupliziert)
    print("\n" + "=" * 60)
    print("EINDEUTIGE PAARE (global, (A,B)==(B,A))")
    print("=" * 60)

    pairs_sorted = sorted(unique_pairs)  # sortiert für stabile Ausgabe
    for a, b in pairs_sorted:
        print(f"({a}, {b})")

    print("\n" + "-" * 60)
    print(f"Unique pairs: {len(pairs_sorted)}")

    if args.show_groups:
        print(f"Groups printed: {total_groups_printed}")
        print(f"Group pairs printed: {total_group_pairs_printed}")

    # Optional: CSV export
    if args.out_pairs_csv:
        with open(args.out_pairs_csv, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["code_a", "code_b"])
            for a, b in pairs_sorted:
                w.writerow([a, b])
        print(f"[OK] Wrote pairs CSV: {args.out_pairs_csv}")


if __name__ == "__main__":
    main()
