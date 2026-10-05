"""Fit driver electro-mechanical parameters to complex impedance measurements."""

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path

from scipy.optimize import least_squares

from scripts.enclosure.acoustic_model import DriverParameters
from scripts.measurement.response_data import ComplexCurve


def _impedance(frequency, values, bl, reference_frequency):
    re, le, exponent, rms, mms, cms = values
    omega = 2 * math.pi * frequency
    reference_omega = 2 * math.pi * reference_frequency
    electrical = re + le * (1j * omega)**exponent / reference_omega**(exponent - 1)
    mechanical = rms + 1j * omega * mms + 1 / (1j * omega * cms)
    return electrical + bl**2 / mechanical


def fit_impedance(curve, initial, bl, sd, xmax=None, frequency_range=None,
                  max_samples=400, reference_frequency=1000.0):
    """Fit Re, Le, fractional-Le exponent, Rms, Mms and Cms to complex ZMA.

    ``initial`` is an SI-unit mapping with ``re``, ``le``, ``rms``, ``mms``,
    and ``cms`` keys. ``bl`` (Tm) and ``sd`` (m2) must be independently known.
    ZMA must include phase; magnitude-only data cannot uniquely constrain this fit.
    """
    if not curve.phase_available:
        raise ValueError("Complex impedance fitting requires phase-bearing ZMA data.")
    if bl <= 0 or sd <= 0 or reference_frequency <= 0:
        raise ValueError("BL, Sd, and reference frequency must be positive.")
    start_frequency, stop_frequency = frequency_range or curve.frequency_range
    indices = [index for index, frequency in enumerate(curve.frequencies)
               if start_frequency <= frequency <= stop_frequency]
    if len(indices) < 12:
        raise ValueError("At least 12 impedance samples are required in the fit range.")
    if len(indices) > max_samples:
        step = (len(indices) - 1) / (max_samples - 1)
        indices = [indices[round(index * step)] for index in range(max_samples)]

    frequencies = [curve.frequencies[index] for index in indices]
    measured = [curve.value(frequency) for frequency in frequencies]
    initial_values = [initial[key] for key in ("re", "le", "rms", "mms", "cms")]
    if min(initial_values) <= 0:
        raise ValueError("Initial Re, Le, Rms, Mms, and Cms values must be positive.")
    exponent = initial.get("inductance_exponent", 0.9)
    parameters = [initial["re"], initial["le"], exponent,
                  initial["rms"], initial["mms"], initial["cms"]]
    lower = [initial["re"] * 0.05, initial["le"] * 0.001, 0.5,
             initial["rms"] * 0.001, initial["mms"] * 0.001, initial["cms"] * 0.001]
    upper = [initial["re"] * 20, initial["le"] * 1000, 1.0,
             initial["rms"] * 1000, initial["mms"] * 1000, initial["cms"] * 1000]
    scales = [max(abs(value), 1e-12) for value in parameters]
    log_weights = [math.log(frequencies[min(index + 1, len(frequencies) - 1)] /
                            frequencies[max(index - 1, 0)]) / 2
                   for index in range(len(frequencies))]
    mean_weight = sum(log_weights) / len(log_weights)
    weights = [math.sqrt(max(weight / mean_weight, 1e-12)) for weight in log_weights]

    def residual(values):
        result = []
        for frequency, actual, weight in zip(frequencies, measured, weights):
            predicted = _impedance(frequency, values, bl, reference_frequency)
            scale = max(abs(actual), initial["re"], 1e-6)
            delta = (predicted - actual) / scale * weight
            result.extend((delta.real, delta.imag))
        return result

    fit = least_squares(residual, parameters, bounds=(lower, upper), x_scale=scales,
                        max_nfev=5000, ftol=1e-11, xtol=1e-11, gtol=1e-11)
    re, le_coefficient, le_exponent, rms, mms, cms = fit.x
    reference_omega = 2 * math.pi * reference_frequency
    driver = DriverParameters(
        re=re,
        le=le_coefficient,
        bl=bl,
        mms=mms,
        cms=cms,
        rms=rms,
        sd=sd,
        xmax=xmax,
        name=initial.get("name", "fitted driver"),
        inductance_exponent=le_exponent,
        inductance_reference_frequency=reference_frequency,
    )
    return {
        "driver": driver,
        "success": fit.success,
        "message": fit.message,
        "cost": fit.cost,
        "rms_relative_complex_error": math.sqrt(2 * fit.cost / len(frequencies)),
        "sample_count": len(frequencies),
        "fit_frequency_range": (frequencies[0], frequencies[-1]),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("zma", help="complex impedance file with frequency, magnitude, phase")
    parser.add_argument("--bl", type=float, required=True, help="motor strength in Tm")
    parser.add_argument("--sd", type=float, required=True, help="cone area in square metres")
    parser.add_argument("--re", type=float, required=True, help="initial DC resistance in ohms")
    parser.add_argument("--le-mh", type=float, required=True, help="initial inductance in mH")
    parser.add_argument("--rms", type=float, required=True, help="initial mechanical resistance in Ns/m")
    parser.add_argument("--mms-g", type=float, required=True, help="initial moving mass in grams")
    parser.add_argument("--cms-mm-n", type=float, required=True, help="initial compliance in mm/N")
    parser.add_argument("--xmax-mm", type=float, help="linear one-way excursion in mm")
    parser.add_argument("--name", default="fitted driver")
    parser.add_argument("--min-hz", type=float)
    parser.add_argument("--max-hz", type=float)
    parser.add_argument("--output", help="write fitted parameters to JSON")
    args = parser.parse_args()

    curve = ComplexCurve.from_file(args.zma, magnitude_is_db=False)
    fit = fit_impedance(
        curve,
        {
            "name": args.name,
            "re": args.re,
            "le": args.le_mh * 1e-3,
            "rms": args.rms,
            "mms": args.mms_g * 1e-3,
            "cms": args.cms_mm_n * 1e-3,
        },
        bl=args.bl,
        sd=args.sd,
        xmax=args.xmax_mm * 1e-3 if args.xmax_mm is not None else None,
        frequency_range=(args.min_hz or curve.frequency_range[0],
                         args.max_hz or curve.frequency_range[1]),
    )
    driver = fit["driver"]
    payload = {
        "driver": asdict(driver),
        "derived": {"fs": driver.fs, "qes": driver.qes, "qms": driver.qms,
                    "qts": driver.qts, "vas_m3": driver.vas},
        "fit": {key: value for key, value in fit.items() if key != "driver"},
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote fitted driver parameters to {output}")
    print(f"Fit {'converged' if fit['success'] else 'did not converge'}: "
          f"Fs={driver.fs:.2f} Hz, Qts={driver.qts:.3f}, "
          f"Vas={driver.vas*1000:.3f} L, relative complex error="
          f"{fit['rms_relative_complex_error']:.4f}")


if __name__ == "__main__":
    main()