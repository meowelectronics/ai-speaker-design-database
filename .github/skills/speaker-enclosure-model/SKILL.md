---
name: speaker-enclosure-model
description: "Model a user-selected sealed, vented, aperiodic, or passive-radiator enclosure; check volume, tuning, port/PR geometry, excursion, and wiring arrays. Use for bass alignment or cabinet calculations."
argument-hint: "Selected driver/T/S, alignment, net volume, tuning, port or PR data"
---

# Enclosure Modeling

1. Confirm user-selected driver/source, net volume, alignment, losses, wiring, and any port/PR data.
2. If deriving net volume from rectangular dimensions, require outer dimensions, wall thickness, and a named displacement ledger; nonrectangular CAD must supply its measured/calculated net volume.
3. Use `acoustic_model.py` and `ts_alignments.py`; run `python -B -m scripts.enclosure.calculate_box CONFIG.json` or the universal workflow.
4. Inspect complex impedance, response/F3, group delay, cone/PR excursion, port velocity, port pipe resonance, and series-loss assumptions.
5. Mark predicted dimensions and limits as model estimates; compare with in-box impedance, tuning, and nearfield response before build approval.

Do not optimize to F3 alone. Flag missing displacement, Q losses, port clearance/turbulence, subsonic protection, panel modes, or thermal data. References: [enclosure knowledge](../../../docs/DESIGN_KNOWLEDGE_BASE.md#4-choose-and-model-the-bass-alignment).