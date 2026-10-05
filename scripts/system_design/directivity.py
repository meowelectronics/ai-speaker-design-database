"""Idealized circular/rectangular piston directivity for unmeasured angles."""

import math

import numpy as np
from scipy.special import j1


def piston_directivity(frequency, horizontal_angle=0.0, vertical_angle=0.0,
                       diameter=None, width=None, height=None, speed=343.0):
    """Return a real relative-amplitude directivity estimate for a rigid piston.

    Supply either a circular ``diameter`` or rectangular ``width`` and ``height``.
    Angles are in degrees. This ideal-piston estimate excludes cone breakup and baffle
    diffraction; measured off-axis FRD should take precedence.
    """
    if frequency < 0 or speed <= 0:
        raise ValueError("Frequency must be nonnegative and sound speed positive.")
    circular = diameter is not None
    rectangular = width is not None and height is not None
    if circular == rectangular:
        raise ValueError("Specify exactly one of circular diameter or rectangular width/height.")
    if circular and diameter <= 0 or rectangular and min(width, height) <= 0:
        raise ValueError("Piston dimensions must be positive.")

    horizontal = abs(horizontal_angle)
    vertical = abs(vertical_angle)
    angle = max(horizontal, vertical)
    direction_factor = math.sin(math.radians(angle)) if angle <= 90 else 1 + math.sin(math.radians(angle - 90))
    wave_number = math.pi * frequency / speed
    if circular:
        argument = wave_number * diameter * direction_factor
        return 1.0 if abs(argument) < 1e-12 else abs(2 * j1(argument) / argument)
    horizontal_argument = wave_number * width * math.sin(math.radians(horizontal))
    vertical_argument = wave_number * height * math.sin(math.radians(vertical))
    horizontal_sinc = np.sinc(horizontal_argument / math.pi)
    vertical_sinc = np.sinc(vertical_argument / math.pi)
    return abs(float(horizontal_sinc * vertical_sinc))