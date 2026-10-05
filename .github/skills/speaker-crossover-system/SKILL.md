---
name: speaker-crossover-system
description: "Simulate or tune a user-defined passive/active multiway speaker crossover from measured FRD/ZMA. Use for ladder filters, Zobel/L-pad/notch, DSP, phase, impedance, directivity, or candidate networks."
argument-hint: "User-selected drivers, measured curves, branch topology, parts, offsets, and load limits"
---

# Crossover and System Simulation

1. Require user-selected drivers and matching measured on-baffle FRD/ZMA for every branch; verify explicit part identities.
2. Preserve the user’s active/passive topology, branch count, wiring, polarity, offset, component values/DCR/ESR, and amplifier impedance floor.
3. Use `system_calculator.py` for complex branch transfer and multiway summation; `active_filters.py` for per-way DSP; `calculate_system.py` for JSON/CSV runs.
4. Inspect requested angles, branch/system phase, group delay, impedance magnitude/phase, minimum impedance, measurement coverage, and polarity reversal.
5. Never promote textbook alignments or an optimizer score as a finished design. Require prototype measurement and component thermal/power checks.

If an angle is requested but unavailable, report a measurement blocker rather than silently omitting it. Weighted spatial results require valid user-supplied angular weights and complete relevant directional data. References: [crossover knowledge](../../../docs/DESIGN_KNOWLEDGE_BASE.md#8-design-the-crossover).