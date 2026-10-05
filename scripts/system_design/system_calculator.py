"""Measured-data two-way crossover simulation and component screening."""

from dataclasses import dataclass
import cmath
import itertools
import math


@dataclass(frozen=True)
class TwoWayCrossover:
    woofer_inductor: float
    tweeter_capacitor: float
    tweeter_inductor: float
    tweeter_series_resistor: float = 0.0
    tweeter_shunt_resistor: float | None = None
    woofer_zobel_resistor: float | None = None
    woofer_zobel_capacitor: float | None = None
    woofer_inductor_dcr: float = 0.0
    tweeter_inductor_dcr: float = 0.0

    def __post_init__(self):
        if min(self.woofer_inductor, self.tweeter_capacitor, self.tweeter_inductor) <= 0:
            raise ValueError("Crossover L and C values must be positive SI units.")
        if self.tweeter_series_resistor < 0 or (
            self.tweeter_shunt_resistor is not None and self.tweeter_shunt_resistor <= 0
        ) or min(self.woofer_inductor_dcr, self.tweeter_inductor_dcr) < 0:
            raise ValueError("Crossover resistances must be nonnegative and shunt R positive.")
        if (self.woofer_zobel_resistor is None) != (self.woofer_zobel_capacitor is None):
            raise ValueError("Zobel resistance and capacitance must be specified together.")
        if self.woofer_zobel_resistor is not None and min(
            self.woofer_zobel_resistor, self.woofer_zobel_capacitor
        ) <= 0:
            raise ValueError("Zobel R and C values must be positive.")


@dataclass(frozen=True)
class LadderElement:
    kind: str
    connection: str
    value: float
    series_resistance: float = 0.0

    def __post_init__(self):
        if self.kind not in {"L", "C", "R"} or self.connection not in {"series", "shunt"}:
            raise ValueError("Ladder elements must be L/C/R in series or shunt connection.")
        if self.value <= 0 or self.series_resistance < 0:
            raise ValueError("Element values must be positive and ESR/DCR nonnegative.")


@dataclass(frozen=True)
class LadderNetwork:
    connection: str
    topology: str
    resistance: float = 0.0
    inductance: float = 0.0
    capacitance: float = 0.0

    def __post_init__(self):
        if self.connection not in {"series", "shunt"} or self.topology not in {"series", "parallel"}:
            raise ValueError("RLC network needs series/shunt connection and series/parallel topology.")
        if min(self.resistance, self.inductance, self.capacitance) < 0:
            raise ValueError("RLC values cannot be negative.")
        if self.resistance == self.inductance == self.capacitance == 0:
            raise ValueError("RLC network must contain at least one component.")


@dataclass(frozen=True)
class PassiveLadder:
    direction: str
    elements: tuple

    def __post_init__(self):
        if self.direction not in {"lowpass", "highpass"}:
            raise ValueError("Ladder direction must be lowpass or highpass.")
        if any(not isinstance(element, (LadderElement, LadderNetwork)) for element in self.elements):
            raise TypeError("Ladder elements must be component or composite RLC instances.")


_PROTOTYPES = {
    ("lowpass", 1, "butterworth"): (0, 0, 0.1590, 0),
    ("lowpass", 2, "butterworth"): (0.1125, 0, 0.2251, 0),
    ("lowpass", 2, "bessel"): (0.0912, 0, 0.2756, 0),
    ("lowpass", 2, "linkwitz_riley"): (0.0796, 0, 0.3183, 0),
    ("lowpass", 2, "chebyshev"): (0.1592, 0, 0.1592, 0),
    ("lowpass", 3, "butterworth"): (0.2122, 0, 0.2387, 0.0796),
    ("lowpass", 4, "butterworth"): (0.2509, 0.0609, 0.2437, 0.1723),
    ("lowpass", 4, "bessel"): (0.2336, 0.0504, 0.3583, 0.1463),
    ("lowpass", 4, "linkwitz_riley"): (0.2533, 0.0563, 0.3000, 0.1500),
    ("lowpass", 4, "legendre"): (0.2365, 0.0910, 0.2294, 0.2034),
    ("lowpass", 4, "gaussian"): (0.2235, 0.0768, 0.3253, 0.1674),
    ("lowpass", 4, "linear_phase"): (0.2255, 0.0632, 0.3285, 0.1578),
    ("highpass", 1, "butterworth"): (0.1590, 0, 0, 0),
    ("highpass", 2, "butterworth"): (0.1125, 0, 0.2251, 0),
    ("highpass", 2, "bessel"): (0.0912, 0, 0.2756, 0),
    ("highpass", 2, "linkwitz_riley"): (0.0796, 0, 0.3183, 0),
    ("highpass", 2, "chebyshev"): (0.1592, 0, 0.1592, 0),
    ("highpass", 3, "butterworth"): (0.1061, 0.3183, 0.1194, 0),
    ("highpass", 4, "butterworth"): (0.1040, 0.1470, 0.1009, 0.4159),
    ("highpass", 4, "bessel"): (0.0702, 0.0719, 0.0862, 0.4983),
    ("highpass", 4, "linkwitz_riley"): (0.0844, 0.1688, 0.1000, 0.4501),
    ("highpass", 4, "legendre"): (0.1104, 0.1246, 0.1073, 0.2783),
    ("highpass", 4, "gaussian"): (0.0767, 0.1491, 0.1116, 0.3251),
    ("highpass", 4, "linear_phase"): (0.0741, 0.1524, 0.1079, 0.3853),
}


def design_standard_ladder(direction, order, alignment, cutoff, reference_impedance,
                           inductor_dcr=0.0, capacitor_esr=0.0):
    """Design a common normalized passive low/high-pass ladder (SI units)."""
    family = alignment.lower().replace("-", "_").replace(" ", "_")
    key = (direction, order, family)
    if key not in _PROTOTYPES:
        raise ValueError(f"Unsupported passive ladder prototype: {direction}, {order}, {alignment}.")
    if min(cutoff, reference_impedance) <= 0 or min(inductor_dcr, capacitor_esr) < 0:
        raise ValueError("Cutoff/load must be positive and component loss values nonnegative.")
    c1, c2, l1, l2 = _PROTOTYPES[key]
    capacitors = [coefficient / (reference_impedance * cutoff)
                  for coefficient in (c1, c2)]
    inductors = [coefficient * reference_impedance / cutoff
                 for coefficient in (l1, l2)]
    if direction == "lowpass":
        sequence = (("L", "series", inductors[0]), ("C", "shunt", capacitors[0]),
                    ("L", "series", inductors[1]), ("C", "shunt", capacitors[1]))
    else:
        sequence = (("C", "series", capacitors[0]), ("L", "shunt", inductors[0]),
                    ("C", "series", capacitors[1]), ("L", "shunt", inductors[1]))
    elements = tuple(
        LadderElement(kind, connection, value,
                      inductor_dcr if kind == "L" else capacitor_esr if kind == "C" else 0.0)
        for kind, connection, value in sequence if value > 0
    )
    return PassiveLadder(direction, elements)


def _parallel(first, second):
    return first * second / (first + second)


def _measurement_covered(driver, frequency):
    if hasattr(driver, "measurement_covered"):
        return driver.measurement_covered(frequency)
    return all(curve.frequency_range[0] <= frequency <= curve.frequency_range[1]
               for curve in (driver.frd, driver.impedance))


def _element_impedance(element, frequency):
    omega = 2 * math.pi * frequency
    if element.kind == "R":
        return complex(element.value)
    if element.kind == "L":
        return element.series_resistance + 1j * omega * element.value
    return element.series_resistance + 1 / (1j * omega * element.value)


def ladder_transfer(frequency, load_impedance, ladder):
    """Return ladder voltage transfer and input impedance using ABCD cascades."""
    a, b, c, d = 1 + 0j, 0j, 0j, 1 + 0j
    for element in ladder.elements:
        if isinstance(element, LadderNetwork):
            impedances = []
            if element.resistance:
                impedances.append(complex(element.resistance))
            if element.inductance:
                impedances.append(1j * 2 * math.pi * frequency * element.inductance)
            if element.capacitance:
                impedances.append(1 / (1j * 2 * math.pi * frequency * element.capacitance))
            if element.topology == "series":
                impedance = sum(impedances)
            else:
                impedance = 1 / sum(1 / item for item in impedances)
        else:
            impedance = _element_impedance(element, frequency)
        if element.connection == "series":
            a, b = a, a * impedance + b
            c, d = c, c * impedance + d
        else:
            admittance = 1 / impedance
            a, b = a + b * admittance, b
            c, d = c + d * admittance, d
    denominator = c * load_impedance + d
    input_impedance = (a * load_impedance + b) / denominator
    transfer = load_impedance / (a * load_impedance + b)
    return transfer, input_impedance


def zobel_values(re, le, resistor_ratio=1.25):
    """Return a first-pass series-RC Zobel connected across a driver."""
    if re <= 0 or le <= 0 or resistor_ratio <= 0:
        raise ValueError("Driver Re, Le, and Zobel resistor ratio must be positive.")
    resistance = resistor_ratio * re
    return {"resistance": resistance, "capacitance": le / resistance**2}


def simulate_multiway(branches, frequencies, input_voltage=2.83,
                      frd_reference_voltage=2.83):
    """Complex acoustic/electrical summation for arbitrary measured multiway branches.

    Each branch mapping contains ``name``, ``driver``, and ``ladder``; optional fields are
    ``polarity`` (+1/-1), ``offset_m``, and ``baffle`` (complex transfer callable).
    """
    frequencies = list(frequencies)
    if input_voltage < 0 or frd_reference_voltage <= 0:
        raise ValueError("Input voltage must be nonnegative and FRD reference positive.")
    if len(branches) < 1 or len(frequencies) < 2:
        raise ValueError("System simulation requires at least one branch and two frequencies.")
    if any(a >= b or a <= 0 for a, b in zip(frequencies, frequencies[1:])):
        raise ValueError("Frequencies must be positive and strictly increasing.")
    if any(branch.get("polarity", 1) not in {-1, 1} for branch in branches):
        raise ValueError("Branch polarity must be +1 or -1.")

    rows = []
    for frequency in frequencies:
        response_by_branch = {}
        branch_impedances = []
        coverage = True
        for branch in branches:
            driver, ladder = branch["driver"], branch["ladder"]
            transfer, impedance = ladder_transfer(frequency, driver.z(frequency), ladder)
            pressure = driver.response(frequency) * transfer * input_voltage / frd_reference_voltage
            active_filter = branch.get("active_filter")
            if active_filter:
                pressure *= active_filter.response(frequency)
            pressure *= branch.get("polarity", 1)
            pressure *= cmath.exp(-1j * 2 * math.pi * frequency * branch.get("offset_m", 0.0) / 343.0)
            baffle = branch.get("baffle")
            if baffle:
                pressure *= baffle(frequency)
            directivity = branch.get("directivity")
            if directivity:
                pressure *= directivity(frequency)
            response_by_branch[branch.get("name", driver.name)] = pressure
            branch_impedances.append(impedance)
            coverage = coverage and _measurement_covered(driver, frequency)
        total_admittance = sum(1 / impedance for impedance in branch_impedances)
        total_impedance = 1 / total_admittance
        response = sum(response_by_branch.values())
        rows.append({
            "frequency": frequency,
            "branch_responses": response_by_branch,
            "response": response,
            "spl_db": 20 * math.log10(max(abs(response), 1e-30)),
            "input_impedance": total_impedance,
            "input_impedance_magnitude": abs(total_impedance),
            "measurement_covered": coverage,
        })
    _group_delay(rows)
    return rows


def _woofer_branch(frequency, driver, crossover):
    omega = 2 * math.pi * frequency
    load = driver.z(frequency)
    if crossover.woofer_zobel_resistor is not None:
        zobel = crossover.woofer_zobel_resistor + 1 / (
            1j * omega * crossover.woofer_zobel_capacitor
        )
        load = _parallel(load, zobel)
    series = crossover.woofer_inductor_dcr + 1j * omega * crossover.woofer_inductor
    branch_impedance = load + series
    return load / branch_impedance, branch_impedance


def _tweeter_branch(frequency, driver, crossover):
    omega = 2 * math.pi * frequency
    load = driver.z(frequency)
    if crossover.tweeter_shunt_resistor is not None:
        load = _parallel(load, crossover.tweeter_shunt_resistor)
    pad_load = crossover.tweeter_series_resistor + load
    shunt_inductor = crossover.tweeter_inductor_dcr + 1j * omega * crossover.tweeter_inductor
    shunt_load = _parallel(shunt_inductor, pad_load)
    series_capacitor = 1 / (1j * omega * crossover.tweeter_capacitor)
    branch_impedance = series_capacitor + shunt_load
    voltage_gain = shunt_load / branch_impedance * load / pad_load
    return voltage_gain, branch_impedance


def _group_delay(rows):
    phases = []
    previous = None
    offset = 0.0
    for row in rows:
        phase = cmath.phase(row["response"])
        if previous is not None:
            delta = phase - previous
            if delta > math.pi:
                offset -= 2 * math.pi
            elif delta < -math.pi:
                offset += 2 * math.pi
        phases.append(phase + offset)
        previous = phase

    for index, row in enumerate(rows):
        left, right = max(0, index - 1), min(len(rows) - 1, index + 1)
        row["group_delay"] = -(phases[right] - phases[left]) / (
            2 * math.pi * (rows[right]["frequency"] - rows[left]["frequency"])
        )


def simulate_two_way(woofer, tweeter, crossover, frequencies, input_voltage=2.83,
                     frd_reference_voltage=2.83, tweeter_offset=0.0,
                     invert_tweeter=False, woofer_baffle=None, tweeter_baffle=None):
    """Simulate a 2-way network using complex measured FRD/ZMA driver data.

    Driver FRD magnitudes are assumed referenced to ``frd_reference_voltage``.
    Baffle functions, when supplied, must return complex pressure transfer functions.
    """
    if input_voltage < 0 or frd_reference_voltage <= 0:
        raise ValueError("Input voltage must be nonnegative and FRD reference voltage positive.")
    frequencies = list(frequencies)
    if len(frequencies) < 2 or any(f <= 0 for f in frequencies):
        raise ValueError("At least two positive frequencies are required.")
    if any(a >= b for a, b in zip(frequencies, frequencies[1:])):
        raise ValueError("Frequency grid must be strictly increasing.")

    voltage_scale = input_voltage / frd_reference_voltage
    rows = []
    for frequency in frequencies:
        hw, zw = _woofer_branch(frequency, woofer, crossover)
        ht, zt = _tweeter_branch(frequency, tweeter, crossover)
        bw = woofer_baffle(frequency) if woofer_baffle else 1.0
        bt = tweeter_baffle(frequency) if tweeter_baffle else 1.0
        vw = hw * woofer.response(frequency) * bw * voltage_scale
        vt = ht * tweeter.response(frequency) * bt * voltage_scale
        vt *= cmath.exp(-1j * 2 * math.pi * frequency * tweeter_offset / 343.0)
        if invert_tweeter:
            vt = -vt
        system_impedance = _parallel(zw, zt)
        response = vw + vt
        rows.append({
            "frequency": frequency,
            "woofer_response": vw,
            "tweeter_response": vt,
            "response": response,
            "spl_db": 20 * math.log10(max(abs(response), 1e-30)),
            "input_impedance": system_impedance,
            "input_impedance_magnitude": abs(system_impedance),
            "measurement_covered": all(
                _measurement_covered(driver, frequency)
                for driver in (woofer, tweeter)
            ),
        })
    _group_delay(rows)
    return rows


def score_system(rows, reference_band=(500, 3000), evaluate_band=(300, 16000)):
    """Return response smoothness and minimum impedance for an evaluated band."""
    selected = [row for row in rows if evaluate_band[0] <= row["frequency"] <= evaluate_band[1]]
    reference = [row["spl_db"] for row in selected
                 if reference_band[0] <= row["frequency"] <= reference_band[1]]
    if not selected or not reference:
        raise ValueError("Frequency grid must cover both evaluation and reference bands.")
    level = sum(reference) / len(reference)
    deviations = [row["spl_db"] - level for row in selected]
    return {
        "reference_db": level,
        "rms_deviation_db": math.sqrt(sum(value**2 for value in deviations) / len(deviations)),
        "peak_to_peak_db": max(deviations) - min(deviations),
        "minimum_impedance_ohm": min(row["input_impedance_magnitude"] for row in selected),
        "measurement_coverage_fraction": sum(row["measurement_covered"] for row in selected) / len(selected),
    }


def weighted_angular_average(rows_by_angle, weights):
    """Compute weighted spatial level and directivity from measured/modelled directions.

    ``weights`` should represent the angular integration weights (solid angle); an
    unweighted horizontal sweep is not a full-sphere sound-power estimate. The caller
    must provide a complete directional data set for full-sphere integration.
    """
    if not rows_by_angle or set(rows_by_angle) != set(weights):
        raise ValueError("Supply exactly one positive integration weight for every angle.")
    if any(weight <= 0 for weight in weights.values()):
        raise ValueError("Angular integration weights must be positive.")
    reference_angle = 0 if 0 in rows_by_angle else min(rows_by_angle)
    reference_rows = rows_by_angle[reference_angle]
    by_frequency = {angle: {row["frequency"]: row for row in rows}
                    for angle, rows in rows_by_angle.items()}
    total_weight = sum(weights[angle] for angle in rows_by_angle)
    result = []
    for reference in reference_rows:
        frequency = reference["frequency"]
        if any(frequency not in by_frequency[angle] for angle in rows_by_angle):
            raise ValueError("Angular response grids must have matching frequencies.")
        mean_power = sum(
            weights[angle] * abs(by_frequency[angle][frequency]["response"])**2
            for angle in rows_by_angle
        ) / total_weight
        sound_power_db = 10 * math.log10(max(mean_power, 1e-30))
        result.append({
            "frequency": frequency,
            "weighted_spatial_level_db": sound_power_db,
            "directivity_index_db": reference["spl_db"] - sound_power_db,
        })
    return result


def optimize_two_way(woofer, tweeter, grid, frequencies, minimum_impedance=3.2,
                     limit=20, **simulation_options):
    """Rank common 2-way component combinations subject to an impedance floor.

    Grid values use SI units and keys: ``woofer_inductors``, ``tweeter_capacitors``,
    ``tweeter_inductors``, ``series_resistors``, and ``shunt_resistors``. Optional
    ``zobel`` entries are ``(R, C)`` pairs. Results are estimates for measured inputs,
    not a substitute for power, thermal, or prototype checks.
    """
    keys = ("woofer_inductors", "tweeter_capacitors", "tweeter_inductors",
            "series_resistors", "shunt_resistors")
    if any(key not in grid or not grid[key] for key in keys):
        raise ValueError("Component grid is missing one or more required value lists.")
    zobels = grid.get("zobels", (None,))
    woofer_dcrs = grid.get("woofer_inductor_dcrs", (0.0,))
    tweeter_dcrs = grid.get("tweeter_inductor_dcrs", (0.0,))
    candidates = []
    for values in itertools.product(*(grid[key] for key in keys), woofer_dcrs,
                                    tweeter_dcrs, zobels):
        lw, ct, lt, rs, rp, woofer_dcr, tweeter_dcr, zobel = values
        zr, zc = zobel if zobel is not None else (None, None)
        crossover = TwoWayCrossover(
            lw, ct, lt, rs, rp, zr, zc,
            woofer_inductor_dcr=woofer_dcr,
            tweeter_inductor_dcr=tweeter_dcr,
        )
        rows = simulate_two_way(woofer, tweeter, crossover, frequencies, **simulation_options)
        score = score_system(rows)
        if score["minimum_impedance_ohm"] < minimum_impedance:
            continue
        candidates.append((score["rms_deviation_db"], score["peak_to_peak_db"],
                           crossover, score))
    candidates.sort(key=lambda item: (item[0], item[1]))
    return candidates[:limit]