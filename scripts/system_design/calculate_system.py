"""Run a measured-data two-way design from a JSON configuration file."""

import argparse
import cmath
import csv
import json
import math
from pathlib import Path

from scripts.measurement.response_data import (
    MagnitudeCorrection,
    MeasurementCoverageError,
    measured_angles,
    measured_driver_files,
    measured_driver_at_angle,
)
from scripts.system_design.active_filters import (
    ActiveFilterChain,
    LinkwitzTransform,
    active_pass_filter,
    allpass,
    high_shelf,
    highpass,
    low_shelf,
    lowpass,
    peaking_eq,
)
from scripts.project_paths import ROOT
from scripts.system_design.diffraction import make as make_baffle_diffraction
from scripts.system_design.system_calculator import (
    LadderElement,
    LadderNetwork,
    PassiveLadder,
    TwoWayCrossover,
    design_standard_ladder,
    optimize_two_way,
    score_system,
    simulate_multiway,
    simulate_two_way,
    weighted_angular_average,
)


def _workspace_path(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def _load_angle_data(config, calibration=None):
    if "frd_files" in config:
        files = {int(angle): _workspace_path(path)
                 for angle, path in config["frd_files"].items()}
        return measured_driver_files(
            files, _workspace_path(config["zma_file"]), calibration
        )
    return measured_angles(
        _workspace_path(config["folder"]), config["stem"], calibration=calibration
    )


def _crossover_values(config):
    return TwoWayCrossover(
        woofer_inductor=config["woofer_inductor_mH"] * 1e-3,
        tweeter_capacitor=config["tweeter_capacitor_uF"] * 1e-6,
        tweeter_inductor=config["tweeter_inductor_mH"] * 1e-3,
        tweeter_series_resistor=config.get("tweeter_series_resistor_ohm", 0.0),
        tweeter_shunt_resistor=config.get("tweeter_shunt_resistor_ohm"),
        woofer_zobel_resistor=config.get("woofer_zobel_resistor_ohm"),
        woofer_zobel_capacitor=(
            config["woofer_zobel_capacitor_uF"] * 1e-6
            if "woofer_zobel_capacitor_uF" in config else None
        ),
        woofer_inductor_dcr=config.get("woofer_inductor_dcr_ohm", 0.0),
        tweeter_inductor_dcr=config.get("tweeter_inductor_dcr_ohm", 0.0),
    )


def _optimization_grid(config):
    return {
        "woofer_inductors": [value * 1e-3 for value in config["woofer_inductors_mH"]],
        "tweeter_capacitors": [value * 1e-6 for value in config["tweeter_capacitors_uF"]],
        "tweeter_inductors": [value * 1e-3 for value in config["tweeter_inductors_mH"]],
        "series_resistors": config["tweeter_series_resistors_ohm"],
        "shunt_resistors": config["tweeter_shunt_resistors_ohm"],
        "woofer_inductor_dcrs": config.get("woofer_inductor_dcrs_ohm", [0.0]),
        "tweeter_inductor_dcrs": config.get("tweeter_inductor_dcrs_ohm", [0.0]),
        "zobels": [
            (item["resistor_ohm"], item["capacitor_uF"] * 1e-6)
            for item in config.get("zobels", [None]) if item is not None
        ] or [None],
    }


def _baffle_functions(config):
    if not config:
        return None, None
    width = config["width_mm"] * 1e-3
    height = config["height_mm"] * 1e-3
    woofer_xy = config["woofer_xy_mm"]
    tweeter_xy = config["tweeter_xy_mm"]
    return (
        make_baffle_diffraction(woofer_xy[0] * 1e-3, woofer_xy[1] * 1e-3, width, height),
        make_baffle_diffraction(tweeter_xy[0] * 1e-3, tweeter_xy[1] * 1e-3, width, height),
    )


def _multiway_ladder(config):
    elements = []
    for prototype in config.get("passive_filters", []):
        ladder = design_standard_ladder(
            prototype["direction"], prototype["order"], prototype["alignment"],
            prototype["cutoff_hz"], prototype["reference_impedance_ohm"],
            inductor_dcr=prototype.get("inductor_dcr_ohm", 0.0),
            capacitor_esr=prototype.get("capacitor_esr_ohm", 0.0),
        )
        elements.extend(ladder.elements)
    for element in config.get("custom_elements", []):
        if element["kind"] == "network":
            elements.append(LadderNetwork(
                element["connection"], element["topology"],
                element.get("resistance_ohm", 0.0),
                element.get("inductance_h", 0.0),
                element.get("capacitance_f", 0.0),
            ))
        else:
            elements.append(LadderElement(
                element["kind"], element["connection"], element["value"],
                element.get("series_resistance", 0.0),
            ))
    return PassiveLadder(config.get("direction", "lowpass"), tuple(elements))


def _multiway_active_chain(config, sample_rate):
    filters, delay = [], 0.0
    constructors = {
        "lowpass": lowpass,
        "highpass": highpass,
        "low_shelf": low_shelf,
        "high_shelf": high_shelf,
        "peaking_eq": peaking_eq,
        "allpass": allpass,
    }
    for item in config or []:
        kind = item["type"]
        if kind == "delay":
            delay += item.get("milliseconds", 0.0) * 1e-3
            continue
        if kind not in constructors:
            if kind == "pass_filter":
                filters.extend(active_pass_filter(
                    item["direction"], item["order"], item["alignment"],
                    item["cutoff_hz"], sample_rate,
                ))
                continue
            if kind == "linkwitz_transform":
                filters.append(LinkwitzTransform(
                    item["source_frequency_hz"], item["source_q"],
                    item["target_frequency_hz"], item["target_q"],
                    item.get("linear_phase", False),
                ))
                continue
            raise ValueError(f"Unsupported active filter type: {kind}.")
        constructor = constructors[kind]
        if kind in {"low_shelf", "high_shelf"}:
            filters.append(constructor(item["cutoff_hz"], sample_rate,
                                       item["gain_db"], item.get("slope", 1.0)))
        elif kind == "peaking_eq":
            filters.append(constructor(item["center_hz"], sample_rate,
                                       item["q"], item["gain_db"]))
        else:
            filters.append(constructor(item["cutoff_hz"], sample_rate,
                                       item.get("q", 2**-0.5)))
    return ActiveFilterChain(tuple(filters), delay, sample_rate)


def _run_multiway(config, output_override=None):
    branches_config = config["branches"]
    if len(branches_config) < 1:
        raise ValueError("A system configuration needs at least one branch.")
    simulation = config["simulation"]
    start, stop, count = (simulation["start_hz"], simulation["stop_hz"],
                          simulation.get("points", 400))
    if start <= 0 or stop <= start or count < 2:
        raise ValueError("Simulation frequency range and point count are invalid.")
    frequencies = [start * (stop / start) ** (index / (count - 1)) for index in range(count)]
    sample_rate = simulation.get("sample_rate_hz", 48000.0)
    angles = config.get("angles_degrees", [0])
    calibration = None
    if config.get("microphone_calibration_file"):
        calibration = MagnitudeCorrection.from_file(
            _workspace_path(config["microphone_calibration_file"])
        )
    branch_data = []
    for branch in branches_config:
        drivers = _load_angle_data(branch, calibration)
        reference_angle = 0 if 0 in angles else angles[0]
        if measured_driver_at_angle(drivers, reference_angle) is None:
            raise MeasurementCoverageError(
                f"{branch['name']} has no measured FRD near {reference_angle} degrees."
            )
        branch_data.append((branch, drivers, _multiway_ladder(branch),
                            _multiway_active_chain(branch.get("active_filters"), sample_rate)))

    output_path = Path(output_override or config["output_csv"])
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    all_rows, angle_scores = [], {}
    reference_band = tuple(simulation.get("reference_band_hz", [500, 3000]))
    evaluate_band = tuple(simulation.get("evaluate_band_hz", [300, 16000]))
    for angle in angles:
        branches = []
        for branch, driver_angles, ladder, active_filter in branch_data:
            driver = measured_driver_at_angle(driver_angles, angle)
            if driver is None:
                raise MeasurementCoverageError(
                    f"{branch['name']} lacks data for requested {angle}-degree angle."
                )
            branches.append({
                "name": branch["name"],
                "driver": driver,
                "ladder": ladder,
                "active_filter": active_filter,
                "polarity": branch.get("polarity", 1),
                "offset_m": branch.get("offset_mm", 0.0) * 1e-3,
            })
        if len(branches) != len(branch_data):
            raise MeasurementCoverageError(f"Not every branch has requested {angle}-degree data.")
        rows = simulate_multiway(
            branches,
            frequencies,
            input_voltage=simulation.get("input_voltage", 2.83),
            frd_reference_voltage=simulation.get("frd_reference_voltage", 2.83),
        )
        angle_scores[angle] = score_system(rows, reference_band, evaluate_band)
        all_rows.extend((angle, row) for row in rows)

    if not all_rows:
        raise ValueError("No requested angle has measurement coverage for every branch.")
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("angle_deg", "frequency_hz", "system_spl_db", "phase_deg",
                         "impedance_ohm", "impedance_phase_deg", "group_delay_ms",
                         "measurement_covered",
                         *(f"{branch['name']}_db" for branch in branches_config)))
        for angle, row in all_rows:
            writer.writerow((
                angle, row["frequency"], row["spl_db"],
                math.degrees(cmath.phase(row["response"])),
                row["input_impedance_magnitude"],
                math.degrees(cmath.phase(row["input_impedance"])),
                row["group_delay"] * 1000, row["measurement_covered"],
                *(20 * math.log10(max(abs(row["branch_responses"][branch["name"]]), 1e-30))
                  for branch in branches_config),
            ))

    score = angle_scores.get(0, next(iter(angle_scores.values())))
    print(f"Wrote {len(all_rows)} multiway response rows to {output_path}")
    print(f"Minimum system impedance: {score['minimum_impedance_ohm']:.2f} ohm")
    impedance_floor = simulation.get("minimum_impedance_ohm", 3.2)
    if score["minimum_impedance_ohm"] < impedance_floor:
        print(f"WARNING: below the configured {impedance_floor:.2f} ohm screening floor; "
              "this is not a build-ready crossover")
    print(f"Response RMS deviation: {score['rms_deviation_db']:.2f} dB; "
          f"peak-to-peak: {score['peak_to_peak_db']:.2f} dB")
    print(f"Measured-data coverage: {score['measurement_coverage_fraction']*100:.1f}% of evaluation band")
    return output_path


def run(config_path, output_override=None):
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if "branches" in config:
        return _run_multiway(config, output_override)

    calibration = None
    if config.get("microphone_calibration_file"):
        calibration = MagnitudeCorrection.from_file(
            _workspace_path(config["microphone_calibration_file"])
        )
    woofer_cfg, tweeter_cfg = config["woofer"], config["tweeter"]
    woofer_angles = _load_angle_data(woofer_cfg, calibration)
    tweeter_angles = _load_angle_data(tweeter_cfg, calibration)
    angles = config.get("angles_degrees", [0])
    reference_angle = 0 if 0 in angles else angles[0]
    reference_woofer = measured_driver_at_angle(woofer_angles, reference_angle)
    reference_tweeter = measured_driver_at_angle(tweeter_angles, reference_angle)
    if reference_woofer is None or reference_tweeter is None:
        raise ValueError("Both drivers need FRD data at the selected reference angle.")

    simulation = config["simulation"]
    start, stop, count = (simulation["start_hz"], simulation["stop_hz"],
                          simulation.get("points", 400))
    if start <= 0 or stop <= start or count < 2:
        raise ValueError("Simulation frequency range and point count are invalid.")
    frequencies = [start * (stop / start) ** (index / (count - 1)) for index in range(count)]
    baffle_woofer, baffle_tweeter = _baffle_functions(config.get("baffle"))
    common = {
        "input_voltage": simulation.get("input_voltage", 2.83),
        "frd_reference_voltage": simulation.get("frd_reference_voltage", 2.83),
        "tweeter_offset": simulation.get("tweeter_offset_mm", 0.0) * 1e-3,
        "invert_tweeter": simulation.get("invert_tweeter", False),
        "woofer_baffle": baffle_woofer,
        "tweeter_baffle": baffle_tweeter,
    }

    search = config.get("search")
    if search:
        ranked = optimize_two_way(
            reference_woofer, reference_tweeter,
            _optimization_grid(search), frequencies,
            minimum_impedance=search.get("minimum_impedance_ohm", 3.2),
            limit=search.get("keep_candidates", 1), **common,
        )
        if not ranked:
            raise ValueError("No crossover candidates met the impedance floor.")
        crossover = ranked[0][2]
    else:
        crossover = _crossover_values(config["crossover"])

    output_path = _workspace_path(output_override or config["output_csv"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    reference_band = tuple(simulation.get("reference_band_hz", [500, 3000]))
    evaluate_band = tuple(simulation.get("evaluate_band_hz", [300, 16000]))
    all_rows = []
    angle_scores = {}
    rows_by_angle = {}
    for angle in angles:
        woofer = measured_driver_at_angle(woofer_angles, angle)
        tweeter = measured_driver_at_angle(tweeter_angles, angle)
        if woofer is None or tweeter is None:
            raise MeasurementCoverageError(
                f"Both drivers need measured/interpolable data at requested {angle}-degree angle."
            )
        rows = simulate_two_way(woofer, tweeter, crossover,
                                frequencies, **common)
        score = score_system(rows, reference_band, evaluate_band)
        angle_scores[angle] = score
        rows_by_angle[angle] = rows
        all_rows.extend((angle, row) for row in rows)

    if not all_rows:
        raise ValueError("No common measured FRD angles are available for both drivers.")
    angular_by_frequency = {}
    if "angular_weights" in config:
        weights = {float(angle): float(weight)
                   for angle, weight in config["angular_weights"].items()}
        angular_by_frequency = {
            row["frequency"]: row
            for row in weighted_angular_average(rows_by_angle, weights)
        }
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("angle_deg", "frequency_hz", "spl_db", "phase_deg",
                         "woofer_db", "tweeter_db", "impedance_ohm",
                         "impedance_phase_deg", "group_delay_ms", "measurement_covered",
                         "weighted_spatial_level_db", "directivity_index_db"))
        for angle, row in all_rows:
            writer.writerow((
                angle, row["frequency"], row["spl_db"],
                math.degrees(cmath.phase(row["response"])),
                20 * math.log10(max(abs(row["woofer_response"]), 1e-30)),
                20 * math.log10(max(abs(row["tweeter_response"]), 1e-30)),
                row["input_impedance_magnitude"],
                math.degrees(cmath.phase(row["input_impedance"])),
                row["group_delay"] * 1000, row["measurement_covered"],
                angular_by_frequency.get(row["frequency"], {}).get("weighted_spatial_level_db", ""),
                angular_by_frequency.get(row["frequency"], {}).get("directivity_index_db", ""),
            ))

    score = angle_scores.get(reference_angle, next(iter(angle_scores.values())))
    print(f"Wrote {len(all_rows)} response rows to {output_path}")
    print(f"Minimum system impedance: {score['minimum_impedance_ohm']:.2f} ohm")
    impedance_floor = simulation.get("minimum_impedance_ohm", 3.2)
    if score["minimum_impedance_ohm"] < impedance_floor:
        print(f"WARNING: below the configured {impedance_floor:.2f} ohm screening floor; "
              "this is not a build-ready crossover")
    print(f"Response RMS deviation: {score['rms_deviation_db']:.2f} dB; "
          f"peak-to-peak: {score['peak_to_peak_db']:.2f} dB")
    print(f"Measured-data coverage: {score['measurement_coverage_fraction']*100:.1f}% "
          f"of the evaluation band")
    if angular_by_frequency:
        print("Weighted spatial level and directivity included using configured angular weights")
    print("Crossover: "
          f"Lw={crossover.woofer_inductor*1e3:.3g} mH, "
          f"Ct={crossover.tweeter_capacitor*1e6:.3g} uF, "
          f"Lt={crossover.tweeter_inductor*1e3:.3g} mH")
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="JSON design configuration, relative to workspace root")
    parser.add_argument("--output", help="override configured CSV output path")
    args = parser.parse_args()
    run(args.config, args.output)


if __name__ == "__main__":
    main()