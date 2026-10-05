"""Complex digital filters for active/DSP loudspeaker branch simulation."""

from dataclasses import dataclass
import cmath
import math

from scipy.signal import bessel as design_bessel
from scipy.signal import butter as design_butterworth


@dataclass(frozen=True)
class Biquad:
    b0: float
    b1: float
    b2: float
    a0: float
    a1: float
    a2: float

    def __post_init__(self):
        if self.a0 == 0 or not all(math.isfinite(value) for value in (
            self.b0, self.b1, self.b2, self.a0, self.a1, self.a2
        )):
            raise ValueError("Biquad coefficients must be finite and a0 must be nonzero.")

    def response(self, frequency, sample_rate):
        if frequency < 0 or sample_rate <= 0 or frequency >= sample_rate / 2:
            raise ValueError("Frequency must be nonnegative and below Nyquist; sample rate positive.")
        z1 = cmath.exp(-2j * math.pi * frequency / sample_rate)
        z2 = z1 * z1
        numerator = self.b0 + self.b1 * z1 + self.b2 * z2
        denominator = self.a0 + self.a1 * z1 + self.a2 * z2
        return numerator / denominator


def _parameters(cutoff, sample_rate, q):
    if sample_rate <= 0 or not 0 < cutoff < sample_rate / 2 or q <= 0:
        raise ValueError("Cutoff must be below Nyquist, sample rate and Q positive.")
    omega = 2 * math.pi * cutoff / sample_rate
    return omega, math.cos(omega), math.sin(omega) / (2 * q)


def lowpass(cutoff, sample_rate, q=math.sqrt(0.5)):
    omega, cosine, alpha = _parameters(cutoff, sample_rate, q)
    del omega
    a0, a1, a2 = 1 + alpha, -2 * cosine, 1 - alpha
    return Biquad((1 - cosine) / 2 / a0, (1 - cosine) / a0,
                  (1 - cosine) / 2 / a0, 1, a1 / a0, a2 / a0)


def highpass(cutoff, sample_rate, q=math.sqrt(0.5)):
    omega, cosine, alpha = _parameters(cutoff, sample_rate, q)
    del omega
    a0, a1, a2 = 1 + alpha, -2 * cosine, 1 - alpha
    return Biquad((1 + cosine) / 2 / a0, -(1 + cosine) / a0,
                  (1 + cosine) / 2 / a0, 1, a1 / a0, a2 / a0)


def peaking_eq(center, sample_rate, q, gain_db):
    omega, cosine, alpha = _parameters(center, sample_rate, q)
    amplitude = 10 ** (gain_db / 40)
    a0 = 1 + alpha / amplitude
    return Biquad((1 + alpha * amplitude) / a0, -2 * cosine / a0,
                  (1 - alpha * amplitude) / a0, 1,
                  -2 * cosine / a0, (1 - alpha / amplitude) / a0)


def allpass(center, sample_rate, q):
    omega, cosine, alpha = _parameters(center, sample_rate, q)
    del omega
    a0 = 1 + alpha
    return Biquad((1 - alpha) / a0, -2 * cosine / a0,
                  (1 + alpha) / a0, 1, -2 * cosine / a0, (1 - alpha) / a0)


def _shelf(cutoff, sample_rate, gain_db, slope, high):
    if sample_rate <= 0 or not 0 < cutoff < sample_rate / 2 or slope <= 0:
        raise ValueError("Shelf cutoff must be below Nyquist; sample rate and slope positive.")
    amplitude = 10 ** (gain_db / 40)
    omega = 2 * math.pi * cutoff / sample_rate
    cosine, sine = math.cos(omega), math.sin(omega)
    alpha = sine / 2 * math.sqrt((amplitude + 1 / amplitude) * (1 / slope - 1) + 2)
    beta = 2 * math.sqrt(amplitude) * alpha
    if high:
        b0 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosine + beta)
        b1 = -2 * amplitude * ((amplitude - 1) + (amplitude + 1) * cosine)
        b2 = amplitude * ((amplitude + 1) + (amplitude - 1) * cosine - beta)
        a0 = (amplitude + 1) - (amplitude - 1) * cosine + beta
        a1 = 2 * ((amplitude - 1) - (amplitude + 1) * cosine)
        a2 = (amplitude + 1) - (amplitude - 1) * cosine - beta
    else:
        b0 = amplitude * ((amplitude + 1) - (amplitude - 1) * cosine + beta)
        b1 = 2 * amplitude * ((amplitude - 1) - (amplitude + 1) * cosine)
        b2 = amplitude * ((amplitude + 1) - (amplitude - 1) * cosine - beta)
        a0 = (amplitude + 1) + (amplitude - 1) * cosine + beta
        a1 = -2 * ((amplitude - 1) + (amplitude + 1) * cosine)
        a2 = (amplitude + 1) + (amplitude - 1) * cosine - beta
    return Biquad(b0 / a0, b1 / a0, b2 / a0, 1, a1 / a0, a2 / a0)


def low_shelf(cutoff, sample_rate, gain_db, slope=1.0):
    return _shelf(cutoff, sample_rate, gain_db, slope, False)


def high_shelf(cutoff, sample_rate, gain_db, slope=1.0):
    return _shelf(cutoff, sample_rate, gain_db, slope, True)


def active_pass_filter(direction, order, alignment, cutoff, sample_rate):
    """Design analog-target active Butterworth, Bessel, or Linkwitz-Riley filter sections."""
    family = alignment.lower().replace("-", "_").replace(" ", "_")
    if direction not in {"lowpass", "highpass"} or not 0 < cutoff < sample_rate / 2:
        raise ValueError("Use lowpass/highpass direction and a cutoff below Nyquist.")
    if order not in {1, 2, 3, 4, 5, 6, 8}:
        raise ValueError("Supported active filter orders are 1, 2, 3, 4, 5, 6, and 8.")
    if family == "linkwitz_riley":
        if order % 2:
            raise ValueError("Linkwitz-Riley filters require an even order.")
        base = design_butterworth(order // 2, cutoff, btype=direction,
                                  fs=sample_rate, output="sos")
        sections = list(base) + list(base)
    elif family == "butterworth":
        sections = design_butterworth(order, cutoff, btype=direction,
                                      fs=sample_rate, output="sos")
    elif family == "bessel":
        sections = design_bessel(order, cutoff, btype=direction, norm="mag",
                                 fs=sample_rate, output="sos")
    else:
        raise ValueError(f"Unsupported active filter alignment: {alignment}.")
    return tuple(Biquad(*map(float, section)) for section in sections)


@dataclass(frozen=True)
class LinkwitzTransform:
    source_frequency: float
    source_q: float
    target_frequency: float
    target_q: float
    linear_phase: bool = False

    def __post_init__(self):
        if min(self.source_frequency, self.source_q, self.target_frequency, self.target_q) <= 0:
            raise ValueError("Linkwitz-transform frequencies and Q values must be positive.")

    def response(self, frequency, sample_rate=None):
        if frequency < 0:
            raise ValueError("Frequency must be nonnegative.")
        source_ratio = frequency / self.source_frequency
        target_ratio = frequency / self.target_frequency
        source = complex(1 - source_ratio**2, source_ratio / self.source_q)
        target = complex(1 - target_ratio**2, target_ratio / self.target_q)
        result = source / target
        return complex(abs(result)) if self.linear_phase else result


@dataclass(frozen=True)
class ActiveFilterChain:
    filters: tuple = ()
    delay_seconds: float = 0.0
    sample_rate: float = 48000.0

    def __post_init__(self):
        if self.delay_seconds < 0 or self.sample_rate <= 0:
            raise ValueError("Delay must be nonnegative and sample rate positive.")

    def response(self, frequency):
        result = cmath.exp(-2j * math.pi * frequency * self.delay_seconds)
        for filter_ in self.filters:
            result *= filter_.response(frequency, self.sample_rate)
        return result