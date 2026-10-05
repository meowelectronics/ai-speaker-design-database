"""Run a complex T/S enclosure simulation from a JSON configuration."""

import argparse
import csv
import json
import math
from pathlib import Path

from scripts.enclosure.acoustic_model import (
    DriverParameters,
    EnclosureParameters,
    PassiveRadiatorParameters,
    equivalent_driver_array,
    maximum_voltage,
    port_geometry,
    simulate,
)
from scripts.enclosure.ts_alignments import driver_components_from_thiele_small
from scripts.project_paths import ROOT


def _driver_parameters(config):
    source = config.get("source", "components")
    if source in {"datasheet_ts", "measured_ts"}:
        values = driver_components_from_thiele_small(
            fs=config["fs_hz"],
            qes=config["qes"],
            qms=config["qms"],
            re=config["re_ohm"],
            vas=config["vas_m3"],
            sd=config["sd_m2"],
            le=config.get("le_h", 0.0),
            xmax=config.get("xmax_m"),
        )
        driver = DriverParameters(
            re=values["re"], le=values["le"], bl=values["bl"],
            mms=values["mms"], cms=values["cms"], rms=values["rms"],
            sd=values["sd"], xmax=values["xmax"],
            name=config.get("name", "driver"),
            inductance_exponent=config.get("inductance_exponent", 1.0),
            inductance_reference_frequency=config.get("inductance_reference_frequency_hz", 1000.0),
            power_handling_w=config.get("power_handling_w"),
        )
    elif source == "fitted_json":
        fit_path = Path(config["fit_json"])
        if not fit_path.is_absolute():
            fit_path = ROOT / fit_path
        payload = json.loads(fit_path.read_text(encoding="utf-8"))
        parameters = payload.get("driver", payload)
        driver = DriverParameters(**parameters)
    elif source == "components":
        driver = DriverParameters(
            re=config["re_ohm"],
            le=config.get("le_h", 0.0),
            bl=config["bl_tm"],
            mms=config["mms_kg"],
            cms=config["cms_m_n"],
            rms=config["rms_ns_m"],
            sd=config["sd_m2"],
            xmax=config.get("xmax_m"),
            name=config.get("name", "driver"),
            inductance_exponent=config.get("inductance_exponent", 1.0),
            inductance_reference_frequency=config.get("inductance_reference_frequency_hz", 1000.0),
            power_handling_w=config.get("power_handling_w"),
        )
    else:
        raise ValueError("Driver source must be components, datasheet_ts, measured_ts, or fitted_json.")
    wiring = config.get("wiring", {})
    return equivalent_driver_array(driver, wiring.get("series", 1), wiring.get("parallel", 1))


def _enclosure_parameters(config):
    radiator_config = config.get("radiator")
    radiator = PassiveRadiatorParameters(**radiator_config) if radiator_config else None
    return EnclosureParameters(
        kind=config["kind"],
        volume=config.get("volume_m3", 0.0),
        tuning=config.get("tuning_hz"),
        ql=config.get("ql", 15.0),
        qa=config.get("qa", 100.0),
        qp=config.get("qp", 20.0),
        port_area=config.get("port_area_m2"),
        port_count=config.get("port_count", 1),
        port_end_correction=config.get("port_end_correction_m", 0.0),
        radiator=radiator,
    )


def _f3(rows, reference_band, relative_db=3.0):
    reference = [row["spl_db"] for row in rows
                 if reference_band[0] <= row["frequency"] <= reference_band[1]]
    if not reference:
        raise ValueError("Frequency grid does not cover the configured reference band.")
    level = sum(reference) / len(reference)
    threshold = level - relative_db
    return next((row["frequency"] for row in rows if row["spl_db"] >= threshold), None)


def run(config_path, output_override=None):
    config_path = Path(config_path)
    if not config_path.is_absolute():
        config_path = ROOT / config_path
    config = json.loads(config_path.read_text(encoding="utf-8"))
    driver = _driver_parameters(config["driver"])
    enclosure = _enclosure_parameters(config["enclosure"])
    simulation = config["simulation"]
    start, stop, count = (simulation["start_hz"], simulation["stop_hz"],
                          simulation.get("points", 500))
    if start <= 0 or stop <= start or count < 2:
        raise ValueError("Simulation frequency range and point count are invalid.")
    frequencies = [start * (stop / start) ** (index / (count - 1)) for index in range(count)]
    rows = simulate(
        driver,
        enclosure,
        frequencies,
        voltage=simulation.get("voltage_rms", 2.83),
        distance=simulation.get("distance_m", 1.0),
        radiation_solid_angle=simulation.get("radiation_solid_angle_sr", 2 * math.pi),
    )
    output_path = Path(output_override or config["output_csv"])
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.writer(output)
        writer.writerow(("frequency_hz", "spl_db", "impedance_ohm", "impedance_phase_deg",
                         "group_delay_ms", "cone_excursion_mm", "radiator_excursion_mm",
                         "radiator_velocity_m_s", "port_velocity_m_s"))
        for row in rows:
            writer.writerow((
                row["frequency"], row["spl_db"], abs(row["input_impedance"]),
                math.degrees(math.atan2(row["input_impedance"].imag,
                                        row["input_impedance"].real)),
                row["group_delay"] * 1000, row["cone_excursion"] * 1000,
                row["radiator_excursion"] * 1000 if row["radiator_excursion"] is not None else "",
                row["radiator_velocity"] if row["radiator_velocity"] is not None else "",
                row["port_velocity"] if row["port_velocity"] is not None else "",
            ))

    f3 = _f3(rows, tuple(simulation.get("reference_band_hz", [150, 300])))
    limit = maximum_voltage(
        rows,
        driver,
        enclosure.radiator,
        minimum_frequency=simulation.get("limit_minimum_hz", 25.0),
        maximum_port_velocity=simulation.get("maximum_port_velocity_m_s"),
        input_voltage=simulation.get("voltage_rms", 2.83),
    )
    print(f"Wrote {len(rows)} rows to {output_path}")
    print(f"Driver: Fs={driver.fs:.2f} Hz, Qts={driver.qts:.3f}, Vas={driver.vas*1000:.3f} L")
    print(f"Modeled F3 relative to reference band: {f3:.2f} Hz" if f3 else "F3 was not reached in the frequency range")
    print(f"Minimum input impedance: {min(abs(row['input_impedance']) for row in rows):.2f} ohm")
    if enclosure.kind in {"vented", "aperiodic"}:
        geometry = port_geometry(enclosure)
        print(f"Port: {geometry['physical_length']*100:.1f} cm long, "
              f"{geometry['diameter_per_port']*100:.1f} cm diameter each, "
              f"pipe resonance {geometry['first_pipe_resonance']:.0f} Hz")
    if limit:
        voltage, source = limit
        print(f"Linear limit above {simulation.get('limit_minimum_hz', 25.0):g} Hz: "
              f"{voltage:.2f} Vrms ({source}); thermal and compression limits excluded")
    return output_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", help="JSON enclosure configuration, relative to workspace root")
    parser.add_argument("--output", help="override configured CSV output path")
    args = parser.parse_args()
    run(args.config, args.output)


if __name__ == "__main__":
    main()