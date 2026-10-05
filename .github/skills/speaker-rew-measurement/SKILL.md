---
name: speaker-rew-measurement
description: "Prepare, import, or audit REW FRD/ZMA and UMIK calibration for loudspeaker design. Use for gated sweeps, nearfield splices, phase/time alignment, on-baffle angles, or measurement coverage."
argument-hint: "REW exports, mic calibration, angles, voltage, distance, and timing"
---

# REW Measurement Intake

1. Confirm individual-driver measurements on the final baffle, not a whole-system trace used as one branch.
2. Confirm mic orientation and matching UMIK 0/90-degree calibration. If REW already applied calibration, do not apply it again in the system config.
3. Import FRD columns (frequency, SPL, phase) and ZMA columns (frequency, magnitude, phase) through `response_data.py`; explicit `frd_files` plus `zma_file` paths may point directly to REW text exports.
4. Check phase presence, requested angle coverage, frequency ranges, drive voltage, distance, time reference, gate, and calibration coverage. Report holds/extrapolation and do not invent angles.
5. For bass, keep drive voltage consistent; measure woofer and port/PR separately, scale by radiating area, and splice to gated farfield/ground-plane data only in a defensible overlap band.

Output a file inventory and unverified conditions. The presence of a calibration file does not prove room reflections or timing are correct. References: [REW workflow](../../../docs/DESIGN_KNOWLEDGE_BASE.md#7-measure-drivers-in-the-finished-acoustic-geometry), [response reader](../../../scripts/measurement/response_data.py).