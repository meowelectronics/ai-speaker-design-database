"""Generate an auditable speaker design report from a workflow package plan."""

import csv
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

from scripts.system_design.speaker_knowledge_db import DEFAULT_DATABASE, list_sources


def _latex_escape(value):
    replacements = {
        "\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$",
        "#": r"\#", "_": r"\_", "{": r"\{", "}": r"\}",
        "~": r"\textasciitilde{}", "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def _read_csv(path):
    path = Path(path)
    if not path.is_file():
        return []
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def _calculation_summaries(package_dir, generated):
    summaries = []
    for generated_path in generated:
        rows = _read_csv(Path(package_dir) / generated_path)
        summary = {"file": generated_path, "rows": len(rows)}
        if rows:
            for column, label in (("impedance_ohm", "minimum_impedance_ohm"),
                                  ("impedance_phase_deg", "maximum_abs_impedance_phase_deg"),
                                  ("cone_excursion_mm", "maximum_cone_excursion_mm"),
                                  ("radiator_excursion_mm", "maximum_radiator_excursion_mm"),
                                  ("port_velocity_m_s", "maximum_port_velocity_m_s")):
                values = []
                for row in rows:
                    try:
                        value = float(row[column])
                    except (KeyError, TypeError, ValueError):
                        continue
                    values.append(abs(value) if "phase" in column else value)
                if values:
                    summary[label] = min(values) if column == "impedance_ohm" else max(values)
            coverage_values = [row.get("measurement_covered", "").lower() == "true"
                               for row in rows if row.get("measurement_covered", "")]
            if coverage_values:
                summary["measurement_coverage_fraction"] = sum(coverage_values) / len(coverage_values)
        summaries.append(summary)
    return summaries


def _context_from_plan(plan, package_dir):
    return {
        "project_name": plan.get("project_name") or "Speaker Design",
        "status": plan.get("status", "NEEDS_INPUT"),
        "ways": plan.get("ways"),
        "target": plan.get("target", {}),
        "budget": plan.get("budget"),
        "drivers": plan.get("drivers", []),
        "box_design": plan.get("box_design"),
        "fabrication": plan.get("fabrication", {}),
        "fabrication_volume": plan.get("fabrication_volume"),
        "bill_of_materials": plan.get("bill_of_materials", []),
        "missing_inputs": plan.get("missing_inputs", []),
        "missing_measurements": plan.get("missing_measurements", []),
        "questions": plan.get("questions", []),
        "warnings": plan.get("warnings", []),
        "calculation_errors": plan.get("calculation_errors", []),
        "generated_calculations": plan.get("generated_calculations", []),
        "copied_configs": plan.get("copied_configs", {}),
        "input_manifest": plan.get("input_manifest", []),
        "calculation_summaries": _calculation_summaries(
            package_dir, plan.get("generated_calculations", [])
        ),
        "reference_sources": list_sources(DEFAULT_DATABASE) if DEFAULT_DATABASE.is_file() else [],
    }


def _format_value(value):
    if value is None or value == "":
        return "Not provided"
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, ensure_ascii=True)
    return str(value)


def _markdown(context):
    lines = [f"# {context['project_name']} - Design Report", "",
             f"**Readiness:** `{context['status']}`", "",
             "This is a deterministic calculation package, not a build certification. "
             "A READY status means inputs and measured coverage passed workflow gates; "
             "physical prototype verification is still required.", "",
             "## Design Targets", "",
             f"- Ways: {_format_value(context['ways'])}"]
    for key, label in (("low_hz", "Low frequency"), ("high_hz", "High frequency"),
                       ("target_spl_db", "Target SPL"), ("distance_m", "Listening distance"),
                       ("headroom_db", "Headroom"), ("use_case", "Use case"),
                       ("room_or_placement", "Room/placement")):
        if key in context["target"]:
            lines.append(f"- {label}: {_format_value(context['target'][key])}")
    budget = context.get("budget")
    lines.append(f"- User budget: {_format_value(budget) if budget else 'Not specified'}")
    lines.extend(("", "## User-Selected Drivers", ""))
    if context["drivers"]:
        lines.extend(("| Role | Driver | Part | Quantity | Wiring | Data source | User price |",
                  "|---|---|---|---:|---|---|---:|"))
        for driver in context["drivers"]:
            wiring = f"{driver.get('series', 1)}s{driver.get('parallel', driver.get('quantity', 1))}p"
            price = _format_value(driver.get("price"))
            lines.append("| " + " | ".join(_format_value(driver.get(key)) for key in
                         ("role", "name", "part_number", "quantity"))
                         + f" | {wiring} | {_format_value(driver.get('source'))} | {price} |")
    else:
        lines.append("No driver selections provided.")

    lines.extend(("", "## Enclosure and Fabrication", "",
                  f"- Enclosure model: {_format_value(context.get('box_design'))}",
                  f"- Fabrication inputs: {_format_value(context['fabrication'])}"))
    if context.get("fabrication_volume"):
        lines.append(f"- Derived rectangular volume: {_format_value(context['fabrication_volume'])}")
    lines.extend(("", "## User Bill of Materials", ""))
    if context["bill_of_materials"]:
        lines.extend(("| Quantity | User-selected item | User price | Notes |",
                  "|---:|---|---:|---|"))
        for item in context["bill_of_materials"]:
            lines.append("| " + " | ".join(_format_value(item.get(key)) for key in
                         ("quantity", "item", "price", "notes")) + " |")
    else:
        lines.append("No BOM supplied.")

    lines.extend(("", "## Calculation Results", ""))
    if context["calculation_summaries"]:
        for summary in context["calculation_summaries"]:
            lines.append(f"### `{summary['file']}`")
            lines.append("")
            for key, value in summary.items():
                if key != "file":
                    lines.append(f"- {key}: {_format_value(value)}")
            lines.append("")
    else:
        lines.append("No calculations were generated. Resolve the open inputs and rerun the workflow.")

    lines.extend(("## Readiness Gates", ""))
    for title, values in (("Missing user inputs", context["missing_inputs"]),
                          ("Missing measurements", context["missing_measurements"]),
                          ("Warnings", context["warnings"]),
                          ("Calculation errors", context["calculation_errors"])):
        lines.extend((f"### {title}", ""))
        lines.extend(f"- {item}" for item in values) if values else lines.append("- None recorded.")
        lines.append("")
    lines.extend(("## Provenance", "", "### Configs", ""))
    lines.extend(f"- {key}: `{value}`" for key, value in context["copied_configs"].items())
    lines.extend(("", "### Input files and SHA-256", ""))
    lines.extend(f"- `{item['path']}`: `{item['sha256']}`" for item in context["input_manifest"])
    lines.extend(("", "## Build/Measurement Notes", "",
                  "- Parts and prices are user supplied; no substitutions or catalog ranking were applied.",
                  "- Datasheet-derived values are not measurements. Consult the data-source label per driver.",
                  "- Check exact cutouts, clearances, net volume, port/PR tuning, wiring polarity, and component DCR/ESR before fabrication.",
                  "- Re-measure the prototype on its finished baffle and verify system impedance, response, excursion, noise, and thermal behavior.",
                  "- The linear model does not certify distortion, thermal compression, panel vibration, room response, or safety.", ""))
    lines.extend(("## Reference Sources", ""))
    for source in context["reference_sources"]:
        reference = f"[{source['source_id']}] {source['title']}"
        if source["uri"]:
            reference += f" ({source['uri']})"
        if source["citation"]:
            reference += f"; {source['citation']}"
        if source["notes"]:
            reference += f". {source['notes']}"
        lines.append(f"- {reference}")
    if not context["reference_sources"]:
        lines.append("- Local knowledge database unavailable; rebuild it to include the source registry.")
    lines.append("")
    return "\n".join(lines)


def _latex_table(headers, rows):
    width = 0.96 / max(1, len(headers))
    columns = "|".join([f"p{{{width:.3f}\\linewidth}}"] * len(headers))
    lines = [f"\\begin{{longtable}}{{{columns}}}", "\\toprule",
             " & ".join(_latex_escape(header) for header in headers) + r" \\",
             "\\midrule", "\\endfirsthead", "\\toprule",
             " & ".join(_latex_escape(header) for header in headers) + r" \\",
             "\\midrule", "\\endhead"]
    for row in rows:
        lines.append(" & ".join(_latex_escape(_format_value(value)) for value in row) + r" \\")
    lines.extend(("\\bottomrule", "\\end{longtable}"))
    return "\n".join(lines)


def _latex(context):
    driver_rows = [[driver.get("role"), driver.get("name"), driver.get("part_number"),
                    driver.get("quantity"), driver.get("source"), driver.get("price")]
                   for driver in context["drivers"]]
    bom_rows = [[item.get("quantity"), item.get("item"), item.get("price"), item.get("notes")]
                for item in context["bill_of_materials"]]
    summary_rows = [[summary["file"], key, value]
                    for summary in context["calculation_summaries"]
                    for key, value in summary.items() if key != "file"]
    provenance_rows = [[item["path"], item["sha256"]] for item in context["input_manifest"]]
    sections = [
        r"\documentclass[11pt]{article}",
        r"\usepackage[margin=22mm]{geometry}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{booktabs,longtable,array,hyperref,xcolor}",
        r"\title{" + _latex_escape(context["project_name"]) + r" -- Speaker Design Report}",
        r"\date{\today}", r"\begin{document}", r"\maketitle",
        r"\section*{Readiness}", _latex_escape(context["status"]),
        r"\par This report summarizes deterministic calculations and user-provided data. It is not a build, safety, thermal, or listening certification.",
        r"\section{Targets}",
        _latex_escape(json.dumps(context["target"], sort_keys=True, ensure_ascii=True)),
        r"\par Ways: " + _latex_escape(context["ways"]),
        r"\par Budget: " + _latex_escape(_format_value(context.get("budget"))),
        r"\section{User-selected drivers}",
        _latex_table(["Role", "Driver", "Part", "Qty", "Source", "User price"], driver_rows)
        if driver_rows else "No driver selections provided.",
        r"\section{Enclosure and fabrication}",
        _latex_escape(_format_value(context.get("box_design"))), r"\par",
        _latex_escape(_format_value(context["fabrication"])),
        r"\par Derived volume: " + _latex_escape(_format_value(context.get("fabrication_volume"))),
        r"\section{User bill of materials}",
        _latex_table(["Qty", "User-selected item", "User price", "Notes"], bom_rows)
        if bom_rows else "No BOM supplied.",
        r"\section{Calculation results}",
        _latex_table(["File", "Metric", "Value"], summary_rows)
        if summary_rows else "No calculations were generated.",
        r"\section{Open gates and warnings}",
    ]
    for label, values in (("Missing inputs", context["missing_inputs"]),
                          ("Missing measurements", context["missing_measurements"]),
                          ("Warnings", context["warnings"]),
                          ("Calculation errors", context["calculation_errors"])):
        sections.append(r"\subsection{" + _latex_escape(label) + "}")
        sections.append(r"\begin{itemize}")
        sections.extend(r"\item " + _latex_escape(item) for item in values)
        if not values:
            sections.append(r"\item None recorded.")
        sections.append(r"\end{itemize}")
    sections.extend((r"\section{Input provenance}",
                     _latex_table(["Input file", "SHA-256"], provenance_rows)
                     if provenance_rows else "No source files were recorded.",
                     r"\section{Reference sources}"))
    sections.extend(r"\paragraph{" + _latex_escape(source["source_id"]) + "} "
                    + _latex_escape(source["title"] + ". " + source["citation"] + ". " + source["notes"])
                    for source in context["reference_sources"])
    sections.extend((
                     r"\section{Build and measurement checks}",
                     r"\begin{itemize}",
                     r"\item Verify physical cutouts, clearances, gross/net volume, seals, and wiring before fabrication.",
                     r"\item Re-measure finished-baffle response, complex impedance, directivity, excursion/noise, and component heating.",
                     r"\item Linear models do not certify nonlinear distortion, thermal compression, room response, panel vibration, or safety.",
                     r"\end{itemize}", r"\end{document}"))
    return "\n".join(sections) + "\n"


def generate_report(plan, package_dir):
    """Generate Markdown/LaTeX and optional PDF; delete temporary serialized context on exit."""
    package_dir = Path(package_dir)
    package_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="speaker-report-context-") as temporary:
        context_path = Path(temporary) / "report_context.json"
        context_path.write_text(json.dumps(_context_from_plan(plan, package_dir),
                                           ensure_ascii=True, sort_keys=True), encoding="utf-8")
        context = json.loads(context_path.read_text(encoding="utf-8"))
        markdown_path = package_dir / "design_report.md"
        latex_path = package_dir / "design_report.tex"
        markdown_path.write_text(_markdown(context), encoding="utf-8")
        latex_path.write_text(_latex(context), encoding="utf-8")

        pdf_path = package_dir / "design_report.pdf"
        engine = shutil.which("pdflatex") or shutil.which("tectonic")
        pdf_generated = False
        pdf_error = None
        if engine:
            compile_dir = Path(temporary) / "latex"
            compile_dir.mkdir()
            source_copy = compile_dir / latex_path.name
            source_copy.write_text(latex_path.read_text(encoding="utf-8"), encoding="utf-8")
            command = ([engine, "-interaction=nonstopmode", "-halt-on-error", source_copy.name]
                       if Path(engine).name.lower().startswith("pdf")
                       else [engine, "--outdir", str(compile_dir), source_copy.name])
            try:
                subprocess.run(command, cwd=compile_dir, check=True,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                built_pdf = compile_dir / "design_report.pdf"
                if built_pdf.is_file():
                    shutil.copyfile(built_pdf, pdf_path)
                    pdf_generated = True
            except (OSError, subprocess.CalledProcessError) as error:
                pdf_error = str(error)

    return {
        "markdown": markdown_path.name,
        "latex": latex_path.name,
        "pdf": pdf_path.name if pdf_generated else None,
        "pdf_engine_available": bool(engine),
        "pdf_error": pdf_error,
        "temporary_context_removed": not context_path.exists(),
    }