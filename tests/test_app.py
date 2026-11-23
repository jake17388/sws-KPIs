import os
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class DashboardTests(unittest.TestCase):
    def test_google_sheet_render_and_slider_rebalance(self):
        fixture = Path(__file__).parent / "fixtures" / "install_log.csv"
        os.environ["INSTALL_LOG_CSV_PATH"] = str(fixture)
        try:
            app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"),
                                    default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(len(app.radio), 0)
            self.assertIn("Install Log · percentages: Day Allocation % (column J)",
                          [caption.value for caption in app.caption])
            splits = [slider for slider in app.slider if slider.label == "% of day"]
            splits[0].set_value(40)
            app.run()
            values = [slider.value for slider in app.slider if slider.label == "% of day"]
            self.assertEqual(values, [40.0, 60.0])
            self.assertAlmostEqual(sum(values), 100.0)
            save = [button.label for button in app.button if button.label.startswith("Save ")]
            self.assertEqual(save, ["Save 2 changes to Google Sheet"])
            self.assertFalse(app.exception)
        finally:
            os.environ.pop("INSTALL_LOG_CSV_PATH", None)


if __name__ == "__main__":
    unittest.main()
