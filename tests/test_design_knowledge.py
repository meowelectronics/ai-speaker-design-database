import math
import unittest

from scripts.system_design.design_knowledge import (
    acoustic_center_delay,
    added_mass_mms,
    axis_tilt_degrees,
    bl_from_force_mass,
    corrected_q_values,
    delta_compliance_mms,
    displacement_volume,
    ebp_screen,
    first_boundary_null,
    half_power_ts,
    le_from_impedance,
    lpad_constant_impedance,
    piston_ka_3_frequency,
    required_power,
    room_modes,
    sensitivity_from_efficiency,
    spl_at_distance,
    vas_from_closed_box,
    vas_from_cms,
    voltage_for_power,
    zobel_starting_values,
)


class DesignKnowledgeTests(unittest.TestCase):
    def test_ebp_and_series_loss_q_correction(self):
        self.assertEqual(ebp_screen(50, 1)["starting_topology"], "sealed")
        self.assertEqual(ebp_screen(100, 1)["starting_topology"], "bass_reflex")
        values = corrected_q_values(4, 0.4, 4, 1)
        self.assertAlmostEqual(values["qes"], 0.5)
        self.assertAlmostEqual(values["qts"], 4 / 9)

    def test_half_power_t_s_recovery(self):
        fs, re, zpeak, qms = 50, 6, 30, 4
        ratio = zpeak / re
        bandwidth = fs * math.sqrt(ratio) / qms
        x = math.asinh(bandwidth / (2 * fs))
        values = half_power_ts(re, zpeak, fs * math.exp(-x), fs * math.exp(x))
        self.assertAlmostEqual(values["fs"], fs, places=8)
        self.assertAlmostEqual(values["qms"], qms, places=8)

    def test_added_mass_and_delta_compliance_methods(self):
        fs, mms, mx = 50, 0.01, 0.005
        shifted_fs = fs / math.sqrt(1 + mx / mms)
        self.assertAlmostEqual(added_mass_mms(fs, shifted_fs, mx), mms)
        sd, volume = 0.005, 0.002
        cms = volume / (1.18 * 343**2 * sd**2)
        box_fs = fs * math.sqrt(1 + (1 / cms) / (1 / (1 / (2 * math.pi * fs)**2 / mms)))
        result = delta_compliance_mms(fs, box_fs, volume, sd)
        self.assertAlmostEqual(result["mms"], mms, delta=1e-10)

    def test_t_s_supporting_conversions(self):
        self.assertAlmostEqual(vas_from_closed_box(0.002, 50, 100), 0.006)
        self.assertAlmostEqual(vas_from_cms(0.001, 0.005), 0.00346, places=4)
        self.assertAlmostEqual(bl_from_force_mass(0.01, 0.1), 0.980665)
        self.assertAlmostEqual(le_from_impedance(4, math.sqrt(4**2 + (2*math.pi*1000*0.001)**2), 1000), 0.001)
        self.assertAlmostEqual(displacement_volume(0.005, 0.004), 20e-6)

    def test_output_budgeting(self):
        sensitivity = sensitivity_from_efficiency(0.01, 8)
        self.assertAlmostEqual(sensitivity["spl_1w_1m_db"], 92.1)
        self.assertAlmostEqual(spl_at_distance(90, 2), 83.9794000867)
        power = required_power(90, 90, distance_m=2)
        self.assertAlmostEqual(power["power_w"], 4)
        self.assertAlmostEqual(voltage_for_power(50, 8), 20)

    def test_room_sbir_spacing_and_directivity_checks(self):
        modes = room_modes((5, 4, 3), max_index=1)
        self.assertAlmostEqual(modes[0]["frequency"], 343 / 10)
        self.assertEqual(modes[0]["kind"], "axial")
        self.assertAlmostEqual(first_boundary_null(0.5), 171.5)
        self.assertAlmostEqual(acoustic_center_delay(0.0343), 0.0001)
        self.assertAlmostEqual(axis_tilt_degrees(0.01, 0.1), math.degrees(math.atan(0.1)))
        self.assertAlmostEqual(piston_ka_3_frequency(0.1), 3.83 * 343 / (math.pi * 0.1))

    def test_zobel_and_constant_impedance_lpad(self):
        zobel = zobel_starting_values(4, 0.001)
        self.assertAlmostEqual(zobel["resistance_ohm"], 5)
        self.assertAlmostEqual(zobel["capacitance_f"], 40e-6)
        pad = lpad_constant_impedance(8, 6)
        self.assertAlmostEqual(pad["series_ohm"] + 1 / (1 / pad["shunt_ohm"] + 1 / 8), 8)
        self.assertAlmostEqual((1 / (1 / pad["shunt_ohm"] + 1 / 8)) /
                               (pad["series_ohm"] + 1 / (1 / pad["shunt_ohm"] + 1 / 8)),
                               10 ** (-6 / 20))


if __name__ == "__main__":
    unittest.main()