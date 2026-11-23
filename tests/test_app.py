import os
from pathlib import Path
import unittest

from streamlit.testing.v1 import AppTest


class DashboardTests(unittest.TestCase):
    def test_google_sheet_render_and_slider_rebalance(self):
        fixture = Path(__file__).parents[1] / "data" / "sample_install_log.csv"
        os.environ["INSTALL_LOG_CSV_PATH"] = str(fixture)
        try:
            app = AppTest.from_file(str(Path(__file__).parents[1] / "app.py"),
                                    default_timeout=30).run()
            self.assertFalse(app.exception)
            self.assertEqual(app.radio[0].value, "Google Sheet (Install Log)")
            splits = [slider for slider in app.slider if slider.label == "% of day"]
            splits[0].set_value(40)
            app.run()
            values = [slider.value for slider in app.slider if slider.label == "% of day"]
            self.assertEqual(values[:4], [40, 20, 20, 20])
            self.assertEqual(sum(values[:4]), 100)
            save = [button.label for button in app.button if button.label.startswith("Save ")]
            self.assertEqual(save, ["Save 4 changes to Google Sheet"])
            self.assertFalse(app.exception)
        finally:
            os.environ.pop("INSTALL_LOG_CSV_PATH", None)


if __name__ == "__main__":
    unittest.main()
