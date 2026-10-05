"""Run a user-directed, deterministic speaker-design workflow from a normalized brief."""

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil

from scripts.enclosure.calculate_box import run as run_box
from scripts.measurement.response_data import MeasurementCoverageError
from scripts.project_paths import ROOT
from scripts.system_design.calculate_system import run as run_system
from scripts.system_design.design_report import generate_report


DRIVER_SOURCES = {"datasheet_ts", "measured_ts", "components", "fitted_json"}
TARGET_FIELDS = ("low_hz", "high_hz", "target_spl_db", "distance_m")
MEASUREMENT_METADATA_FIELDS = ("on_baffle", "measurement_voltage_v", "reference_distance_m",
                               "time_reference", "microphone_orientation_degrees")


def _resolve(path):
    candidate = Path(path)
    return candidate if candidate.is_absolute() else ROOT / candidate


def _system_branches(config):
    if isinstance(config.get("branches"), list):
        return config["branches"]
    if config.get("woofer") and config.get("tweeter"):
        return [config["woofer"], config["tweeter"]]
    return []


def _driver_mapping_issues(drivers, branches, ways, label):
    issues = []
    if len(branches) != ways:
        return [f"{label} has {len(branches)} branches but the brief specifies {ways} ways."]
    for index, (driver, branch) in enumerate(zip(drivers, branches)):
        expected = driver.get("part_number") or driver.get("name")
        configured = branch.get("part_number") or branch.get("driver_name")
        if not configured:
            issues.append(f"{label} branch {index + 1} needs part_number or driver_name to bind it to the selected driver.")
        elif configured != expected:
            issues.append(f"{label} branch {index + 1} selects {configured}, but the brief selects {expected}.")
    return issues


def _driver_data_issues(index, driver):
    source = driver.get("source")
    if source == "fitted_json":
        path = _resolve(driver.get("fit_json", ""))
        if not path.is_file():
            return [f"drivers[{index}].fit_json"]
        try:
            fit = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return [f"drivers[{index}].fit_json_invalid"]
        params = fit.get("driver", fit) if isinstance(fit, dict) else {}
        required = ("re", "le", "bl", "mms", "cms", "rms", "sd")
        if any(not isinstance(params.get(key), (int, float)) or isinstance(params.get(key), bool)
               or not math.isfinite(params[key]) for key in required):
            return [f"drivers[{index}].fit_json_parameters"]
        return []
    required = {
        "datasheet_ts": ("fs_hz", "qes", "qms", "re_ohm", "vas_m3", "sd_m2"),
        "measured_ts": ("fs_hz", "qes", "qms", "re_ohm", "vas_m3", "sd_m2"),
        "components": ("re_ohm", "le_h", "bl_tm", "mms_kg", "cms_m_n", "rms_ns_m", "sd_m2"),
    }.get(source, ())
    issues = []
    for field in required:
        value = driver.get(field)
        if (not isinstance(value, (int, float)) or isinstance(value, bool)
                or not math.isfinite(value) or value <= 0):
            issues.append(f"drivers[{index}].{field}")
    for field in ("le_h",):
        value = driver.get(field)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                  or not math.isfinite(value) or value < 0):
            issues.append(f"drivers[{index}].{field}")
    for field in ("xmax_m", "power_handling_w"):
        value = driver.get(field)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool)
                                  or not math.isfinite(value) or value <= 0):
            issues.append(f"drivers[{index}].{field}")
    return issues


def _measurement_metadata_gaps(metadata):
    if not isinstance(metadata, dict):
        metadata = {}
    gaps = []
    if metadata.get("on_baffle") is not True:
        gaps.append("measurement_metadata.on_baffle")
    for field in ("measurement_voltage_v", "reference_distance_m", "microphone_orientation_degrees"):
        value = metadata.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            gaps.append(f"measurement_metadata.{field}")
        elif field != "microphone_orientation_degrees" and value <= 0:
            gaps.append(f"measurement_metadata.{field}")
    if not isinstance(metadata.get("time_reference"), str) or not metadata["time_reference"].strip():
        gaps.append("measurement_metadata.time_reference")
    return gaps


def _rectangular_volume(fabrication):
    dimensions = fabrication.get("external_dimensions_mm")
    wall = fabrication.get("wall_thickness_mm")
    displacement = fabrication.get("displacements_l")
    if (fabrication.get("geometry_type") != "rectangular"
            or not isinstance(dimensions, list) or len(dimensions) != 3
            or not isinstance(wall, (int, float)) or wall <= 0
            or not isinstance(displacement, dict) or not displacement):
        return None
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0
           for value in dimensions):
        return None
    if any(not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0
           for value in displacement.values()):
        return None
    internal = [dimension - 2 * wall for dimension in dimensions]
    if min(internal) <= 0:
        return None
    gross_l = math.prod(internal) / 1e6
    displaced_l = sum(displacement.values())
    net_l = gross_l - displaced_l
    if net_l <= 0:
        return None
    return {"internal_dimensions_mm": internal, "gross_volume_l": gross_l,
            "displacement_total_l": displaced_l, "net_volume_l": net_l,
            "assumption": "Rectangular internal cavity; displacement ledger supplied by user."}


def _system_measurement_paths(config):
    paths = []
    driver_configs = config.get("branches") or [config.get("woofer", {}), config.get("tweeter", {})]
    for driver in driver_configs:
        if "frd_files" in driver:
            paths.extend(_resolve(path) for path in driver["frd_files"].values())
            if driver.get("zma_file"):
                paths.append(_resolve(driver["zma_file"]))
        elif driver.get("folder") and driver.get("stem"):
            folder, stem = _resolve(driver["folder"]), driver["stem"]
            for angle in config.get("angles_degrees", [0, 15, 30, 45]):
                measured = folder / "FRD" / f"{stem}@{angle}.frd"
                if measured.is_file():
                    paths.append(measured)
            impedance = folder / "ZMA" / f"{stem}.zma"
            if impedance.is_file():
                paths.append(impedance)
    if config.get("microphone_calibration_file"):
        paths.append(_resolve(config["microphone_calibration_file"]))
    return paths


def _sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _input_manifest(brief_path, brief):
    paths = [brief_path]
    for key in ("enclosure_config", "system_config"):
        if brief.get(key):
            source = _resolve(brief[key])
            if source.is_file():
                paths.append(source)
                if key == "system_config":
                    try:
                        system = json.loads(source.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        system = None
                    if isinstance(system, dict):
                        paths.extend(path for path in _system_measurement_paths(system)
                                     if path.is_file())
    if isinstance(brief.get("system_design"), dict):
        paths.extend(path for path in _system_measurement_paths(brief["system_design"])
                     if path.is_file())
    for driver in brief.get("drivers", []):
        if isinstance(driver, dict) and driver.get("source") == "fitted_json" and driver.get("fit_json"):
            source = _resolve(driver["fit_json"])
            if source.is_file():
                paths.append(source)
    unique = sorted({path.resolve() for path in paths}, key=lambda path: str(path).lower())
    return [{"path": str(path), "sha256": _sha256(path)} for path in unique if path.is_file()]


def _measured_coverage(csv_path):
    with Path(csv_path).open(newline="", encoding="utf-8") as source:
        rows = list(csv.DictReader(source))
    if not rows or "measurement_covered" not in rows[0]:
        return 0.0
    return sum(row["measurement_covered"].strip().lower() == "true" for row in rows) / len(rows)


def assess_brief(brief):
    """Validate user-selected design inputs without choosing drivers or imposing prices."""
    missing_inputs, questions, warnings = [], [], []
    if not isinstance(brief, dict):
        return {
            "schema_version": 1,
            "project_name": None,
            "status": "NEEDS_INPUT",
            "ways": None,
            "target": {},
            "drivers": [],
            "missing_inputs": ["brief_object"],
            "missing_measurements": [],
            "questions": ["Provide the design brief as a JSON object."],
            "warnings": [],
            "stages": [],
            "enclosure_config": None,
            "system_config": None,
            "fabrication": {},
            "bill_of_materials": [],
        }
    if brief.get("schema_version") != 1:
        missing_inputs.append("schema_version")
        questions.append("Use design brief schema_version 1.")
    project_name = brief.get("project_name")
    if not isinstance(project_name, str) or not project_name.strip():
        missing_inputs.append("project_name")
        questions.append("What should this project be called?")

    ways = brief.get("ways")
    if type(ways) is not int or ways < 1:
        missing_inputs.append("ways")
        questions.append("How many independently filtered driver ways will the speaker use?")

    target = brief.get("target", {})
    if not isinstance(target, dict):
        target = {}
        missing_inputs.append("target")
        questions.append("Provide target values as a JSON object.")
    for field in TARGET_FIELDS:
        value = target.get(field)
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            missing_inputs.append(f"target.{field}")
    if any(f"target.{field}" in missing_inputs for field in TARGET_FIELDS):
        questions.append("Provide target low/high frequency, SPL, and listening distance.")
    elif target["low_hz"] <= 0 or target["high_hz"] <= target["low_hz"] or target["distance_m"] <= 0:
        missing_inputs.append("target.valid_ranges")
        questions.append("Correct the frequency band and listening distance to positive values.")

    drivers = brief.get("drivers", [])
    if not isinstance(drivers, list) or len(drivers) != (ways if isinstance(ways, int) else 1):
        missing_inputs.append("drivers")
        questions.append("Provide exactly one user-selected driver record per way; arrays use quantity/wiring fields.")
        drivers = drivers if isinstance(drivers, list) else []
    part_ids = []
    for index, driver in enumerate(drivers):
        if not isinstance(driver, dict):
            missing_inputs.append(f"drivers[{index}].name")
            questions.append(f"Enter a manufacturer/model name for driver {index + 1}.")
            continue
        if not driver.get("name"):
            missing_inputs.append(f"drivers[{index}].name")
            questions.append(f"Enter a manufacturer/model name for driver {index + 1}.")
        if driver.get("source") not in DRIVER_SOURCES:
            missing_inputs.append(f"drivers[{index}].source")
            questions.append(
                f"Choose a T/S source for {driver['name']}: datasheet_ts, measured_ts, components, or fitted_json."
            )
        else:
            source_fields = {
                "datasheet_ts": ("fs_hz", "qes", "qms", "re_ohm", "vas_m3", "sd_m2"),
                "measured_ts": ("fs_hz", "qes", "qms", "re_ohm", "vas_m3", "sd_m2"),
                "components": ("re_ohm", "le_h", "bl_tm", "mms_kg", "cms_m_n", "rms_ns_m", "sd_m2"),
                "fitted_json": ("fit_json",),
            }
            for field in source_fields[driver["source"]]:
                if field not in driver or driver[field] in (None, ""):
                    missing_inputs.append(f"drivers[{index}].{field}")
            missing_driver_fields = [field for field in source_fields[driver["source"]]
                                     if field not in driver or driver[field] in (None, "")]
            if missing_driver_fields:
                questions.append(
                    f"Enter {', '.join(missing_driver_fields)} for {driver.get('name') or f'driver {index + 1}'} "
                    f"to use its {driver['source']} data source."
                )
            if driver["source"] == "fitted_json" and driver.get("fit_json"):
                if not _resolve(driver["fit_json"]).is_file():
                    missing_inputs.append(f"drivers[{index}].fit_json")
            missing_inputs.extend(_driver_data_issues(index, driver))
        if driver.get("part_number"):
            part_ids.append(driver["part_number"])
        quantity = driver.get("quantity")
        series = driver.get("series")
        parallel = driver.get("parallel")
        if (type(quantity) is not int or quantity < 1 or type(series) is not int
                or type(parallel) is not int or series < 1 or parallel < 1
                or series * parallel != quantity):
            missing_inputs.append(f"drivers[{index}].wiring")
            questions.append(
                f"Specify physical quantity and series/parallel counts for {driver.get('name') or f'driver {index + 1}'} "
                "whose product equals its quantity."
            )
        if not driver.get("role"):
            missing_inputs.append(f"drivers[{index}].role")
            questions.append(f"Assign a design role to {driver.get('name') or f'driver {index + 1}'} (for example low, mid, or high).")
    if len(part_ids) != len(set(part_ids)):
        warnings.append("Repeated part numbers detected; confirm that duplicated drivers are intentional.")

    budget = brief.get("budget")
    if budget is not None:
        if not isinstance(budget, dict):
            missing_inputs.append("budget")
            questions.append("Budget must be an object with amount and currency, or omitted.")
        elif budget.get("amount") in (None, "") and not budget.get("currency"):
            budget = None
        elif (not isinstance(budget.get("amount"), (int, float))
              or isinstance(budget.get("amount"), bool)
              or not math.isfinite(budget["amount"]) or budget["amount"] < 0
              or not budget.get("currency")):
            missing_inputs.append("budget")
            questions.append("If specifying a budget, provide a nonnegative amount and currency; it will not drive part selection.")

    enclosure_config = brief.get("enclosure_config")
    box_design = brief.get("box_design")
    if not enclosure_config and box_design is None:
        missing_inputs.append("box_design")
        questions.append("Choose an enclosure alignment and provide its net volume/tuning/port or PR inputs.")
    elif enclosure_config and not _resolve(enclosure_config).is_file():
        missing_inputs.append("enclosure_config_file")
        questions.append(f"Enclosure config not found: {enclosure_config}")
    elif enclosure_config and _resolve(enclosure_config).is_file():
        try:
            enclosure_file = json.loads(_resolve(enclosure_config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            enclosure_file = None
            missing_inputs.append("enclosure_config_json")
            questions.append("Enclosure config must be valid JSON before its driver can be checked.")
        box_role = enclosure_file.get("driver_role") if isinstance(enclosure_file, dict) else None
        selected_box_driver = next((driver for driver in drivers
                                    if isinstance(driver, dict) and driver.get("role") == box_role), None)
        if not box_role or selected_box_driver is None:
            missing_inputs.append("enclosure_config.driver_role")
            questions.append("Declare driver_role in the enclosure config and match it to a selected brief driver role.")
            selected_box_driver = {}
        box_driver = enclosure_file.get("driver", {}) if isinstance(enclosure_file, dict) else {}
        expected_id = selected_box_driver.get("part_number") or selected_box_driver.get("name")
        actual_id = box_driver.get("part_number") or box_driver.get("name")
        if selected_box_driver and not actual_id:
            missing_inputs.append("enclosure_config.driver_identity")
            questions.append("Add the enclosure config driver's part_number or exact name to verify it matches your selected driver role.")
        elif selected_box_driver and actual_id != expected_id:
            missing_inputs.append("enclosure_config.driver_mismatch")
            questions.append(f"Enclosure config uses {actual_id}; the brief selected {expected_id}.")
    elif box_design is not None and not isinstance(box_design, dict):
        missing_inputs.append("box_design")
        questions.append("Provide box_design as a JSON object.")
    elif isinstance(box_design, dict):
        box_role = box_design.get("driver_role")
        if not box_role or not any(isinstance(driver, dict) and driver.get("role") == box_role
                       for driver in drivers):
            missing_inputs.append("box_design.driver_role")
            questions.append("Select which user-defined driver role drives the enclosure model.")
        if box_design.get("kind") not in {"sealed", "vented", "aperiodic", "pr"}:
            missing_inputs.append("box_design.kind")
            questions.append("Select sealed, vented, aperiodic, or passive-radiator alignment.")
        if box_design.get("volume_m3") is not None and (
            not isinstance(box_design["volume_m3"], (int, float))
            or not math.isfinite(box_design["volume_m3"])
            or box_design["volume_m3"] <= 0
        ):
            missing_inputs.append("box_design.volume_m3")
            questions.append("Net enclosure volume must be a positive cubic-metre value.")
        if box_design.get("kind") in {"vented", "aperiodic"} and not all(
            box_design.get(key) for key in ("tuning_hz", "port_area_m2")
        ):
            missing_inputs.append("box_design.port")
            questions.append("Vented designs require tuning frequency and total port area.")
        if box_design.get("kind") == "pr" and not all(
            box_design.get(key) for key in ("tuning_hz", "radiator")
        ):
            missing_inputs.append("box_design.radiator")
            questions.append("Passive-radiator designs require user-selected PR parameters and tuning.")
        if box_design.get("kind") == "pr" and isinstance(box_design.get("radiator"), dict):
            for field in ("mms", "cms", "rms", "sd"):
                if box_design["radiator"].get(field) is None:
                    missing_inputs.append(f"box_design.radiator.{field}")

    fabrication = brief.get("fabrication", {})
    if not isinstance(fabrication, dict):
        fabrication = {}
        missing_inputs.append("fabrication")
        questions.append("Provide fabrication details as a JSON object.")
    dimensions = fabrication.get("external_dimensions_mm")
    geometry_type = fabrication.get("geometry_type")
    dimensions_valid = (isinstance(dimensions, list) and len(dimensions) == 3 and all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        and math.isfinite(value) and value > 0 for value in dimensions
    ))
    if geometry_type not in {"rectangular", "tapered", "custom"}:
        missing_inputs.append("fabrication.geometry_type")
        questions.append("Choose rectangular, tapered, or custom fabrication geometry.")
    if geometry_type == "rectangular" and not dimensions_valid:
        missing_inputs.append("fabrication.external_dimensions_mm")
        questions.append("Provide external width, height, and depth in millimetres for a rectangular cabinet.")
    if geometry_type != "rectangular" and not (
        fabrication.get("geometry_reference") or fabrication.get("cad_model")
    ):
        missing_inputs.append("fabrication.geometry_reference")
        questions.append("Provide a CAD model/path or geometry description for tapered/custom fabrication.")
    volume_calculation = _rectangular_volume(fabrication)
    net_volume = fabrication.get("net_volume_l")
    if (not isinstance(net_volume, (int, float)) or not math.isfinite(net_volume)
            or net_volume <= 0):
        if volume_calculation:
            net_volume = volume_calculation["net_volume_l"]
            fabrication = {**fabrication, "calculated_volume": volume_calculation}
        else:
            missing_inputs.append("fabrication.net_volume_l")
            questions.append("Provide net volume, or rectangular dimensions plus wall thickness and displacement_l ledger.")
    elif volume_calculation and abs(net_volume - volume_calculation["net_volume_l"]) / net_volume > 0.02:
        warnings.append("Entered net volume differs by over 2% from the rectangular displacement-ledger estimate.")
    if (isinstance(box_design, dict) and isinstance(box_design.get("volume_m3"), (int, float))
            and isinstance(net_volume, (int, float)) and net_volume > 0
            and abs(box_design["volume_m3"] * 1000 - net_volume) / net_volume > 0.02):
        warnings.append("Box-model net volume differs by over 2% from fabrication net volume.")
    if isinstance(box_design, dict) and box_design.get("volume_m3") is None:
        if isinstance(net_volume, (int, float)) and net_volume > 0:
            box_design = {**box_design, "volume_m3": net_volume / 1000}
        else:
            missing_inputs.append("box_design.volume_m3")
            questions.append("Provide net box volume or enough rectangular geometry/displacement data to derive it.")
    if not fabrication.get("cutouts"):
        missing_inputs.append("fabrication.cutouts")
        questions.append("Provide user-selected driver/port cutouts and center locations.")
    if not fabrication.get("material"):
        missing_inputs.append("fabrication.material")
        questions.append("Specify the enclosure material and construction method.")
    wall = fabrication.get("wall_thickness_mm")
    if (geometry_type == "rectangular" and
            (not isinstance(wall, (int, float)) or isinstance(wall, bool)
             or not math.isfinite(wall) or wall <= 0)):
        missing_inputs.append("fabrication.wall_thickness_mm")
        questions.append("Specify a positive rectangular-cabinet wall thickness in millimetres.")

    bom = brief.get("bill_of_materials")
    if not isinstance(bom, list) or not bom:
        missing_inputs.append("bill_of_materials")
        questions.append("List the user-selected drivers, crossover parts, cabinet material, and hardware.")
    else:
        for index, item in enumerate(bom):
            quantity = item.get("quantity", 1) if isinstance(item, dict) else None
            if (not isinstance(item, dict) or not item.get("item")
                    or not isinstance(quantity, (int, float))
                    or not math.isfinite(quantity) or quantity <= 0):
                missing_inputs.append(f"bill_of_materials[{index}]")
            elif item.get("price") is not None and (
                not isinstance(item["price"], (int, float)) or not math.isfinite(item["price"])
                or item["price"] < 0
            ):
                missing_inputs.append(f"bill_of_materials[{index}].price")
        if any(item.get("price") is None for item in bom if isinstance(item, dict)):
            warnings.append("One or more user-selected BOM prices are unknown; no substitute price was assumed.")

    measurement_metadata = brief.get("measurement_metadata", {})
    if not isinstance(measurement_metadata, dict):
        measurement_metadata = {}
        warnings.append("Measurement metadata must be a JSON object; measured-design gates remain closed.")
    missing_measurements = []
    if measurement_metadata.get("on_baffle") is not True:
        missing_measurements.append("measurement_metadata.on_baffle")
    for field in ("measurement_voltage_v", "reference_distance_m", "microphone_orientation_degrees"):
        value = measurement_metadata.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            missing_measurements.append(f"measurement_metadata.{field}")
        elif field != "microphone_orientation_degrees" and value <= 0:
            missing_measurements.append(f"measurement_metadata.{field}")
    if not isinstance(measurement_metadata.get("time_reference"), str) or not measurement_metadata["time_reference"].strip():
        missing_measurements.append("measurement_metadata.time_reference")
    system_config = brief.get("system_config")
    system_design = brief.get("system_design")
    if system_config and not _resolve(system_config).is_file():
        missing_inputs.append("system_config_file")
        questions.append(f"Measured-system config not found: {system_config}")
    elif system_config and _resolve(system_config).is_file():
        try:
            system_object = json.loads(_resolve(system_config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            system_object = None
            missing_inputs.append("system_config_json")
            questions.append("Measured-system config must be valid JSON.")
        if isinstance(system_object, dict):
            branches = _system_branches(system_object)
            missing_inputs.extend(_driver_mapping_issues(drivers, branches, ways, "system_config"))
    elif system_config and _resolve(system_config).is_file():
        try:
            system_object = json.loads(_resolve(system_config).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            system_object = None
        if not isinstance(system_object, dict):
            missing_inputs.append("system_config_json")
            questions.append("Measured-system config must be valid JSON object data.")
        else:
            branches = _system_branches(system_object)
            missing_inputs.extend(_driver_mapping_issues(drivers, branches, ways, "system_config"))
    if system_design is not None and (
        not isinstance(system_design, dict) or not system_design
        or not _system_branches(system_design)
    ):
        missing_inputs.append("system_design")
        questions.append("Embedded system_design must contain populated branches or woofer/tweeter driver configs.")
    elif isinstance(system_design, dict):
        missing_inputs.extend(_driver_mapping_issues(
            drivers, _system_branches(system_design), ways, "system_design"
        ))
    if not system_config and not isinstance(system_design, dict):
        missing_measurements.append("system_config")
    measurement_metadata = brief.get("measurement_metadata", {})
    missing_measurements.extend(_measurement_metadata_gaps(measurement_metadata))

    missing_inputs = sorted(set(missing_inputs))
    missing_measurements = sorted(set(missing_measurements))
    questions = list(dict.fromkeys(questions))
    status = "NEEDS_INPUT" if missing_inputs else "PROTOTYPE_ONLY"
    stages = [
        {"stage": "brief_and_targets", "status": "complete" if not any(x.startswith("target.") for x in missing_inputs) else "blocked"},
        {"stage": "user_selected_drivers", "status": "complete" if drivers and not any(x.startswith("drivers") for x in missing_inputs) else "blocked"},
        {"stage": "enclosure_calculation", "status": "configured" if enclosure_config and _resolve(enclosure_config).is_file() else "blocked"},
        {"stage": "fabrication_and_user_bom", "status": "complete" if not any(x.startswith(("fabrication.", "bill_of_materials")) for x in missing_inputs) else "blocked"},
        {"stage": "measured_crossover", "status": "ready_to_simulate" if not missing_measurements else "measurement_required"},
        {"stage": "prototype_verification", "status": "required_after_build"},
    ]
    return {
        "schema_version": 1,
        "project_name": project_name,
        "status": status,
        "ways": ways,
        "target": target,
        "budget": budget,
        "drivers": drivers,
        "missing_inputs": missing_inputs,
        "missing_measurements": missing_measurements,
        "questions": questions,
        "warnings": warnings,
        "stages": stages,
        "enclosure_config": enclosure_config,
        "box_design": box_design,
        "system_config": system_config,
        "system_design": system_design,
        "measurement_metadata": measurement_metadata,
        "fabrication": fabrication,
        "fabrication_volume": volume_calculation,
        "bill_of_materials": bom or [],
    }


def _build_notes(plan, generated, report_files=None):
    lines = [f"# {plan['project_name'] or 'Speaker Design'}", "",
             f"**Readiness: {plan['status']}**", "",
             "All drivers, prices, enclosure choices, and BOM entries below came from the user brief; "
             "this workflow does not auto-select or substitute parts.", "",
             "## Targets", "",
             f"Topology: {plan['ways'] or '?'} ways",
             f"Frequency: {plan['target'].get('low_hz', '?')} Hz to {plan['target'].get('high_hz', '?')} Hz",
             f"SPL: {plan['target'].get('target_spl_db', '?')} dB at {plan['target'].get('distance_m', '?')} m",
             f"Budget: {plan['budget'].get('amount')} {plan['budget'].get('currency')}"
             if isinstance(plan.get("budget"), dict) else "Budget: not specified",
             "", "## User-Selected Drivers", ""]
    for driver in plan["drivers"]:
        price = f", price {driver['price']}" if driver.get("price") is not None else ""
        part = f" ({driver['part_number']})" if driver.get("part_number") else ""
        lines.append(f"- {driver.get('role', 'way')}: {driver.get('name', 'unspecified')}{part}; "
                     f"data source {driver.get('source', 'missing')}{price}")
    fabrication = plan["fabrication"]
    volume_note = fabrication.get("net_volume_l")
    volume_calc = plan.get("fabrication_volume")
    if volume_note is None and volume_calc:
        volume_note = f"{volume_calc['net_volume_l']:.2f} L (derived)"
    lines.extend(("", "## Fabrication", "",
                  f"External dimensions (mm): {fabrication.get('external_dimensions_mm', 'missing')}",
                  f"Net volume (L): {volume_note or 'missing'}",
                  f"Cutouts/centers: {fabrication.get('cutouts', 'missing')}", "",
                  "## User Bill of Materials", ""))
    if volume_calc:
        lines.insert(lines.index("## User Bill of Materials"),
                     f"Volume calculation: {volume_calc['gross_volume_l']:.2f} L gross - "
                     f"{volume_calc['displacement_total_l']:.2f} L user displacement ledger; "
                     f"{volume_calc['assumption']}")
    for item in plan["bill_of_materials"]:
        price = f"; user price {item['price']}" if item.get("price") is not None else ""
        lines.append(f"- {item.get('quantity', 1)} x {item.get('item', 'unspecified')}{price}")
    lines.extend(("", "## Open Questions", ""))
    if plan["missing_inputs"] or plan["missing_measurements"]:
        lines.extend(f"- Input: `{item}`" for item in plan["missing_inputs"])
        lines.extend(f"- Measurement: `{item}`" for item in plan["missing_measurements"])
    else:
        lines.append("- Required brief and measurement inputs are present; build and verify the prototype.")
    if plan.get("warnings") or plan.get("calculation_errors"):
        lines.extend(("", "## Warnings", ""))
        lines.extend(f"- {warning}" for warning in plan.get("warnings", []))
        lines.extend(f"- Calculation blocked: {error}" for error in plan.get("calculation_errors", []))
    lines.extend(("", "## Generated Calculations", ""))
    lines.extend(f"- {path}" for path in generated) if generated else lines.append("- None; required configuration or measurements are missing.")
    if report_files:
        lines.extend(("", "## Design Reports", ""))
        lines.extend(f"- {path}" for path in report_files)
    lines.extend(("", "No candidate scoring, price substitution, or hidden design preference is applied. "
                  "The package is deterministic for the same brief, source data, and software version. "
                  "Prototype verification is still required.", ""))
    return "\n".join(lines)


def run(brief_path, output_dir):
    brief_path = Path(brief_path)
    if not brief_path.is_absolute():
        brief_path = ROOT / brief_path
    brief = json.loads(brief_path.read_text(encoding="utf-8"))
    plan = assess_brief(brief)
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    results_dir = output_dir / "results"
    results_dir.mkdir(exist_ok=True)
    inputs_dir = output_dir / "inputs"
    inputs_dir.mkdir(exist_ok=True)
    shutil.copyfile(brief_path, inputs_dir / "design_brief.json")
    copied_configs = {}
    for key in ("enclosure_config", "system_config"):
        if plan.get(key):
            source = _resolve(plan[key])
            if source.is_file():
                name = f"{key}.json"
                shutil.copyfile(source, inputs_dir / name)
                copied_configs[key] = f"inputs/{name}"
    generated_enclosure_config = None
    if not plan["missing_inputs"] and not plan["enclosure_config"] and plan["box_design"]:
        box_role = plan["box_design"].get("driver_role")
        driver = next((item for item in plan["drivers"] if item.get("role") == box_role), None)
        if driver:
            target = plan["target"]
            simulation = brief.get("box_simulation", {})
            start_hz = simulation.get("start_hz", max(10.0, target.get("low_hz", 20) / 2))
            stop_hz = simulation.get("stop_hz", target.get("high_hz", 20000))
            generated_enclosure_config = {
                "driver": {key: value for key, value in driver.items()
                           if key not in {"role", "part_number", "price", "quantity",
                                          "series", "parallel"}},
                "wiring": {"series": driver["series"], "parallel": driver["parallel"]},
                "enclosure": plan["box_design"],
                "simulation": {
                    "start_hz": start_hz,
                    "stop_hz": stop_hz,
                    "points": simulation.get("points", 500),
                    "voltage_rms": simulation.get("voltage_rms", 2.83),
                    "reference_band_hz": simulation.get("reference_band_hz", [150, 300]),
                    "limit_minimum_hz": simulation.get("limit_minimum_hz", target.get("low_hz", 25)),
                    **{key: value for key, value in simulation.items()
                       if key not in {"start_hz", "stop_hz", "points", "voltage_rms",
                                      "reference_band_hz", "limit_minimum_hz"}},
                },
                "output_csv": "results/low_frequency.csv",
            }
            generated_path = inputs_dir / "generated_enclosure_config.json"
            generated_path.write_text(json.dumps(generated_enclosure_config, indent=2) + "\n",
                                      encoding="utf-8")
            copied_configs["generated_enclosure_config"] = "inputs/generated_enclosure_config.json"

    generated_system_config = None
    if plan["system_design"]:
        generated_system_config = inputs_dir / "generated_system_config.json"
        generated_system_config.write_text(json.dumps(plan["system_design"], indent=2) + "\n",
                                           encoding="utf-8")
        copied_configs["generated_system_config"] = "inputs/generated_system_config.json"

    generated = []
    calculation_errors = []
    enclosure_config = plan["enclosure_config"]
    if plan["status"] != "NEEDS_INPUT":
        try:
            if generated_enclosure_config:
                run_box(generated_path, results_dir / "low_frequency.csv")
                generated.append("results/low_frequency.csv")
            elif enclosure_config and _resolve(enclosure_config).is_file():
                run_box(enclosure_config, results_dir / "low_frequency.csv")
                generated.append("results/low_frequency.csv")
        except (KeyError, TypeError, ValueError, FileNotFoundError) as error:
            calculation_errors.append(f"Enclosure calculation: {error}")
            plan["status"] = "NEEDS_INPUT"
    selected_system_config = (generated_system_config if generated_system_config
                              else _resolve(plan["system_config"]) if plan["system_config"] else None)
    if (plan["status"] != "NEEDS_INPUT" and not plan["missing_inputs"] and selected_system_config
            and Path(selected_system_config).is_file()):
        try:
            system_output = results_dir / "system_response.csv"
            run_system(selected_system_config, system_output)
            generated.append("results/system_response.csv")
            coverage = _measured_coverage(system_output)
            plan["measured_coverage_fraction"] = coverage
            if coverage < 1.0:
                plan["missing_measurements"] = sorted(set(
                    plan["missing_measurements"] + ["full_frd_zma_frequency_coverage"]
                ))
                plan["warnings"].append(
                    f"FRD/ZMA cover {coverage:.1%} of simulated rows; out-of-range endpoints are extrapolated holds."
                )
            plan["status"] = (
                "READY_FOR_PROTOTYPE_VALIDATION"
                if coverage == 1.0 and not plan["missing_measurements"]
                else "PROTOTYPE_ONLY"
            )
        except MeasurementCoverageError as error:
            plan["missing_measurements"] = sorted(set(
                plan["missing_measurements"] + ["requested_measurement_angles"]
            ))
            plan["warnings"].append(str(error))
            plan["status"] = "PROTOTYPE_ONLY"
        except (KeyError, TypeError, ValueError, FileNotFoundError) as error:
            calculation_errors.append(f"Measured-system calculation: {error}")
            plan["status"] = "NEEDS_INPUT"

    plan["generated_calculations"] = generated
    plan["calculation_errors"] = calculation_errors
    plan["copied_configs"] = copied_configs
    plan["input_manifest"] = _input_manifest(brief_path, brief)
    report_files = generate_report(plan, output_dir)
    report_outputs = [report_files["markdown"], report_files["latex"]]
    if report_files["pdf"]:
        report_outputs.append(report_files["pdf"])
    plan["generated_report"] = report_files
    (output_dir / "design_plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "status": plan["status"],
        "portable": False,
        "reproduction_note": "External FRD/ZMA/calibration/fitted files are hashed by source path but not bundled; retain those files at their recorded paths.",
        "input_files": plan["input_manifest"],
        "copied_configs": copied_configs,
        "generated_files": generated + report_outputs,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output_dir / "BUILD_NOTES.md").write_text(
        _build_notes(plan, generated, report_outputs), encoding="utf-8"
    )
    print(f"Design package: {output_dir}")
    print(f"Readiness: {plan['status']}")
    print(f"Missing user inputs: {len(plan['missing_inputs'])}; measurements/configs outstanding: "
          f"{len(plan['missing_measurements'])}")
    for question in plan["questions"]:
        print(f"  - {question}")
    return plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("brief", help="Normalized user-selected design brief JSON")
    parser.add_argument("--output-dir", required=True, help="Directory for auditable design package")
    args = parser.parse_args()
    run(args.brief, args.output_dir)


if __name__ == "__main__":
    main()