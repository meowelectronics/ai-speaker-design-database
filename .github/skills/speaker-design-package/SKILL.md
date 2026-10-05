---
name: speaker-design-package
description: "Run, inspect, or update the universal deterministic speaker-design package from a user-owned JSON brief. Use for missing-input questions, readiness, manifests, calculation output, or reproducibility."
argument-hint: "Brief JSON and output directory"
---

# Design Package

1. Validate schema, exact user-selected driver mapping, source-specific T/S, enclosure/fabrication, BOM, and measurement metadata.
2. Run `python -B -m scripts.system_design.design_workflow BRIEF.json --output-dir PACKAGE`.
3. Inspect `design_plan.json`, `BUILD_NOTES.md`, `design_report.md`, `design_report.tex` (and PDF if generated), `manifest.json`, copied configs, and all generated CSVs.
4. Explain each `NEEDS_INPUT`, `PROTOTYPE_ONLY`, or `READY_FOR_PROTOTYPE_VALIDATION` state by naming its exact gate. READY is not physical certification.
5. Preserve the user’s part choices/prices; never insert catalog recommendations or substitute BOM entries.

If a calculation fails, report its specific error in the package and resolve the responsible input/config. Do not report readiness from the assessment alone; measured-system execution and full requested FRD/ZMA coverage must pass.