---
name: speaker-brief-intake
description: "Normalize a beginner's speaker-design prompt into the universal JSON brief. Use for goals, topology, user-selected drivers/prices, enclosure/fabrication constraints, budget, or when design_workflow reports missing inputs. Never choose parts for the user."
argument-hint: "Speaker goals, selected parts, measurements, and build constraints"
---

# Speaker Brief Intake

Use before calculations when the user gives a natural-language speaker request.

## Procedure

1. Read [design_brief_template.json](../../../data/configs/design_brief_template.json) and [DESIGN_PROMPT_TEMPLATE.md](../../../docs/DESIGN_PROMPT_TEMPLATE.md).
2. Preserve user-selected driver names/part numbers, quantity, series/parallel wiring, prices/currency, topology, and enclosure preferences verbatim.
3. Normalize targets, units, T/S source, user BOM, fabrication dimensions/displacement, measurement files, and measurement metadata into schema v1.
4. Ask only for missing or ambiguous values. Do not infer a driver, price, volume, T/S value, cutout, or measurement condition.
5. Validate the brief with `assess_brief()` or run `python -B -m scripts.system_design.design_workflow BRIEF.json --output-dir PACKAGE`.

## Output

Return the normalized brief, unresolved fields/questions, and whether the result is `NEEDS_INPUT`, `PROTOTYPE_ONLY`, or ready for prototype validation. Budget and price are user-owned and never an automatic candidate filter.