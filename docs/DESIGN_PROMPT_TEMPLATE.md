# Beginner Design Intake

Use this as the natural-language prompt for describing a speaker project. The prompt is
normalized into `data/configs/design_brief_template.json`; calculations after that use the
normalized fields deterministically. The user owns the topology, all driver/part selections,
prices/currency, budget, enclosure constraints, and supplier preferences. No catalogue
ranking, substitution, or price cap is imposed.

```text
Design a [number]-way [passive/active] speaker for [use case and placement].

Targets:
- Low and high frequency: [Hz]
- Maximum/desired SPL at [distance] m: [dB]
- Desired headroom or use level: [dB / description]
- Room/placement: [free-standing, desktop, near wall, room dimensions if known]
- Budget and currency: [optional user limit; informational, not an automatic parts filter]

I choose these drivers and prices:
- Way/role: [manufacturer, exact model/part number, quantity, price/currency]
- For multiple identical drivers on one way, give series and parallel wiring counts; their product must equal quantity.
- Way/role: [manufacturer, exact model/part number, quantity, price/currency]
- Add rows for every way.
- T/S source for each driver: [datasheet values / my measured values / component measurements / fitted impedance JSON]
- Attach or identify FRD, ZMA, and calibration data if available.

Enclosure:
- User-selected alignment and the driver role to model in that box: [sealed / vented / passive radiator / aperiodic; e.g. woofer]
- Geometry type: [rectangular / tapered / custom]
- Net volume in litres, or rectangular external dimensions, wall thickness, and named displacement ledger: [values and units]
- For non-rectangular geometry, provide CAD-calculated net volume and the geometry/model reference.
- For a vent, provide tuning and area; for a PR, provide model and T/S values.
- User-authored enclosure/system config paths, if already available: [paths]
- Passive or active/DSP: [choice]
- Available parts / amplifier / impedance floor: [details]
- On-baffle FRD/ZMA and measured angles available: [yes/no; file names]

Build constraints:
- Budget and currency: [user value]
- Required BOM or preferred suppliers: [details]
- Tools and construction method: [details]

Do not invent missing prices or measurements. List unknowns as questions, distinguish
datasheet predictions from measured results, and do not call a design build-ready until
the acoustic measurements, fabrication dimensions, user BOM, and impedance/excursion checks
are present. Budget and BOM price are optional and always user-provided.
```

## Deterministic Package

After the prompt has been normalized into JSON, run:

```powershell
python -B -m scripts.system_design.design_workflow data/configs/my_design_brief.json `
  --output-dir data/results/my_design_package
```

The package contains `design_plan.json`, `BUILD_NOTES.md`, an extensive `design_report.md`
and `design_report.tex` (plus `design_report.pdf` when `pdflatex` or `tectonic` is installed),
`manifest.json`, a copy of the normalized brief and supplied calculation configs, plus hashes/paths for referenced
measurement files. The report includes input provenance, calculation summaries, open gates,
and the local source bibliography. A serialized report-context JSON is held only in a
temporary directory and removed after report generation. FRD/ZMA/calibration files are not bundled, so the package is not portable
unless you retain/copy those inputs separately. It includes calculation CSVs for the
enclosure and measured system when those config files are supplied. The readiness states
are:

- `NEEDS_INPUT`: required user choices, fabrication details, or a valid enclosure config are missing.
- `PROTOTYPE_ONLY`: a box calculation can run, but measured on-baffle FRD/ZMA, alignment, or a system config is missing.
- `READY_FOR_PROTOTYPE_VALIDATION`: the required user brief, fabrication/BOM, measurement metadata, a successful measured-system calculation, and full requested FRD/ZMA frequency/angle coverage are present. BOM prices are optional. This still means build and verify the prototype; it is not a certification.

Measurement metadata (on-baffle status, drive voltage, distance, timing reference, and mic
orientation) is user-reported context, not automatically verified by software. Readiness is
promoted only after the configured measured-system simulation runs and every exported row
is covered by the source FRD/ZMA frequency ranges; requested missing angles or incomplete
coverage keep the package at `PROTOTYPE_ONLY`.

`ways` is any positive integer. Driver names, models, sources, quantities, and prices come
from the user brief. Catalogues are optional reference data; the workflow does not impose
the workspace's historic driver sizes, budget, or candidate parts. A `box_design` object can
be supplied directly (`kind`, `volume_m3`, and the appropriate tuning/port/PR values); if
`enclosure_config` is provided instead, that selected config is used unchanged. Optional
`system_design` embeds the user-authored measured-system config; otherwise `system_config`
points to one. Box and system calculations run from these explicit inputs, never from hidden
recommendation defaults.