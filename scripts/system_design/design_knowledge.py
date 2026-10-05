"""Reusable loudspeaker design checks distilled from supplied reference material."""

import itertools
import math


AIR_DENSITY = 1.18
SPEED_OF_SOUND = 343.0


def electrical_biological_product(fs, qes):
    if fs <= 0 or qes <= 0:
        raise ValueError("Fs and Qes must be positive.")
    return fs / qes


def ebp_screen(fs, qes):
    ebp = electrical_biological_product(fs, qes)
    if ebp <= 50:
        suggested = "sealed"
    elif ebp >= 100:
        suggested = "bass_reflex"
    else:
        suggested = "compare_both"
    return {"ebp": ebp, "starting_topology": suggested, "is_rule_of_thumb": True}


def corrected_q_values(re, qes, qms, series_resistance=0.0):
    if min(re, qes, qms) <= 0 or series_resistance < 0:
        raise ValueError("Re/Q values must be positive and added series resistance nonnegative.")
    corrected_qes = qes * (re + series_resistance) / re
    corrected_qts = corrected_qes * qms / (corrected_qes + qms)
    return {"qes": corrected_qes, "qms": qms, "qts": corrected_qts}


def half_power_ts(re, z_peak, f1, f2):
    """Estimate Fs/Qes/Qms/Qts from impedance peak and half-power frequencies."""
    if min(re, z_peak, f1, f2) <= 0 or z_peak <= re or f1 >= f2:
        raise ValueError("Require Zpeak > Re > 0 and 0 < f1 < f2.")
    ratio = z_peak / re
    fs = math.sqrt(f1 * f2)
    qms = fs * math.sqrt(ratio) / (f2 - f1)
    qes = qms / (ratio - 1)
    qts = qms * qes / (qms + qes)
    return {"fs": fs, "qms": qms, "qes": qes, "qts": qts}


def added_mass_mms(fs, shifted_fs, added_mass):
    if min(fs, shifted_fs, added_mass) <= 0 or shifted_fs >= fs:
        raise ValueError("Added mass must lower resonance; all values must be positive.")
    return added_mass / ((fs / shifted_fs)**2 - 1)


def delta_compliance_mms(fs, box_fs, box_volume, sd,
                         density=AIR_DENSITY, speed=SPEED_OF_SOUND):
    if min(fs, box_fs, box_volume, sd, density, speed) <= 0 or box_fs <= fs:
        raise ValueError("The sealed test box must raise resonance above free-air Fs.")
    box_compliance = box_volume / (density * speed**2 * sd**2)
    mms = 1 / (4 * math.pi**2 * box_compliance * (box_fs**2 - fs**2))
    return {"box_compliance": box_compliance, "mms": mms}


def vas_from_closed_box(box_volume, fs, box_fs):
    if min(box_volume, fs, box_fs) <= 0 or box_fs <= fs:
        raise ValueError("Closed-box resonance must exceed positive free-air Fs.")
    return box_volume * ((box_fs / fs)**2 - 1)


def vas_from_cms(cms, sd, density=AIR_DENSITY, speed=SPEED_OF_SOUND):
    if min(cms, sd, density, speed) <= 0:
        raise ValueError("Cms, Sd, density, and sound speed must be positive.")
    return density * speed**2 * cms * sd**2


def bl_from_force_mass(mass_kg, current_a, gravity=9.80665):
    if mass_kg <= 0 or current_a <= 0 or gravity <= 0:
        raise ValueError("Mass, current, and gravity must be positive.")
    return gravity * mass_kg / current_a


def le_from_impedance(re, impedance_magnitude, frequency):
    if min(re, impedance_magnitude, frequency) <= 0 or impedance_magnitude < re:
        raise ValueError("Require positive values and |Z| >= Re.")
    return math.sqrt(impedance_magnitude**2 - re**2) / (2 * math.pi * frequency)


def sensitivity_from_efficiency(efficiency, resistance=8.0):
    if not 0 < efficiency or resistance <= 0:
        raise ValueError("Efficiency and resistance must be positive.")
    spl_1w = 112.1 + 10 * math.log10(efficiency)
    spl_2_83v = spl_1w + 10 * math.log10(8 / resistance)
    return {"spl_1w_1m_db": spl_1w, "spl_2_83v_1m_db": spl_2_83v}


def required_power(target_spl_db, sensitivity_1w_1m_db, distance_m=1.0,
                   headroom_db=0.0):
    if distance_m <= 0 or headroom_db < 0:
        raise ValueError("Distance must be positive and headroom nonnegative.")
    required_spl = target_spl_db + headroom_db + 20 * math.log10(distance_m)
    power = 10 ** ((required_spl - sensitivity_1w_1m_db) / 10)
    return {"power_w": power, "power_gain_db": 10 * math.log10(power),
            "required_spl_at_1m_db": required_spl}


def spl_at_distance(spl_1m_db, distance_m):
    if distance_m <= 0:
        raise ValueError("Distance must be positive.")
    return spl_1m_db - 20 * math.log10(distance_m)


def voltage_for_power(power_w, resistance_ohm):
    if power_w < 0 or resistance_ohm <= 0:
        raise ValueError("Power must be nonnegative and resistance positive.")
    return math.sqrt(power_w * resistance_ohm)


def displacement_volume(sd, xmax):
    if min(sd, xmax) <= 0:
        raise ValueError("Sd and one-way Xmax must be positive SI values.")
    return sd * xmax


def room_modes(dimensions_m, max_index=4, speed=SPEED_OF_SOUND):
    """Return rectangular-room modal frequencies and axial/tangential/oblique types."""
    if len(dimensions_m) != 3 or min(dimensions_m) <= 0 or max_index < 1 or speed <= 0:
        raise ValueError("Provide three positive room dimensions and a positive mode limit.")
    modes = []
    for indices in itertools.product(range(max_index + 1), repeat=3):
        if indices == (0, 0, 0):
            continue
        frequency = speed / 2 * math.sqrt(sum(
            (index / dimension)**2 for index, dimension in zip(indices, dimensions_m)
        ))
        nonzero = sum(index > 0 for index in indices)
        kind = "axial" if nonzero == 1 else "tangential" if nonzero == 2 else "oblique"
        modes.append({"frequency": frequency, "indices": indices, "kind": kind})
    return sorted(modes, key=lambda mode: mode["frequency"])


def first_boundary_null(distance_m, speed=SPEED_OF_SOUND):
    """First ideal speaker-boundary cancellation for a single rigid boundary."""
    if distance_m <= 0 or speed <= 0:
        raise ValueError("Boundary distance and sound speed must be positive.")
    return speed / (4 * distance_m)


def acoustic_center_delay(distance_m, speed=SPEED_OF_SOUND):
    if distance_m < 0 or speed <= 0:
        raise ValueError("Distance must be nonnegative and sound speed positive.")
    return distance_m / speed


def axis_tilt_degrees(horizontal_offset_m, vertical_spacing_m):
    if vertical_spacing_m == 0:
        raise ValueError("Vertical driver spacing must be nonzero.")
    return math.degrees(math.atan2(horizontal_offset_m, vertical_spacing_m))


def piston_ka_3_frequency(diameter_m, speed=SPEED_OF_SOUND):
    if diameter_m <= 0 or speed <= 0:
        raise ValueError("Diameter and sound speed must be positive.")
    return 3.83 * speed / (math.pi * diameter_m)


def zobel_starting_values(re, le, resistor_ratio=1.25):
    if re <= 0 or le <= 0 or resistor_ratio <= 0:
        raise ValueError("Re, Le, and resistor ratio must be positive.")
    resistance = resistor_ratio * re
    return {"resistance_ohm": resistance, "capacitance_f": le / resistance**2}


def lpad_constant_impedance(load_ohm, attenuation_db):
    """Return series/shunt L-pad values for positive attenuation in dB."""
    if load_ohm <= 0 or attenuation_db <= 0:
        raise ValueError("Load and positive attenuation must be greater than zero.")
    voltage_ratio = 10 ** (-attenuation_db / 20)
    return {
        "series_ohm": load_ohm * (1 - voltage_ratio),
        "shunt_ohm": load_ohm * voltage_ratio / (1 - voltage_ratio),
    }