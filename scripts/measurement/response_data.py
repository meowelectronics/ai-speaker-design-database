"""Read and interpolate complex FRD/ZMA measurement files."""

from dataclasses import dataclass
import cmath
import math
from pathlib import Path


class MeasurementCoverageError(ValueError):
    """Requested measurement angles/frequency ranges are not available."""


def _unwrap_degrees(degrees):
    result = []
    offset = 0.0
    previous = None
    for value in degrees:
        if previous is not None:
            delta = value - previous
            if delta > 180:
                offset -= 360
            elif delta < -180:
                offset += 360
        result.append(value + offset)
        previous = value
    return result


@dataclass(frozen=True)
class ComplexCurve:
    frequencies: tuple
    magnitudes: tuple
    phases: tuple
    magnitude_is_db: bool
    phase_available: bool = True

    def __post_init__(self):
        if len(self.frequencies) < 2 or not (
            len(self.frequencies) == len(self.magnitudes) == len(self.phases)
        ):
            raise ValueError("A response curve needs at least two complete samples.")
        if any(f <= 0 for f in self.frequencies):
            raise ValueError("Response frequencies must be positive.")
        if any(a >= b for a, b in zip(self.frequencies, self.frequencies[1:])):
            raise ValueError("Response frequencies must be strictly increasing.")

    @classmethod
    def from_file(cls, path, magnitude_is_db):
        frequencies, magnitudes, phase_degrees = [], [], []
        phase_available = True
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line[0] in "*#;'!":
                continue
            fields = line.replace(",", " ").split()
            try:
                frequency, magnitude = float(fields[0]), float(fields[1])
            except (ValueError, IndexError):
                continue
            if len(fields) > 2:
                try:
                    phase = float(fields[2])
                except ValueError:
                    phase_available = False
                    phase = 0.0
            else:
                phase_available = False
                phase = 0.0
            frequencies.append(frequency)
            magnitudes.append(magnitude)
            phase_degrees.append(phase)

        if not phase_available:
            phase_degrees = [0.0] * len(frequencies)
        phases = tuple(math.radians(value) for value in _unwrap_degrees(phase_degrees))
        return cls(tuple(frequencies), tuple(magnitudes), phases,
                   magnitude_is_db, phase_available)

    @property
    def frequency_range(self):
        return self.frequencies[0], self.frequencies[-1]

    def _interpolated(self, values, frequency):
        if frequency <= self.frequencies[0]:
            return values[0]
        if frequency >= self.frequencies[-1]:
            return values[-1]
        low, high = 0, len(self.frequencies) - 1
        while high - low > 1:
            middle = (low + high) // 2
            if self.frequencies[middle] <= frequency:
                low = middle
            else:
                high = middle
        ratio = math.log(frequency / self.frequencies[low]) / math.log(
            self.frequencies[high] / self.frequencies[low]
        )
        return values[low] + ratio * (values[high] - values[low])

    def value(self, frequency):
        if frequency <= 0:
            raise ValueError("Interpolation frequency must be positive.")
        magnitude = self._interpolated(self.magnitudes, frequency)
        if self.magnitude_is_db:
            magnitude = 10 ** (magnitude / 20)
        phase = self._interpolated(self.phases, frequency)
        return cmath.rect(magnitude, phase)

    def magnitude_db(self, frequency):
        value = self.value(frequency)
        return 20 * math.log10(max(abs(value), 1e-30))

    def corrected_magnitude(self, correction):
        """Return an FRD curve with additive microphone dB corrections applied."""
        if not self.magnitude_is_db:
            raise ValueError("Microphone magnitude correction applies only to SPL curves.")
        if (correction.frequencies[0] > self.frequencies[0]
                or correction.frequencies[-1] < self.frequencies[-1]):
            raise ValueError("Microphone calibration must cover the full FRD frequency range.")
        magnitudes = tuple(
            value + correction.value(frequency)
            for frequency, value in zip(self.frequencies, self.magnitudes)
        )
        return ComplexCurve(self.frequencies, magnitudes, self.phases, True,
                            self.phase_available)


@dataclass(frozen=True)
class MagnitudeCorrection:
    frequencies: tuple
    corrections_db: tuple

    def __post_init__(self):
        if len(self.frequencies) < 2 or len(self.frequencies) != len(self.corrections_db):
            raise ValueError("Microphone correction requires at least two frequency/dB pairs.")
        if any(frequency <= 0 for frequency in self.frequencies):
            raise ValueError("Calibration frequencies must be positive.")
        if any(a >= b for a, b in zip(self.frequencies, self.frequencies[1:])):
            raise ValueError("Calibration frequencies must be strictly increasing.")

    @property
    def frequency_range(self):
        return self.frequencies[0], self.frequencies[-1]

    @classmethod
    def from_file(cls, path):
        frequencies, corrections = [], []
        for line in Path(path).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line[0] in "*#;'!":
                continue
            fields = line.replace(",", " ").split()
            try:
                frequency, correction = float(fields[0]), float(fields[1])
            except (ValueError, IndexError):
                continue
            frequencies.append(frequency)
            corrections.append(correction)
        return cls(tuple(frequencies), tuple(corrections))

    def value(self, frequency):
        if frequency < self.frequencies[0] or frequency > self.frequencies[-1]:
            raise ValueError("Frequency is outside the microphone calibration range.")
        if frequency == self.frequencies[-1]:
            return self.corrections_db[-1]
        low, high = 0, len(self.frequencies) - 1
        while high - low > 1:
            middle = (low + high) // 2
            if self.frequencies[middle] <= frequency:
                low = middle
            else:
                high = middle
        ratio = math.log(frequency / self.frequencies[low]) / math.log(
            self.frequencies[high] / self.frequencies[low]
        )
        return self.corrections_db[low] + ratio * (
            self.corrections_db[high] - self.corrections_db[low]
        )


@dataclass(frozen=True)
class MeasuredDriver:
    frd: ComplexCurve
    impedance: ComplexCurve
    name: str
    angle: int = 0

    @classmethod
    def from_folder(cls, folder, stem, angle=0):
        folder = Path(folder)
        return cls(
            ComplexCurve.from_file(folder / "FRD" / f"{stem}@{angle}.frd", True),
            ComplexCurve.from_file(folder / "ZMA" / f"{stem}.zma", False),
            stem,
            angle,
        )

    def response(self, frequency):
        return self.frd.value(frequency)

    def z(self, frequency):
        return self.impedance.value(frequency)


class InterpolatedAngleDriver:
    def __init__(self, lower, upper, angle):
        self.lower = lower
        self.upper = upper
        self.angle = angle
        self.name = lower.name
        self.impedance = lower.impedance

    def response(self, frequency):
        if self.lower.angle == self.upper.angle:
            return self.lower.response(frequency)
        ratio = (self.angle - self.lower.angle) / (self.upper.angle - self.lower.angle)
        lower = self.lower.response(frequency)
        upper = self.upper.response(frequency)
        lower_db = 20 * math.log10(max(abs(lower), 1e-30))
        upper_db = 20 * math.log10(max(abs(upper), 1e-30))
        phase_delta = cmath.phase(upper) - cmath.phase(lower)
        phase_delta = (phase_delta + math.pi) % (2 * math.pi) - math.pi
        magnitude = 10 ** ((lower_db + ratio * (upper_db - lower_db)) / 20)
        phase = cmath.phase(lower) + ratio * phase_delta
        return cmath.rect(magnitude, phase)

    def z(self, frequency):
        return self.lower.z(frequency)

    def measurement_covered(self, frequency):
        return all(curve.frequency_range[0] <= frequency <= curve.frequency_range[1]
                   for curve in (self.lower.frd, self.upper.frd, self.impedance))


def measured_driver_at_angle(drivers, angle):
    """Return an exact or phase-aware interpolated measured driver angle.

    Returns None outside the measured angular span rather than extrapolating.
    """
    if angle in drivers:
        return drivers[angle]
    lower_angles = [value for value in drivers if value < angle]
    upper_angles = [value for value in drivers if value > angle]
    if not lower_angles or not upper_angles:
        return None
    lower = drivers[max(lower_angles)]
    upper = drivers[min(upper_angles)]
    return InterpolatedAngleDriver(lower, upper, angle)


def measured_angles(folder, stem, angles=(0, 15, 30, 45), calibration=None):
    """Load available horizontal FRD angles while sharing the driver's ZMA."""
    folder = Path(folder)
    zma = ComplexCurve.from_file(folder / "ZMA" / f"{stem}.zma", False)
    drivers = {}
    for angle in angles:
        path = folder / "FRD" / f"{stem}@{angle}.frd"
        if path.is_file():
            frd = ComplexCurve.from_file(path, True)
            if calibration is not None:
                frd = frd.corrected_magnitude(calibration)
            drivers[angle] = MeasuredDriver(
                frd, zma, stem, angle
            )
    if not drivers:
        raise FileNotFoundError(f"No FRD angle files found for {stem} in {folder / 'FRD'}.")
    return drivers


def measured_driver_files(frd_files, zma_file, calibration=None):
    """Load explicit angle-to-FRD paths and one shared ZMA, including REW text exports."""
    zma = ComplexCurve.from_file(zma_file, False)
    drivers = {}
    for angle, path in frd_files.items():
        angle = int(angle)
        frd = ComplexCurve.from_file(path, True)
        if calibration is not None:
            frd = frd.corrected_magnitude(calibration)
        drivers[angle] = MeasuredDriver(frd, zma, Path(path).stem, angle)
    if not drivers:
        raise ValueError("At least one explicit FRD path is required.")
    return drivers