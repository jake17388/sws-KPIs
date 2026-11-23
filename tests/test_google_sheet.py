import unittest

import pandas as pd

import data
import google_sheet


HEADERS = [
    "Date", "Crew member", "Job number", "Job name", "Truck", "Crew Size",
    "Total Estimated Job Hours", "Est. Hours (Day)", "Total Clocked Hours (Day)",
    "Day %", "Work Completed on Schedule", "Fleetio AM", "Fleetio PM",
    "Late Departure (After 6:30)", "Job Delay", "Repair", "Remake", "Go Back", "Notes",
]


class GoogleSheetMappingTests(unittest.TestCase):
    def raw(self):
        return pd.DataFrame([
            ["2026-11-20", "Alex", "260001", "Lobby", "Bucket", 2, 16, 4, 8,
             "25%", "TRUE", "TRUE", "FALSE", "FALSE", "FALSE", "FALSE", "FALSE",
             "FALSE", "Started"],
            ["2026-11-20", "Alex", "260002", "Exterior", "Bucket", 2, 24, 6, 8,
             "75%", "FALSE", "TRUE", "TRUE", "FALSE", "TRUE", "FALSE", "FALSE",
             "TRUE", "Return tomorrow"],
        ], columns=HEADERS).assign(_sheet_row=[2, 3])

    def test_column_j_percentage_is_mapped_and_parsed(self):
        raw = self.raw()
        cleaned = data.clean(raw)
        header, letter = google_sheet.percentage_source(raw)
        self.assertEqual((header, letter), ("Day %", "J"))
        self.assertEqual(cleaned["day_pct"].tolist(), [25.0, 75.0])

    def test_edits_apply_to_metrics_before_sync(self):
        cleaned = data.clean(self.raw())
        keys = cleaned["key"].tolist()
        edited = data.apply_edits(
            cleaned, {keys[0]: 40, keys[1]: 60}, {},
            {(keys[0], "on_schedule"): False}, {keys[0]: "Updated note"})
        self.assertEqual(edited["day_pct"].tolist(), [40, 60])
        self.assertEqual(edited["actual_hours"].tolist(), [3.2, 4.8])
        self.assertFalse(bool(edited.iloc[0]["on_schedule"]))
        self.assertEqual(edited.iloc[0]["notes"], "Updated note")

    def test_batch_updates_target_source_rows_and_headers(self):
        cleaned = data.clean(self.raw())
        keys = cleaned["key"].tolist()
        updates = google_sheet.build_updates(
            cleaned, HEADERS, {keys[0]: 40, keys[1]: 60}, {},
            {(keys[0], "on_schedule"): True}, {keys[1]: "Done"})
        self.assertEqual(updates, [
            {"range": "J2", "values": [["40%"]]},
            {"range": "J3", "values": [["60%"]]},
            {"range": "K2", "values": [[True]]},
            {"range": "S3", "values": [["Done"]]},
        ])

    def test_sync_stops_if_sheet_rows_have_moved(self):
        loaded = data.clean(self.raw())
        moved_raw = self.raw().iloc[::-1].reset_index(drop=True)
        moved_raw["_sheet_row"] = [2, 3]
        current = data.clean(moved_raw)
        with self.assertRaisesRegex(ValueError, "rows changed"):
            google_sheet.validate_source_rows(loaded, current, {loaded.iloc[0]["key"]})


if __name__ == "__main__":
    unittest.main()
