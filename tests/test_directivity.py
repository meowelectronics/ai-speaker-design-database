import unittest

from scripts.system_design.directivity import piston_directivity


class DirectivityTests(unittest.TestCase):
    def test_circular_piston_is_omnidirectional_at_low_frequency(self):
        self.assertAlmostEqual(piston_directivity(100, diameter=0.1), 1.0, places=5)

    def test_off_axis_directivity_is_bounded_and_symmetric(self):
        on_axis = piston_directivity(4000, diameter=0.1)
        off_axis = piston_directivity(4000, horizontal_angle=45, diameter=0.1)
        mirrored = piston_directivity(4000, horizontal_angle=-45, diameter=0.1)
        self.assertGreaterEqual(off_axis, 0)
        self.assertLessEqual(off_axis, 1)
        self.assertAlmostEqual(off_axis, mirrored, places=12)
        self.assertLess(off_axis, on_axis)

    def test_rectangular_piston_axis_and_angle(self):
        self.assertAlmostEqual(piston_directivity(1000, width=0.15, height=0.2), 1)
        self.assertLess(piston_directivity(5000, horizontal_angle=45,
                                           width=0.15, height=0.2), 1)


if __name__ == "__main__":
    unittest.main()