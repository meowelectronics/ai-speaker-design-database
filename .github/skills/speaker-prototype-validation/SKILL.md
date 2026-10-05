---
name: speaker-prototype-validation
description: "Review a built loudspeaker prototype against user goals and model predictions. Use for verification plans, pass/fail checklists, voicing, room placement, or decisions about prototype readiness."
argument-hint: "Build details, measured results, targets, and model package"
---

# Prototype Verification

1. Check build identity, dimensions, net volume, displacements, seals, port/PR installation, wiring, and crossover component values/DCR.
2. Compare in-box impedance/tuning, nearfield bass, gated on/off-axis FRD, full system impedance, polarity, and excursion/noise observations against the package.
3. Separate measured facts, simulation estimates, user listening feedback, and unavailable tests.
4. Record unresolved distortion, thermal compression, port turbulence, panel vibration, room response, and amplifier-load risks explicitly.
5. Issue `pass`, `needs retest`, or `fail` per criterion; never use `READY_FOR_PROTOTYPE_VALIDATION` as evidence that a built unit passed.

Use the checklist in [DESIGN_KNOWLEDGE_BASE.md](../../../docs/DESIGN_KNOWLEDGE_BASE.md#11-measurementconstruction-checklist).