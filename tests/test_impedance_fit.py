import cmath
import math
import unittest

from scripts.enclosure.acoustic_model import DriverParameters
from scripts.measurement.impedance_fit import fit_impedance
from scripts.measurement.response_data import ComplexCurve


class ImpedanceFitTests(unittest.TestCase):
    def test_fit_recovers_synthetic_complex_impedance(self):
        actual = DriverParameters(
            re=6.4,
            le=0.0004,
            bl=5.0,
            mms=0.01,
            cms=0.001,
            rms=1.0,
            sd=0.005,
            inductance_exponent=0.78,
        )
        frequencies = [10 * 1000 ** (index / 199) for index in range(200)]
        magnitudes, phases = [], []
        offset = 0.0
        previous = None
        for frequency in frequencies:
            omega = 2 * math.pi * frequency
            mechanical = actual.rms + 1j * omega * actual.mms + 1 / (1j * omega * actual.cms)
            impedance = actual.electrical_impedance(frequency) + actual.bl**2 / mechanical
            phase = cmath.phase(impedance)
            if previous is not None:
                if phase - previous > math.pi:
                    offset -= 2 * math.pi
                elif phase - previous < -math.pi:
                    offset += 2 * math.pi
            magnitudes.append(abs(impedance))
            phases.append(phase + offset)
            previous = phase
        curve = ComplexCurve(tuple(frequencies), tuple(magnitudes), tuple(phases), False)
        fit = fit_impedance(
            curve,
            {"re": 6.0, "le": 0.0005, "rms": 1.2, "mms": 0.011,
             "cms": 0.0009, "inductance_exponent": 0.9},
            bl=actual.bl,
            sd=actual.sd,
            max_samples=200,
        )
        self.assertTrue(fit["success"], fit["message"])
        self.assertAlmostEqual(fit["driver"].fs, actual.fs, delta=0.1)
        self.assertAlmostEqual(fit["driver"].le, actual.le, delta=0.00003)
        self.assertAlmostEqual(fit["driver"].inductance_exponent,
                               actual.inductance_exponent, delta=0.03)
        self.assertLess(fit["rms_relative_complex_error"], 0.01)


if __name__ == "__main__":
    unittest.main()