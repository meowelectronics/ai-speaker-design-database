"""Complex electroacoustic models for driver and low-frequency enclosure design."""

from dataclasses import dataclass, replace
import cmath
import math


AIR_DENSITY = 1.18
SPEED_OF_SOUND = 343.0
REFERENCE_PRESSURE = 20e-6


@dataclass(frozen=True)
class DriverParameters:
    re: float
    le: float
    bl: float
    mms: float
    cms: float
    rms: float
    sd: float
    xmax: float | None = None
    name: str = "driver"
    inductance_exponent: float = 1.0
    inductance_reference_frequency: float = 1000.0
    power_handling_w: float | None = None

    def __post_init__(self):
        if min(self.re, self.bl, self.mms, self.cms, self.rms, self.sd) <= 0:
            raise ValueError("Driver Re, BL, Mms, Cms, Rms, and Sd must be positive SI values.")
        if (self.le < 0 or (self.xmax is not None and self.xmax <= 0)
            or not 0.5 <= self.inductance_exponent <= 1.0
            or self.inductance_reference_frequency <= 0
            or (self.power_handling_w is not None and self.power_handling_w <= 0)):
            raise ValueError("Le must be nonnegative and Xmax must be positive when specified.")

    @property
    def fs(self):
        return 1 / (2 * math.pi * math.sqrt(self.mms * self.cms))

    @property
    def qms(self):
        return 2 * math.pi * self.fs * self.mms / self.rms

    @property
    def qes(self):
        return 2 * math.pi * self.fs * self.mms * self.re / self.bl**2

    @property
    def qts(self):
        return self.qms * self.qes / (self.qms + self.qes)

    @property
    def vas(self):
        return AIR_DENSITY * SPEED_OF_SOUND**2 * self.cms * self.sd**2

    def electrical_impedance(self, frequency):
        omega = 2 * math.pi * frequency
        reference_omega = 2 * math.pi * self.inductance_reference_frequency
        inductive = self.le * (1j * omega)**self.inductance_exponent / (
            reference_omega**(self.inductance_exponent - 1)
        ) if self.le else 0j
        return self.re + inductive


def equivalent_driver_array(driver, series=1, parallel=1):
    """Return the electrical/mechanical equivalent for identical wired driver arrays."""
    if (not isinstance(series, int) or isinstance(series, bool) or series < 1
            or not isinstance(parallel, int) or isinstance(parallel, bool) or parallel < 1):
        raise ValueError("Series and parallel counts must be positive integers.")
    count = series * parallel
    power = driver.power_handling_w * count if driver.power_handling_w is not None else None
    return replace(
        driver,
        re=driver.re * series / parallel,
        le=driver.le * series / parallel,
        bl=driver.bl * series,
        mms=driver.mms * count,
        cms=driver.cms / count,
        rms=driver.rms * count,
        sd=driver.sd * count,
        power_handling_w=power,
        name=(driver.name if count == 1 else f"{series}s{parallel}p {driver.name}"),
    )


@dataclass(frozen=True)
class PassiveRadiatorParameters:
    mms: float
    cms: float
    rms: float
    sd: float
    xmax: float | None = None
    added_mass: float = 0.0

    def __post_init__(self):
        if min(self.mms, self.cms, self.rms, self.sd) <= 0 or self.added_mass < 0:
            raise ValueError("PR parameters must be positive SI values; added mass cannot be negative.")
        if self.xmax is not None and self.xmax <= 0:
            raise ValueError("PR Xmax must be positive when specified.")


@dataclass(frozen=True)
class EnclosureParameters:
    kind: str
    volume: float
    tuning: float | None = None
    ql: float = 15.0
    qa: float = 100.0
    qp: float = 20.0
    port_area: float | None = None
    port_count: int = 1
    port_end_correction: float = 0.0
    radiator: PassiveRadiatorParameters | None = None

    def __post_init__(self):
        if self.kind not in {"free", "sealed", "vented", "aperiodic", "pr"}:
            raise ValueError("kind must be free, sealed, vented, aperiodic, or pr.")
        if self.kind != "free" and self.volume <= 0:
            raise ValueError("Enclosure volume must be positive SI cubic metres.")
        if min(self.ql, self.qa, self.qp) <= 0:
            raise ValueError("Enclosure loss Q values must be positive.")
        if self.kind in {"vented", "aperiodic"}:
            if self.tuning is None or self.tuning <= 0 or self.port_area is None or self.port_area <= 0:
                raise ValueError("Vented models need positive tuning and total port area in SI units.")
            if self.port_count < 1 or self.port_end_correction < 0:
                raise ValueError("Port count must be positive and end correction nonnegative.")
        if self.kind == "pr" and self.radiator is None:
            raise ValueError("PR models need passive-radiator parameters.")
        if self.kind == "pr" and (self.tuning is None or self.tuning <= 0):
            raise ValueError("PR models need a positive target tuning frequency.")


def _parallel(first, second):
    if first is None:
        return second
    if second is None:
        return first
    return first * second / (first + second)


def _box_acoustic_impedance(frequency, enclosure, driver):
    if enclosure.kind == "free":
        return None, None, None

    omega = 2 * math.pi * frequency
    cab = enclosure.volume / (AIR_DENSITY * SPEED_OF_SOUND**2)
    reference_hz = enclosure.tuning or driver.fs * math.sqrt(1 + driver.vas/enclosure.volume)
    reference_omega = 2 * math.pi * reference_hz

    absorption_r = 1 / (reference_omega * enclosure.qa * cab) if math.isfinite(enclosure.qa) else 0.0
    leakage_r = enclosure.ql / (reference_omega * cab) if math.isfinite(enclosure.ql) else math.inf
    compliance_branch = complex(absorption_r, -1 / (omega * cab))
    loss_branch = complex(leakage_r) if math.isfinite(leakage_r) else None
    box_load = _parallel(compliance_branch, loss_branch)

    if enclosure.kind in {"vented", "aperiodic"}:
        tune_omega = 2 * math.pi * enclosure.tuning
        port_mass = 1 / (tune_omega**2 * cab)
        port_q = 0.5 if enclosure.kind == "aperiodic" else enclosure.qp
        port_resistance = 1 / (tune_omega * port_q * cab) if math.isfinite(port_q) else 0.0
        port_load = complex(port_resistance, omega * port_mass)
        return _parallel(box_load, port_load), port_load, cab

    if enclosure.kind == "pr":
        radiator = enclosure.radiator
        radiator_mechanical = complex(
            radiator.rms,
            omega * (radiator.mms + radiator.added_mass) - 1 / (omega * radiator.cms),
        )
        radiator_load = radiator_mechanical / radiator.sd**2
        return _parallel(box_load, radiator_load), radiator_load, cab

    return box_load, None, cab


def port_geometry(enclosure):
    """Return Helmholtz port dimensions; area is total area across all ports."""
    if enclosure.kind not in {"vented", "aperiodic"}:
        raise ValueError("Port geometry is available only for vented or aperiodic boxes.")
    tune_omega = 2 * math.pi * enclosure.tuning
    effective_length = SPEED_OF_SOUND**2 * enclosure.port_area / (
        tune_omega**2 * enclosure.volume
    )
    physical_length = effective_length - enclosure.port_end_correction
    if physical_length <= 0:
        raise ValueError("Port end correction must be smaller than effective length.")
    per_port_area = enclosure.port_area / enclosure.port_count
    return {
        "total_area": enclosure.port_area,
        "area_per_port": per_port_area,
        "diameter_per_port": math.sqrt(4 * per_port_area / math.pi),
        "effective_length": effective_length,
        "physical_length": physical_length,
        "first_pipe_resonance": SPEED_OF_SOUND / (2 * physical_length),
    }


def simulate_point(driver, enclosure, frequency, voltage=2.83, distance=1.0,
                   radiation_solid_angle=2 * math.pi):
    """Return complex input/acoustic response and displacement for one frequency.

    Driver and enclosure dimensions use SI units. Voltage is RMS; output SPL uses
    the half-space monopole convention by default and can be changed for a full sphere.
    """
    if frequency <= 0 or voltage < 0 or distance <= 0 or radiation_solid_angle <= 0:
        raise ValueError("Frequency, distance, and radiation solid angle must be positive; voltage nonnegative.")

    omega = 2 * math.pi * frequency
    jw = 1j * omega
    electrical = driver.electrical_impedance(frequency)
    mechanical = driver.rms + jw * driver.mms + 1 / (jw * driver.cms)
    enclosure_load, port_load, _ = _box_acoustic_impedance(frequency, enclosure, driver)

    if enclosure_load is not None:
        mechanical += driver.sd**2 * enclosure_load

    input_impedance = electrical + driver.bl**2 / mechanical
    cone_velocity = driver.bl * voltage / (electrical * mechanical + driver.bl**2)
    cone_flow = driver.sd * cone_velocity
    port_velocity = None
    geometry = None
    radiator_excursion = None
    radiator_velocity = None
    radiated_flow = cone_flow

    if enclosure.kind in {"vented", "aperiodic", "pr"}:
        branch_flow = -cone_flow * enclosure_load / port_load
        radiated_flow += branch_flow
        if enclosure.kind == "pr":
            radiator_velocity = branch_flow / enclosure.radiator.sd
            radiator_excursion = abs(radiator_velocity / jw)
        else:
            port_velocity = abs(branch_flow) / (enclosure.port_area or 1.0)
            geometry = port_geometry(enclosure)

    pressure = (jw * AIR_DENSITY * radiated_flow / (radiation_solid_angle * distance)
                * cmath.exp(-jw * distance / SPEED_OF_SOUND))
    spl = 20 * math.log10(max(abs(pressure), 1e-30) / REFERENCE_PRESSURE)
    return {
        "frequency": frequency,
        "input_impedance": input_impedance,
        "pressure": pressure,
        "response": pressure / REFERENCE_PRESSURE,
        "spl_db": spl,
        "cone_velocity_phasor": cone_velocity,
        "radiated_volume_velocity": radiated_flow,
        "cone_excursion": abs(cone_velocity / jw),
        "radiator_excursion": radiator_excursion,
        "radiator_velocity_phasor": radiator_velocity,
        "radiator_velocity": abs(radiator_velocity) if radiator_velocity is not None else None,
        "port_velocity": port_velocity,
        "port_geometry": geometry,
    }


class EnclosureDriver:
    """Driver adapter blending a T/S enclosure model with optional measured curves."""

    def __init__(self, driver, enclosure, measured=None, reference_voltage=2.83,
                 frd_reference_voltage=2.83, blend_low=150.0, blend_high=500.0):
        if reference_voltage <= 0 or frd_reference_voltage <= 0:
            raise ValueError("Reference voltages must be positive.")
        if blend_low <= 0 or blend_high <= blend_low:
            raise ValueError("Blend limits must be positive and increasing.")
        self.driver = driver
        self.enclosure = enclosure
        self.measured = measured
        self.reference_voltage = reference_voltage
        self.frd_reference_voltage = frd_reference_voltage
        self.blend_low = blend_low
        self.blend_high = blend_high
        self.frd = measured.frd if measured else None
        self.impedance = measured.impedance if measured else None

    def _measurement_weight(self, frequency):
        if frequency <= self.blend_low:
            return 0.0
        if frequency >= self.blend_high:
            return 1.0
        x = math.log(frequency / self.blend_low) / math.log(self.blend_high / self.blend_low)
        return 0.5 - 0.5 * math.cos(math.pi * x)

    def response(self, frequency):
        modeled = simulate_point(
            self.driver, self.enclosure, frequency, voltage=self.reference_voltage
        )["response"]
        if self.measured is None:
            return modeled
        weight = self._measurement_weight(frequency)
        measured = self.measured.response(frequency) * (
            self.reference_voltage / self.frd_reference_voltage
        )
        return modeled * (1 - weight) + measured * weight

    def z(self, frequency):
        modeled = simulate_point(
            self.driver, self.enclosure, frequency, voltage=self.reference_voltage
        )["input_impedance"]
        if self.measured is None:
            return modeled
        weight = self._measurement_weight(frequency)
        measured = self.measured.z(frequency)
        return modeled * (1 - weight) + measured * weight

    def measurement_covered(self, frequency):
        if self.measured is None:
            return False
        return all(curve.frequency_range[0] <= frequency <= curve.frequency_range[1]
                   for curve in (self.measured.frd, self.measured.impedance))


def simulate(driver, enclosure, frequencies, voltage=2.83, distance=1.0,
             radiation_solid_angle=2 * math.pi):
    """Simulate a frequency sequence and append phase-derived group delay in seconds."""
    rows = [simulate_point(driver, enclosure, frequency, voltage, distance,
                           radiation_solid_angle) for frequency in frequencies]
    if len(rows) < 2 or any(a["frequency"] >= b["frequency"] for a, b in zip(rows, rows[1:])):
        raise ValueError("At least two strictly increasing frequencies are required.")

    phases = []
    previous = None
    offset = 0.0
    for row in rows:
        phase = cmath.phase(row["pressure"])
        if previous is not None:
            delta = phase - previous
            if delta > math.pi:
                offset -= 2 * math.pi
            elif delta < -math.pi:
                offset += 2 * math.pi
        phases.append(phase + offset)
        previous = phase

    for index, row in enumerate(rows):
        left = max(index - 1, 0)
        right = min(index + 1, len(rows) - 1)
        phase_slope = (phases[right] - phases[left]) / (
            2 * math.pi * (rows[right]["frequency"] - rows[left]["frequency"])
        )
        row["group_delay"] = -phase_slope
    return rows


def maximum_voltage(rows, driver, radiator=None, minimum_frequency=0.0,
                    maximum_port_velocity=None, input_voltage=2.83):
    """Return the linear voltage ceiling imposed by excursion and port velocity."""
    candidates = []
    for row in rows:
        if row["frequency"] < minimum_frequency:
            continue
        if driver.xmax is not None and row["cone_excursion"] > 0:
            candidates.append((input_voltage * driver.xmax / row["cone_excursion"], "cone excursion"))
        if radiator and radiator.xmax and row["radiator_excursion"]:
            candidates.append((input_voltage * radiator.xmax / row["radiator_excursion"], "PR excursion"))
        if maximum_port_velocity and row["port_velocity"]:
            candidates.append((input_voltage * maximum_port_velocity / row["port_velocity"], "port velocity"))
        if driver.power_handling_w and input_voltage > 0:
            impedance_magnitude = abs(row["input_impedance"])
            copper_power = input_voltage**2 * driver.re / impedance_magnitude**2
            if copper_power > 0:
                candidates.append((input_voltage * math.sqrt(driver.power_handling_w / copper_power),
                                   "thermal input-power estimate"))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])