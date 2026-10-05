import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path

from scripts.enclosure.acoustic_model import DriverParameters
from scripts.enclosure.calculate_box import _driver_parameters


class DesignInputTests(unittest.TestCase):
    def test_composite_ts_source(self):
        driver = _driver_parameters({
            "source": "measured_ts",
            "name": "measured example",
            "fs_hz": 73,
            "qes": 0.386,
            "qms": 5.41,
            "re_ohm": 3.2,
            "vas_m3": 0.00143,
            "sd_m2": 0.00322,
            "le_h": 0.000169,
            "xmax_m": 0.0065,
        })
        self.assertAlmostEqual(driver.fs, 73, places=6)
        self.assertAlmostEqual(driver.qts, 0.36, places=2)
        self.assertEqual(driver.name, "measured example")

    def test_component_source_remains_supported(self):
        driver = _driver_parameters({
            "source": "components",
            "re_ohm": 3.2,
            "le_h": 0.000169,
            "bl_tm": 4.3,
            "mms_kg": 0.00486,
            "cms_m_n": 0.00097,
            "rms_ns_m": 0.411,
            "sd_m2": 0.00322,
        })
        self.assertAlmostEqual(driver.fs, 73.3, places=1)

    def test_fitted_json_source(self):
        driver = DriverParameters(3.2, 0.0002, 4.3, 0.005, 0.001, 0.4, 0.003, name="fit")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fit.json"
            path.write_text(json.dumps({"driver": asdict(driver)}), encoding="utf-8")
            loaded = _driver_parameters({"source": "fitted_json", "fit_json": str(path)})
        self.assertEqual(loaded, driver)

    def test_series_parallel_wiring_changes_model_equivalent(self):
        driver = _driver_parameters({
            "source": "components", "re_ohm": 4, "le_h": 0.0003,
            "bl_tm": 5, "mms_kg": 0.01, "cms_m_n": 0.001,
            "rms_ns_m": 1, "sd_m2": 0.005, "xmax_m": 0.004,
            "wiring": {"series": 1, "parallel": 2},
        })
        self.assertAlmostEqual(driver.re, 2)
        self.assertAlmostEqual(driver.sd, 0.01)
        self.assertAlmostEqual(driver.mms, 0.02)
        self.assertAlmostEqual(driver.fs, 1 / (2 * 3.141592653589793 * (0.02 * 0.0005)**0.5))


if __name__ == "__main__":
    unittest.main()