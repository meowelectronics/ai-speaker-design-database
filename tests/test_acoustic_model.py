import math
import unittest
from dataclasses import replace

from scripts.enclosure.acoustic_model import (
    DriverParameters,
    EnclosureDriver,
    EnclosureParameters,
    PassiveRadiatorParameters,
    maximum_voltage,
    port_geometry,
    simulate,
    simulate_point,
)
from scripts.enclosure.ts_alignments import (
    derive_driver_components,
    derive_thiele_small,
    driver_components_from_thiele_small,
)


class AcousticModelTests(unittest.TestCase):
    def setUp(self):
        self.driver = DriverParameters(
            re=6.4,
            le=0.0,
            bl=5.0,
            mms=0.01,
            cms=0.001,
            rms=1.0,
            sd=0.005,
            xmax=0.003,
        )
        self.frequencies = [20, 30, 50, 80, 120]

    def test_free_air_resonance_impedance(self):
        result = simulate_point(
            self.driver,
            EnclosureParameters("free", 0),
            self.driver.fs,
        )
        self.assertAlmostEqual(result["input_impedance"].real, 31.4, places=8)
        self.assertAlmostEqual(result["input_impedance"].imag, 0.0, places=8)

    def test_composite_ts_round_trip(self):
        original = derive_thiele_small(6.4, 0.01, 0.001, 1.0, 5.0, 0.005)
        components = derive_driver_components(
            original["fs"], original["qes"], original["qms"], 6.4, 5.0, 0.005
        )
        self.assertAlmostEqual(components["mms"], 0.01, places=10)
        self.assertAlmostEqual(components["cms"], 0.001, places=10)
        self.assertAlmostEqual(components["rms"], 1.0, places=10)
        self.assertGreater(components["efficiency"], 0)

    def test_standard_datasheet_ts_builds_model_components(self):
        values = driver_components_from_thiele_small(
            fs=73, qes=0.386, qms=5.41, re=3.2, vas=0.00143, sd=0.00322,
            le=0.000169, xmax=0.0065,
        )
        self.assertAlmostEqual(values["bl"], 4.3, delta=0.1)
        self.assertAlmostEqual(values["mms"], 0.00486, delta=0.0001)
        self.assertAlmostEqual(values["cms"], 0.00097, delta=0.00003)
        self.assertAlmostEqual(values["qts"], 0.3603, places=3)

    def test_sealed_response_and_group_delay(self):
        rows = simulate(self.driver, EnclosureParameters("sealed", 0.002), self.frequencies)
        self.assertTrue(all(math.isfinite(row["spl_db"]) for row in rows))
        self.assertTrue(all(row["group_delay"] >= 0 for row in rows))
        self.assertTrue(all(row["radiator_excursion"] is None for row in rows))

    def test_vented_model_returns_port_velocity(self):
        enclosure = EnclosureParameters(
            "vented", 0.002, tuning=50, port_area=0.001, port_count=2
        )
        rows = simulate(self.driver, enclosure, self.frequencies)
        self.assertTrue(all(row["port_velocity"] > 0 for row in rows))
        self.assertTrue(all(math.isfinite(row["input_impedance"].real) for row in rows))
        self.assertGreater(port_geometry(enclosure)["physical_length"], 0)

    def test_pr_model_returns_radiator_excursion_and_limit(self):
        radiator = PassiveRadiatorParameters(
            mms=0.0164, cms=0.00079, rms=0.5, sd=0.00866, xmax=0.009, added_mass=0.024
        )
        enclosure = EnclosureParameters("pr", 0.003, tuning=54, radiator=radiator)
        rows = simulate(self.driver, enclosure, self.frequencies)
        self.assertTrue(all(row["radiator_excursion"] > 0 for row in rows))
        tuned = simulate_point(self.driver, enclosure, 54)
        self.assertLess((tuned["radiator_velocity_phasor"] *
                 tuned["cone_velocity_phasor"].conjugate()).real, 0)
        limit, source = maximum_voltage(rows, self.driver, radiator, minimum_frequency=20)
        self.assertGreater(limit, 0)
        self.assertIn(source, {"cone excursion", "PR excursion"})

    def test_frequency_grid_must_increase(self):
        with self.assertRaises(ValueError):
            simulate(self.driver, EnclosureParameters("free", 0), [20, 40, 30])

    def test_model_driver_exposes_shared_complex_crossover_interface(self):
        driver = EnclosureDriver(self.driver, EnclosureParameters("sealed", 0.002))
        self.assertGreater(abs(driver.response(80)), 0)
        self.assertGreater(abs(driver.z(80)), 0)
        self.assertFalse(driver.measurement_covered(80))

    def test_thermal_input_power_limits_voltage(self):
        driver = replace(self.driver, xmax=None, power_handling_w=0.01)
        rows = simulate(driver, EnclosureParameters("sealed", 0.002), self.frequencies)
        voltage, source = maximum_voltage(rows, driver, minimum_frequency=20)
        self.assertLess(voltage, 2.83)
        self.assertEqual(source, "thermal input-power estimate")


if __name__ == "__main__":
    unittest.main()