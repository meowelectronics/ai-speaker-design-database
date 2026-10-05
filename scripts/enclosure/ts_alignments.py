"""Reusable Thiele-Small and classical enclosure alignment calculations."""

import math


def derive_thiele_small(re, mms, cms, rms, bl, sd, density=1.18, speed=343.0):
    """Derive SI-unit T/S values from electrical, mechanical, and piston data."""
    if min(re, mms, cms, rms, bl, sd, density, speed) <= 0:
        raise ValueError("T/S inputs and acoustic constants must be positive.")
    fs = 1 / (2 * math.pi * math.sqrt(mms * cms))
    qms = 2 * math.pi * fs * mms / rms
    qes = 2 * math.pi * fs * mms * re / bl**2
    vas_m3 = density * speed**2 * cms * sd**2
    return dict(fs=fs, qms=qms, qes=qes, qts=qms*qes/(qms+qes), vas=vas_m3)


def derive_driver_components(fs, qes, qms, re, bl, sd, density=1.18, speed=343.0):
    """Derive Mms/Cms/Rms and efficiency from composite T/S values."""
    if min(fs, qes, qms, re, bl, sd, density, speed) <= 0:
        raise ValueError("T/S inputs and acoustic constants must be positive.")
    omega = 2 * math.pi * fs
    mms = qes * bl**2 / (omega * re)
    cms = 1 / (omega**2 * mms)
    rms = omega * mms / qms
    qts = qms * qes / (qms + qes)
    vas = density * speed**2 * cms * sd**2
    efficiency = density * sd**2 * bl**2 / (speed * 2 * math.pi * re * mms**2)
    spl_1w = 112.1 + 10 * math.log10(efficiency)
    spl_2_83v = spl_1w + 10 * math.log10(8 / re)
    return dict(fs=fs, qes=qes, qms=qms, qts=qts, re=re, bl=bl, sd=sd,
                mms=mms, cms=cms, rms=rms, vas=vas, efficiency=efficiency,
                spl_1w=spl_1w, spl_2_83v=spl_2_83v)


def driver_components_from_thiele_small(fs, qes, qms, re, vas, sd, le=0.0,
                                        xmax=None, density=1.18, speed=343.0):
    """Build the complex-model SI parameters from common composite datasheet T/S values.

    Required: Fs, Qes, Qms, Re, Vas, and Sd. BL is derived from Qes; Mms/Cms/Rms
    are derived from Fs/Qes/Qms/Vas/Sd. This is appropriate for rounded published or
    measured T/S sets, but fitting complex ZMA with independently measured BL/Sd is
    preferable when available.
    """
    if min(fs, qes, qms, re, vas, sd, density, speed) <= 0 or le < 0:
        raise ValueError("T/S inputs must be positive; Le must be nonnegative.")
    cms = vas / (density * speed**2 * sd**2)
    mms = 1 / ((2 * math.pi * fs)**2 * cms)
    bl = math.sqrt(2 * math.pi * fs * mms * re / qes)
    components = derive_driver_components(fs, qes, qms, re, bl, sd, density, speed)
    return {
        "re": re,
        "le": le,
        "bl": bl,
        "mms": mms,
        "cms": cms,
        "rms": components["rms"],
        "sd": sd,
        "xmax": xmax,
        "fs": fs,
        "qes": qes,
        "qms": qms,
        "qts": components["qts"],
        "vas": components["vas"],
        "efficiency": components["efficiency"],
        "spl_1w": components["spl_1w"],
        "spl_2_83v": components["spl_2_83v"],
    }


def equivalent_driver_array(driver, series=1, parallel=1):
    """Return an ideal identical-driver array equivalent (series strings x parallel)."""
    if not all(isinstance(count, int) and count > 0 for count in (series, parallel)):
        raise ValueError("Series and parallel counts must be positive integers.")
    count = series * parallel
    result = dict(driver)
    result["series"], result["parallel"] = series, parallel
    for key in ("vas", "sd", "vd", "mms", "rms", "pe"):
        if key in result and result[key] is not None:
            result[key] *= count
    if "cms" in result and result["cms"] is not None:
        result["cms"] /= count
    for key in ("re", "le"):
        if key in result and result[key] is not None:
            result[key] *= series / parallel
    if "bl" in result and result["bl"] is not None:
        result["bl"] *= series
    return result


def sealed_alignment(driver, target_qtc=0.707, qa=math.inf):
    """Solve a sealed-box target Qtc, optionally including absorption losses."""
    fs, qts, vas = driver["fs"], driver["qts"], driver["vas"]
    if qa <= 0:
        raise ValueError("Qa must be positive.")
    loss = 0 if math.isinf(qa) else 1 / qa
    ideal_qtc = target_qtc + loss
    if min(fs, qts, vas, target_qtc) <= 0 or ideal_qtc <= qts:
        raise ValueError("Use positive values and a target Qtc above the driver's Qts.")
    alpha = (ideal_qtc / qts)**2 - 1
    volume = vas / alpha
    fc = fs * math.sqrt(1 + alpha)
    qtc = qts * math.sqrt(1 + alpha) - loss
    a = 1 / qtc**2 - 2
    f3 = fc * math.sqrt((a + math.sqrt(a*a + 4)) / 2)
    return dict(volume=volume, qtc=qtc, fc=fc, f3=f3)


def _chebyshev_coefficients(k):
    denominator = 0.125*k**4 + 0.75*k**2 + 0.125
    a1 = 2.6131*k / denominator**0.25
    a2 = (2.4143*k**2 + 1) / denominator**0.5
    a3 = (0.9239*k**3 + 1.6892*k) / denominator**0.75
    return a1, a2, a3


def _chebyshev_k(qts):
    low, high = 0.05, 20.0
    q_low = 1 / math.sqrt(math.prod((_chebyshev_coefficients(low)[0],
                                     _chebyshev_coefficients(low)[2])))
    q_high = 1 / math.sqrt(math.prod((_chebyshev_coefficients(high)[0],
                                      _chebyshev_coefficients(high)[2])))
    if not q_high <= qts <= q_low:
        raise ValueError("Qts is outside the supported C4 alignment range.")
    for _ in range(80):
        middle = (low + high) / 2
        a1, _, a3 = _chebyshev_coefficients(middle)
        q_middle = 1 / math.sqrt(a1*a3)
        if q_middle > qts:
            low = middle
        else:
            high = middle
    return (low + high) / 2


def classical_vented_alignments(driver, response_model):
    """Return QB3/C4 alignment seeds, evaluated by the caller's response model."""
    qts, vas, fs = driver["qts"], driver["vas"], driver["fs"]
    if not 0 < qts < 1 or min(vas, fs) <= 0:
        raise ValueError("Use positive Fs/Vas and a Qts between zero and one.")

    k = _chebyshev_k(qts)
    a1, a2, a3 = _chebyshev_coefficients(k)
    c4_alpha = (a1*a2*a3 - a1*a1 - a3*a3) / (a3*a3)
    alignments = {"C4": (c4_alpha, a1/a3)}

    qb3_h = 1 / (qts * math.sqrt(8 - 8*qts*qts))
    qb3_a2 = 1 / (2*qts*qts*qb3_h)
    qb3_a1 = (2 + qb3_a2*qb3_a2) / (2*math.sqrt(2*qb3_a2))
    qb3_a3 = math.sqrt(2*qb3_a2)
    qb3_alpha = (qb3_a1*qb3_a2*qb3_a3 - qb3_a1**2 - qb3_a3**2) / qb3_a3**2
    alignments["QB3"] = (qb3_alpha, qb3_h)

    output = {}
    for name, (alpha, ratio) in alignments.items():
        if alpha <= 0 or ratio <= 0:
            raise ValueError(f"Invalid {name} alignment for this Qts.")
        volume, tuning = vas/alpha, fs*ratio
        response = response_model(fs, qts, vas, volume, tuning)
        output[name] = dict(volume=volume, tuning=tuning,
                            f3=response[0] if response else None,
                            peak_db=response[1] if response else None)
    return output