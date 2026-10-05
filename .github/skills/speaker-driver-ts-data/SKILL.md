---
name: speaker-driver-ts-data
description: "Validate user-selected driver data, datasheet/measured Thiele-Small parameters, array wiring, or complex-ZMA fitting. Use before enclosure simulation or when T/S values conflict."
argument-hint: "Driver identity, T/S source, units, and impedance files"
---

# Driver and T/S Data

1. Confirm exact user-selected model/part number and source: `datasheet_ts`, `measured_ts`, `components`, or `fitted_json`.
2. Check required parameters and convert to SI at input boundaries. Record temperature, mounting, drive level, frequency range, and test method where known.
3. For composite T/S, use `driver_components_from_thiele_small()`; for direct components use `derive_thiele_small()` to cross-check.
4. For arrays, record physical quantity and series/parallel count; use `equivalent_driver_array()` and verify wiring identity.
5. For a ZMA fit, require phase-bearing impedance, known BL and Sd, reasonable initial values, bounded fit range, and review of residuals.
6. Apply amplifier/cable/crossover series resistance with `corrected_q_values()` before final alignment checks.

Never replace a missing parameter with an invented typical value. Mark rounded datasheet-derived components as derived, not measured. References: [T/S knowledge](../../../docs/DESIGN_KNOWLEDGE_BASE.md#3-obtain-trustworthy-ts-parameters), [impedance fitter](../../../scripts/measurement/impedance_fit.py).