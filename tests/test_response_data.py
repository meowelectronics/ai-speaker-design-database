import math
import tempfile
import unittest
from pathlib import Path

from scripts.measurement.response_data import (
    ComplexCurve,
    MagnitudeCorrection,
    MeasuredDriver,
    measured_driver_files,
    measured_driver_at_angle,
)


class ResponseDataTests(unittest.TestCase):
    def test_phase_is_unwrapped_before_interpolation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "phase.frd"
            path.write_text("100 0 170\n1000 0 -170\n", encoding="utf-8")
            curve = ComplexCurve.from_file(path, magnitude_is_db=True)
        self.assertAlmostEqual(abs(math.degrees(math.atan2(curve.value( math.sqrt(100000)).imag,
                                                           curve.value(math.sqrt(100000)).real))), 180.0)

    def test_magnitude_only_impedance_marks_phase_unavailable(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "magnitude.zma"
            path.write_text("100 4\n1000 8\n", encoding="utf-8")
            curve = ComplexCurve.from_file(path, magnitude_is_db=False)
        self.assertFalse(curve.phase_available)
        self.assertEqual(curve.value(1000), 8 + 0j)

    def test_angle_interpolation_preserves_complex_phase(self):
        frd_0 = ComplexCurve((100, 1000), (0, 0), (0, 0), True)
        frd_30 = ComplexCurve((100, 1000), (0, 0), (math.pi, math.pi), True)
        zma = ComplexCurve((100, 1000), (8, 8), (0, 0), False)
        drivers = {
            0: MeasuredDriver(frd_0, zma, "test", 0),
            30: MeasuredDriver(frd_30, zma, "test", 30),
        }
        middle = measured_driver_at_angle(drivers, 15)
        self.assertAlmostEqual(abs(middle.response(500)), 1.0, places=8)
        self.assertAlmostEqual(abs(middle.response(500).imag), 1.0, places=8)
        self.assertIsNone(measured_driver_at_angle(drivers, 45))

    def test_microphone_calibration_adds_spl_correction(self):
        frd = ComplexCurve((100, 1000), (80, 80), (0, 0), True)
        calibration = MagnitudeCorrection((100, 1000), (1, -1))
        corrected = frd.corrected_magnitude(calibration)
        self.assertAlmostEqual(corrected.magnitudes[0], 81)
        self.assertAlmostEqual(corrected.magnitudes[1], 79)
        self.assertEqual(corrected.phases, frd.phases)

    def test_microphone_calibration_must_cover_frd_range(self):
        frd = ComplexCurve((50, 1000), (80, 80), (0, 0), True)
        calibration = MagnitudeCorrection((100, 1000), (0, 0))
        with self.assertRaises(ValueError):
            frd.corrected_magnitude(calibration)

    def test_umik_calibration_header_and_data_parse(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "umik.txt"
            path.write_text(
                '"Sens Factor =-0.319dB, SERNO: 7149303"\n'
                '"Auto-generated 90-degree calibration file"\n'
                "10.054\t-4.4771\n20.102\t0.5190\n",
                encoding="utf-8",
            )
            correction = MagnitudeCorrection.from_file(path)
        self.assertEqual(correction.frequency_range, (10.054, 20.102))
        self.assertAlmostEqual(correction.value(10.054), -4.4771)

    def test_explicit_rew_export_paths_load_by_angle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            frd = root / "REW export.txt"
            zma = root / "REW impedance.txt"
            frd.write_text("100 80 0\n1000 80 0\n", encoding="utf-8")
            zma.write_text("100 4 10\n1000 8 20\n", encoding="utf-8")
            drivers = measured_driver_files({0: frd}, zma)
        self.assertEqual(set(drivers), {0})
        self.assertAlmostEqual(abs(drivers[0].response(500)), 10**4)
        self.assertGreater(abs(drivers[0].z(500)), 0)


if __name__ == "__main__":
    unittest.main()