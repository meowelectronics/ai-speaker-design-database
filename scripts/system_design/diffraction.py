"""Rectangular-baffle edge diffraction by radial edge summation.

The baffle edge is sampled radially from the driver position. Each element re-radiates
with the extra path length rho_i, and the weights are normalised so the sum tends to
-6 dB as k->0 (4pi -> 2pi transition) and to 0 dB as k->inf.
"""
import cmath, math

C_AIR = 343.0

def edge_distance(x0, y0, w, h, phi):
    """Distance from (x0,y0) to the rectangle boundary along direction phi."""
    cx, sy = math.cos(phi), math.sin(phi)
    ts = []
    if abs(cx) > 1e-12:
        ts.append(((w - x0) if cx > 0 else -x0) / cx)
    if abs(sy) > 1e-12:
        ts.append(((h - y0) if sy > 0 else -y0) / sy)
    return min(t for t in ts if t > 1e-9)

def diffraction(f, x0, y0, w, h, n=720, step_lin=0.5):
    """Complex on-axis baffle response. step_lin=0.5 -> -6 dB low-frequency step."""
    k = 2 * math.pi * f / C_AIR
    acc = 0j
    for i in range(n):
        rho = edge_distance(x0, y0, w, h, 2 * math.pi * i / n)
        acc += cmath.exp(-1j * k * rho)
    return 1 - step_lin * acc / n

def make(x0, y0, w, h, n=720, step_lin=0.5):
    cache = {}
    def H(f):
        if f not in cache:
            cache[f] = diffraction(f, x0, y0, w, h, n, step_lin)
        return cache[f]
    return H

if __name__ == "__main__":
    W, H = 0.130, 0.295
    TW = make(W / 2, H - 0.060, W, H)      # tweeter 60 mm from top
    WF = make(W / 2, H - 0.170, W, H)      # woofer 110 mm below tweeter
    print("validation: LF -> -6 dB, HF -> 0 dB")
    print(f"   woofer   10 Hz : {20*math.log10(abs(WF(10))):+6.2f} dB")
    print(f"   woofer 18000 Hz: {20*math.log10(abs(WF(18000))):+6.2f} dB")
    print("\n  freq |  woofer | tweeter   (dB, free-standing baffle 130 x 295 mm)")
    for ft in (40,60,80,100,150,200,300,400,500,700,1000,1400,2000,3000,
               4000,6000,8000,12000,16000):
        print(f"{ft:6d} | {20*math.log10(abs(WF(ft))):+7.2f} | "
              f"{20*math.log10(abs(TW(ft))):+7.2f}")
    lo = 20*math.log10(abs(WF(50)))
    hi = sum(20*math.log10(abs(WF(f))) for f in (3000,4000,5000,6000))/4
    print(f"\n  realised woofer step = {hi-lo:.2f} dB")
    xo = 20*math.log10(abs(WF(3000))) - 20*math.log10(abs(TW(3000)))
    print(f"  woofer-tweeter diffraction difference @3 kHz = {xo:+.2f} dB")
