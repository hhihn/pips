"""Validate the generated CSV: 87 records including the header (86 observations).

Run with pytest or directly with Python. Durations are seconds; one hour and
1,000 contacts per situation are deliberately generous sanity limits.
"""


import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
import unittest


CSV_PATH = Path(__file__).resolve().parents[1] / "consolidated_data.csv"
PHASE_DURATIONS = {
    1: "Total_Duration",
    2: "Pre-Action_Duration",
    3: "Action_Duration",
    4: "Post_Action_Duration",
}
TALKING_DURATIONS = dict(enumerate([
    "Total_Educator-Speech-Duration",
    "Pre-Action_Educator-Speech_Duration",
    "Action_Educator-Speech_Duration",
    "Post-Action_Educator-Speech_Duration",
], start=1))
PROPORTIONS = dict(enumerate([
    "Total_Educator-Speech_Proportion",
    "Pre-Action_Educator-Speech_Proportion",
    "Action_Educator-Speech_Proportion",
    "Post-Action_Educator-Speech_Proportion",
], start=1))
COUNT_COLUMNS = [
    "Position_Front", "Position_Side", "Position_Behind",
    "PhysContact_with_Holding", "PhysContact_without_Holding",
]
DURATION_COLUMNS = list(PHASE_DURATIONS.values()) + list(TALKING_DURATIONS.values())


class TestConsolidatedCSV(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            cls.fields = reader.fieldnames or []
            cls.rows = list(reader)

    def number(self, row, column):
        cell = row[column]
        try:
            value = Decimal(cell)
        except InvalidOperation:
            self.fail(f"ID {row['ID']}: {column} is not numeric: {cell!r}")
        self.assertTrue(value.is_finite(), f"ID {row['ID']}: {column}={cell!r}")
        return value

    def test_exactly_87_rows_including_header(self):
        self.assertEqual(len(self.rows) + 1, 87)

    def test_schema_and_well_formed_rows(self):
        expected = [
            "ID", "Filename", "Situation_Type", "Cluster",
            *DURATION_COLUMNS, *PROPORTIONS.values(), *COUNT_COLUMNS,
        ]
        self.assertEqual(self.fields, expected)
        self.assertEqual(len(self.fields), len(expected))
        for row in self.rows:
            self.assertNotIn(None, row, f"Extra CSV cells: {row}")
            self.assertNotIn(None, row.values(), f"Missing CSV cells: {row}")
            for column in ("ID", "Filename", "Situation_Type"):
                self.assertTrue(row[column].strip(), f"Empty {column}: {row}")

    def test_all_numbers_are_reasonable(self):
        for row in self.rows:
            with self.subTest(id=row["ID"]):
                self.assertIn(self.number(row, "Cluster"), (Decimal(1), Decimal(2)))
                self.assertIn(row["Situation_Type"], ("Nose Blowing", "Face Cleaning"))
                for column in DURATION_COLUMNS:
                    value = self.number(row, column)
                    self.assertGreaterEqual(value, 0, column)
                    self.assertLessEqual(value, 3600, column)
                for column in COUNT_COLUMNS:
                    value = self.number(row, column)
                    self.assertEqual(value, value.to_integral_value(), column)
                    self.assertGreaterEqual(value, 0, column)
                    self.assertLessEqual(value, 1000, column)

    def test_proportions_are_between_zero_and_one_and_match_durations(self):
        for row in self.rows:
            for phase, column in PROPORTIONS.items():
                with self.subTest(id=row["ID"], column=column):
                    window = self.number(row, PHASE_DURATIONS[phase])
                    if window == 0:
                        self.assertEqual(row[column], "", "Zero duration requires a blank ratio")
                        continue
                    value = self.number(row, column)
                    self.assertGreaterEqual(value, 0)
                    self.assertLessEqual(value, 1)
                    expected = self.number(row, TALKING_DURATIONS[phase]) / window
                    self.assertLessEqual(abs(value - expected), Decimal("1e-12"))

    def test_code_durations_do_not_exceed_containing_durations(self):
        pairs = [(column, "Total_Duration")
                 for column in PHASE_DURATIONS.values()
                 if column != "Total_Duration"]
        pairs.extend((TALKING_DURATIONS[phase], parent)
                     for phase, parent in PHASE_DURATIONS.items())
        pairs.extend((TALKING_DURATIONS[phase], TALKING_DURATIONS[1])
                     for phase in (2, 3, 4))
        for row in self.rows:
            for child, parent in pairs:
                with self.subTest(id=row["ID"], child=child, parent=parent):
                    self.assertLessEqual(
                        self.number(row, child), self.number(row, parent),
                        f"{child} exceeds its containing interval {parent}",
                    )


if __name__ == "__main__":
    unittest.main()
