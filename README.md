# AI Speaker Design Database

A source-indexed loudspeaker knowledge base, deterministic Python calculators, and
VS Code agent workflows for user-directed speaker design. This is a toolkit and
knowledge seed, not a bundled commercial driver catalog or an autonomous manufacturing system.

## What Is Included

- Driver T/S conversions, sealed/vented/passive-radiator/aperiodic small-signal models,
  complex impedance, excursion, port geometry, and estimated voltage ceilings.
- Measured FRD/ZMA import, phase and angle interpolation, microphone corrections,
  complex-impedance fitting, baffle diffraction, and ideal piston directivity.
- Passive multiway networks, two-way component search, active/DSP filters,
  acoustic summation, impedance phase, group delay, and coverage checks.
- A rebuildable JSON-to-SQLite knowledge base with equations, citations, assumptions,
  workflow stages, and documented limitations.
- Agent intake and specialist review workflows, a blank design brief, generated
  Markdown/LaTeX reports, optional PDF compilation, and input-hash manifests.
- A WinISD importer that preserves raw fields, source hashes, duplicate identities,
  SI parameters, and screening flags; no WinISD driver payloads are bundled.

## Quick Start

Python 3.10+ is required. Run commands from the repository root. SciPy is needed for
numerical fitting and filter routines.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -B -m scripts.system_design.speaker_knowledge_db build
python -B -m scripts.system_design.speaker_knowledge_db search "series resistance"
python -B -m unittest discover -s tests -p 'test_*.py' -v
```

On Linux/macOS activate with `source .venv/bin/activate` instead. The SQLite file is
generated locally and excluded from Git. Tests use synthetic fixtures and need no downloaded driver data.

## Agent-Assisted Design

Open the repository in VS Code with GitHub Copilot. Select **Speaker Design Engineer**
from the agent picker. Its four reviewers audit driver data, enclosure modeling,
acoustic systems, and build packages. On-demand procedures live in `.github/skills/`.

The agent must preserve user-selected drivers, prices, topology, and targets; it must
ask for missing inputs rather than invent measurements or silently substitute parts.
See [the intake guide](docs/DESIGN_PROMPT_TEMPLATE.md).

Create a local brief from the blank template, supply your own driver/measurement inputs,
and run:

```powershell
Copy-Item data/configs/design_brief_template.json data/configs/my_design_brief.json
python -B -m scripts.system_design.design_workflow data/configs/my_design_brief.json --output-dir data/results/my_design_package
```

The blank template intentionally reports missing inputs. A completed brief generates
build notes, reports, manifests, and available calculation CSVs. PDF output additionally
requires `pdflatex` or `tectonic`; generated plots and circuit schematics are not
automatically produced by this generic workflow. Outputs remain local and Git-ignored.

Readiness states are `NEEDS_INPUT`, `PROTOTYPE_ONLY`, and
`READY_FOR_PROTOTYPE_VALIDATION`. None constitutes certification or approval to manufacture.

## External Driver and Component Data

The Parts Express catalog is maintained separately:
**https://github.com/meowelectronics/parts-express-database**.
No catalog snapshots are copied into this repository.

To obtain a local copy without adding it to your project history:

```powershell
git clone https://github.com/meowelectronics/parts-express-database.git external/parts-express-database
New-Item -ItemType Directory -Force data/catalogs
Copy-Item external/parts-express-database/partsexpress_*.json data/catalogs/
```

Review source rights, dates, and units before using any dataset. Prices are snapshots,
not current quotes; USD values do not establish EUR budget compliance.

Import your own authorized WinISD files with:

```powershell
python -B -m scripts.catalog.import_winisd_drivers PATH_TO_WDR_DIRECTORY
```

The output is `data/catalogs/winisd_drivers.json`, excluded from Git. Quality flags
are screening aids, not measured validation. Zero/unknown fields, duplicated model
identities, and suspicious T/S relations require review before simulation.

An optional legacy Parts Express acquisition utility is retained for explicit use.
Prefer the separate data repository. Install its extra dependencies only if needed:
`python -m pip install -r requirements-data.txt` and `python -m playwright install chromium`.
Follow website terms, robots rules, and reasonable request limits; do not bypass access controls.

## Documentation and Provenance

- [Calculator guide](docs/CALCULATOR_GUIDE.md): commands, units, inputs, and model limits.
- [Design knowledge base](docs/DESIGN_KNOWLEDGE_BASE.md): equations and measurement gates.
- [Sources and retrieval status](docs/SOURCES.md): data, measurement, and algorithm links.
- [Complete recorded URL inventory](docs/FETCH_LINKS.json): source/product/resource URLs
  recovered from the originating workspace, including unsuccessful retrieval attempts.

The inventory records links, not third-party page contents. A listed URL is not proof
that it was fetched successfully or that its content is licensed for redistribution.

## Repository Boundaries

This clean project excludes personal speaker combinations, project configs/reports,
CAD, renders, PDFs, FRD/ZMA files, manufacturer meshes, WinISD datasets, downloaded
source archives, database binaries, local editor settings, and credentials. The
original working speaker project is separate and was not deleted or rewritten.

Scimpy and SpeakerSim are cited algorithm references; their source trees are not
vendored. External projects retain their own licenses. This repository does not
grant redistribution rights to external data or imply upstream endorsement. No
license has been selected for this project yet; public visibility alone does not
grant an open-source license.

## Limitations

The models are linear and small-signal. They do not certify distortion, thermal
compression, suspension/motor nonlinearity, port turbulence, PETG panel behavior,
room response, safe amplifier operation, or print geometry. Final crossover work
requires individual-driver measurements on the finished baffle with credible timing.
Sparse horizontal angles are not a full-sphere spinorama. Always build and measure a prototype.