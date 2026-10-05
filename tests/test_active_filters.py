import math
import unittest

from scripts.system_design.active_filters import (
    ActiveFilterChain,
    LinkwitzTransform,
    active_pass_filter,
    allpass,
    high_shelf,
    highpass,
    low_shelf,
    lowpass,
    peaking_eq,
)


class ActiveFilterTests(unittest.TestCase):
    def test_butterworth_low_and_highpass_cutoff(self):
        sample_rate, cutoff = 48000, 2000
        low = lowpass(cutoff, sample_rate).response(cutoff, sample_rate)
        high = highpass(cutoff, sample_rate).response(cutoff, sample_rate)
        self.assertAlmostEqual(abs(low), 1 / math.sqrt(2), places=6)
        self.assertAlmostEqual(abs(high), 1 / math.sqrt(2), places=6)

    def test_peaking_and_shelves_have_expected_gain(self):
        sample_rate, center = 48000, 1000
        peak = peaking_eq(center, sample_rate, 1, 6).response(center, sample_rate)
        low = low_shelf(100, sample_rate, 6).response(10, sample_rate)
        high = high_shelf(5000, sample_rate, -6).response(20000, sample_rate)
        self.assertAlmostEqual(20 * math.log10(abs(peak)), 6, places=6)
        self.assertAlmostEqual(20 * math.log10(abs(low)), 6, delta=0.1)
        self.assertAlmostEqual(20 * math.log10(abs(high)), -6, delta=0.1)

    def test_allpass_and_delay_chain(self):
        sample_rate, frequency = 48000, 3000
        filter_ = allpass(2000, sample_rate, 0.707)
        self.assertAlmostEqual(abs(filter_.response(frequency, sample_rate)), 1, places=6)
        chain = ActiveFilterChain((filter_,), delay_seconds=0.0005, sample_rate=sample_rate)
        self.assertAlmostEqual(abs(chain.response(frequency)), 1, places=6)

    def test_higher_order_linkwitz_riley_and_bessel_filters(self):
        sample_rate, cutoff = 48000, 2000
        lr4 = active_pass_filter("lowpass", 4, "linkwitz_riley", cutoff, sample_rate)
        response = math.prod((section.response(cutoff, sample_rate) for section in lr4), start=1 + 0j)
        self.assertAlmostEqual(abs(response), 0.5, places=5)
        bessel = active_pass_filter("highpass", 4, "bessel", cutoff, sample_rate)
        response = math.prod((section.response(cutoff, sample_rate) for section in bessel), start=1 + 0j)
        self.assertAlmostEqual(abs(response), 1 / math.sqrt(2), places=4)

    def test_linkwitz_transform_identity_and_linear_phase_option(self):
        transform = LinkwitzTransform(50, 0.7, 50, 0.7)
        self.assertAlmostEqual(abs(transform.response(100)), 1, places=12)
        linear = LinkwitzTransform(50, 0.7, 30, 0.707, linear_phase=True)
        self.assertEqual(linear.response(100).imag, 0)


if __name__ == "__main__":
    unittest.main()