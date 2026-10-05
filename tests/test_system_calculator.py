import math
import unittest

from scripts.measurement.response_data import ComplexCurve, MeasuredDriver
from scripts.system_design.system_calculator import (
    LadderElement,
    LadderNetwork,
    PassiveLadder,
    TwoWayCrossover,
    design_standard_ladder,
    ladder_transfer,
    optimize_two_way,
    score_system,
    simulate_multiway,
    simulate_two_way,
    weighted_angular_average,
    zobel_values,
)


class SystemCalculatorTests(unittest.TestCase):
    def setUp(self):
        frequencies = (100.0, 1000.0, 10000.0)
        impedance = ComplexCurve(frequencies, (8.0, 8.0, 8.0), (0.0, 0.0, 0.0), False)
        woofer_frd = ComplexCurve(frequencies, (85.0, 85.0, 85.0), (0.0, 0.0, 0.0), True)
        tweeter_frd = ComplexCurve(frequencies, (90.0, 90.0, 90.0), (0.0, 0.0, 0.0), True)
        self.woofer = MeasuredDriver(woofer_frd, impedance, "woofer")
        self.tweeter = MeasuredDriver(tweeter_frd, impedance, "tweeter")
        self.crossover = TwoWayCrossover(0.0006, 3.9e-6, 0.00015, 3.3, 3.9)

    def test_complex_sum_and_system_impedance(self):
        rows = simulate_two_way(
            self.woofer, self.tweeter, self.crossover, [100, 500, 1000, 5000, 10000]
        )
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(row["input_impedance_magnitude"] > 0 for row in rows))
        self.assertTrue(all(math.isfinite(row["group_delay"]) for row in rows))
        self.assertTrue(all(row["measurement_covered"] for row in rows))

    def test_candidate_search_respects_impedance_floor(self):
        grid = {
            "woofer_inductors": [0.0006],
            "tweeter_capacitors": [3.9e-6],
            "tweeter_inductors": [0.00015],
            "series_resistors": [3.3],
            "shunt_resistors": [3.9],
        }
        result = optimize_two_way(
            self.woofer, self.tweeter, grid, [100, 500, 1000, 5000, 10000],
            minimum_impedance=0.1,
        )
        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result[0][3]["minimum_impedance_ohm"], 0.1)

    def test_score_requires_reference_band_coverage(self):
        rows = simulate_two_way(
            self.woofer, self.tweeter, self.crossover, [100, 500, 1000, 5000, 10000]
        )
        with self.assertRaises(ValueError):
            score_system(rows, reference_band=(2000, 3000))

    def test_weighted_angular_average_uses_linear_power(self):
        rows_0 = [{"frequency": 1000, "response": 1 + 0j, "spl_db": 0.0}]
        rows_30 = [{"frequency": 1000, "response": 0.5 + 0j, "spl_db": -6.0206}]
        average = weighted_angular_average({0: rows_0, 30: rows_30}, {0: 1, 30: 1})[0]
        self.assertAlmostEqual(average["weighted_spatial_level_db"], 10 * math.log10(0.625))
        self.assertGreater(average["directivity_index_db"], 0)

    def test_lr2_component_prototype_matches_normalized_values(self):
        ladder = design_standard_ladder("lowpass", 2, "Linkwitz-Riley", 2500, 8)
        self.assertEqual([element.kind for element in ladder.elements], ["L", "C"])
        self.assertAlmostEqual(ladder.elements[0].value, 0.3183 * 8 / 2500)
        self.assertAlmostEqual(ladder.elements[1].value, 0.0796 / (8 * 2500))

    def test_three_way_complex_summation(self):
        lowpass = design_standard_ladder("lowpass", 2, "butterworth", 700, 8)
        highpass_mid = design_standard_ladder("highpass", 2, "butterworth", 700, 8)
        lowpass_mid = design_standard_ladder("lowpass", 2, "butterworth", 3000, 8)
        highpass_tweeter = design_standard_ladder("highpass", 2, "linkwitz_riley", 3000, 8)
        mid_ladder = PassiveLadder(
            "lowpass", highpass_mid.elements + lowpass_mid.elements
        )
        branches = [
            {"name": "woofer", "driver": self.woofer, "ladder": lowpass},
            {"name": "midrange", "driver": self.woofer, "ladder": mid_ladder},
            {"name": "tweeter", "driver": self.tweeter, "ladder": highpass_tweeter},
        ]
        rows = simulate_multiway(branches, [100, 500, 1000, 5000, 10000])
        self.assertEqual(len(rows), 5)
        self.assertEqual(set(rows[2]["branch_responses"]), {"woofer", "midrange", "tweeter"})
        self.assertGreater(rows[2]["input_impedance_magnitude"], 0)
        self.assertTrue(all(math.isfinite(row["group_delay"]) for row in rows))

    def test_single_full_range_branch_uses_identity_ladder(self):
        ladder = PassiveLadder("lowpass", ())
        rows = simulate_multiway(
            [{"name": "fullrange", "driver": self.woofer, "ladder": ladder}],
            [100, 500, 1000, 5000, 10000],
        )
        self.assertEqual(len(rows), 5)
        self.assertAlmostEqual(abs(rows[2]["branch_responses"]["fullrange"]),
                               abs(self.woofer.response(1000)))

    def test_series_rc_zobel_and_composite_notch_network(self):
        values = zobel_values(6.4, 0.0004)
        self.assertAlmostEqual(values["resistance"], 8.0)
        self.assertAlmostEqual(values["capacitance"], 6.25e-6)
        notch = LadderNetwork("shunt", "series", resistance=8,
                              inductance=0.001, capacitance=10e-6)
        ladder = PassiveLadder("lowpass", (
            LadderElement("L", "series", 0.0005), notch,
        ))
        notch_frequency = 1 / (2 * math.pi * math.sqrt(notch.inductance * notch.capacitance))
        transfer, input_z = ladder_transfer(notch_frequency, 8 + 0j, ladder)
        self.assertLess(abs(transfer), 1)
        self.assertGreater(abs(input_z), 0)


if __name__ == "__main__":
    unittest.main()