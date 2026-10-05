# Calculator Guide

Run module commands from the repository root. Install `requirements.txt` first.
All design data and measurements must be supplied locally; no real-driver example
or project-specific crossover is bundled.

## Entry Points

| Command | Function |
|---|---|
| `python -B -m scripts.enclosure.calculate_box CONFIG.json` | Enclosure response, complex impedance, group delay, cone/PR excursion, and port geometry |
| `python -B -m scripts.system_design.calculate_system CONFIG.json` | Measured multiway passive/active system, summed response, angular curves, and input impedance |
| `python -B -m scripts.measurement.impedance_fit --help` | Fit electrical/mechanical components to phase-bearing complex ZMA |
| `python -B -m scripts.system_design.design_workflow BRIEF.json --output-dir PACKAGE` | Validate user brief and generate reports, calculation CSVs, and provenance manifest |
| `python -B -m scripts.system_design.speaker_knowledge_db build` | Rebuild the local SQLite knowledge index from the JSON seed |
| `python -B -m scripts.catalog.import_winisd_drivers DIRECTORY` | Import authorized local WDR records into an ignored catalog |

## Input Units and Driver Sources

Core models use SI: ohms, henries, kilograms, tesla-metres, metres/newton,
newton-seconds/metre, square metres, metres, cubic metres, and hertz. JSON boundary
fields include explicit suffixes such as `_mH`, `_uF`, `_mm`, and `_ohm`.

Enclosure driver sources are `datasheet_ts`, `measured_ts`, `components`, or
`fitted_json`. Composite T/S input requires Fs, Qes, Qms, Re, Vas, and Sd; optional
Le/Xmax/power limits can refine the model. Direct components require Re, Le, BL,
Mms, Cms, Rms, and Sd. Values reconstructed from rounded T/S are derived, not measured.

Use net enclosure volume after driver, port/PR, crossover, and bracing displacement.
For PRs supply Mms, Cms, Rms, Sd, Xmax when known, and added mass. Vented models require
tuning and area; verify end correction and clearance rather than transferring a
round-port assumption to slots or flares.

## FRD/ZMA and Crossover

FRD contains frequency, SPL magnitude, and phase; ZMA contains frequency, electrical
impedance magnitude, and phase. Each measured branch accepts explicit `frd_files`
and `zma_file` paths, or a folder with `FRD/{stem}@{angle}.frd` and
`ZMA/{stem}.zma`. Use individual drivers on the final baffle, not whole-speaker traces.

The two-way config uses `woofer`, `tweeter`, `crossover`, and `simulation` objects.
The multiway alternative uses `branches`, with per-branch passive filters, custom
R/L/C networks, polarity, offset, and optional active filter chains. Inspect
`calculate_system.py` for accepted config keys. Inductor DCR and explicit component
ESR are losses, not inductance/capacitance corrections. Preserve the actual source
voltage, acoustic offset, timing reference, and polarity.

A two-way `search` section can rank supplied component values by response smoothness
subject to an impedance floor; it is not a driver chooser or automatic budget optimizer.
The CSV exports summed and branch levels, phase, input impedance magnitude/phase,
group delay, and frequency coverage. Requested unavailable angles must not be
silently dropped. Sparse horizontal samples are not full-sphere sound power.

When REW already applied microphone calibration, do not apply it again. The optional
calibration file is an additive SPL correction for uncorrected imports and must cover
the entire source FRD range. Gating, nearfield splicing, and acoustic time alignment
remain measurement tasks outside this CLI.

## Output and Verification

Workflow output includes `design_plan.json`, `BUILD_NOTES.md`, `design_report.md`,
`design_report.tex`, manifests, copied configs, and available calculation CSVs. A TeX
compiler is needed for PDF. Charts and circuit drawings are not generated automatically.
Measurement payloads are hashed but not bundled; reports are not automatically portable.

Readiness is gated on explicit inputs, real system calculation success, measurement
metadata, and full requested coverage. `READY_FOR_PROTOTYPE_VALIDATION` still requires
physical measurements. Linear calculations exclude distortion, thermal compression,
port turbulence, panel vibration, room response, and manufacturing clearance.