"""Import WinISD .wdr driver records into a separate normalized JSON catalog."""

import argparse
from collections import defaultdict
from configparser import ConfigParser
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from pathlib import Path
import re

from scripts.project_paths import ROOT

DEFAULT_SOURCE = ROOT / "data" / "local" / "winisd"
DEFAULT_OUTPUT = ROOT / "data" / "catalogs" / "winisd_drivers.json"

PARAMETERS = {
    "fs_hz": ("Fs", "Hz"),
    "qts": ("Qts", "ratio"),
    "qms": ("Qms", "ratio"),
    "qes": ("Qes", "ratio"),
    "nominal_impedance_ohm": ("Znom", "ohm"),
    "re_ohm": ("Re", "ohm"),
    "le_h": ("Le", "H"),
    "power_w": ("Pe", "W"),
    "sensitivity_db": ("SPL", "dB"),
    "bl_tm": ("BL", "T m"),
    "xmax_m": ("Xmax", "m"),
    "cms_m_per_n": ("Cms", "m/N"),
    "rms_n_s_per_m": ("Rms", "N s/m"),
    "mms_kg": ("Mms", "kg"),
    "sd_m2": ("Sd", "m^2"),
    "vas_m3": ("Vas", "m^3"),
}
MODEL_REQUIRED_PARAMETERS = (
    "fs_hz", "qes", "qms", "nominal_impedance_ohm", "re_ohm", "bl_tm",
    "cms_m_per_n", "rms_n_s_per_m", "mms_kg", "sd_m2", "vas_m3",
)
PLAUSIBLE_RANGES = {
    "fs_hz": (1, 30000),
    "qts": (0, 20),
    "qms": (0, 100),
    "qes": (0, 100),
    "nominal_impedance_ohm": (0, 256),
    "re_ohm": (0, 256),
    "bl_tm": (0, 256),
    "xmax_m": (0, 1),
    "cms_m_per_n": (0, 1),
    "rms_n_s_per_m": (0, 10000),
    "mms_kg": (0, 100),
    "sd_m2": (0, 2),
    "vas_m3": (0, 100),
}

_NUMBER = re.compile(r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$")


def parse_number(value):
    """Parse a WinISD number, including decimal-comma locales."""
    text = str(value).strip()
    if not _NUMBER.fullmatch(text):
        raise ValueError(f"Not a numeric WinISD value: {value!r}")
    normalized = text.replace(",", ".")
    try:
        number = Decimal(normalized)
    except InvalidOperation as error:
        raise ValueError(f"Invalid numeric WinISD value: {value!r}") from error
    if not number.is_finite():
        raise ValueError(f"Non-finite WinISD value: {value!r}")
    return float(number)


def quality_flags(parameters):
    flags = [f"nonpositive:{key}" for key in MODEL_REQUIRED_PARAMETERS
             if parameters[key] <= 0]
    for key, (minimum, maximum) in PLAUSIBLE_RANGES.items():
        value = parameters[key]
        if value <= minimum or value > maximum:
            flags.append(f"out_of_range:{key}")

    if parameters["mms_kg"] > 0 and parameters["cms_m_per_n"] > 0:
        predicted_fs = 1 / (2 * math.pi
                            * (parameters["mms_kg"] * parameters["cms_m_per_n"]) ** 0.5)
        if abs(predicted_fs - parameters["fs_hz"]) / parameters["fs_hz"] > 0.1:
            flags.append("fs_mms_cms_mismatch_over_10pct")
    if parameters["qes"] > 0 and parameters["qms"] > 0:
        predicted_qts = parameters["qes"] * parameters["qms"] / (
            parameters["qes"] + parameters["qms"]
        )
        if abs(predicted_qts - parameters["qts"]) / parameters["qts"] > 0.1:
            flags.append("qts_qes_qms_mismatch_over_10pct")
    if (parameters["cms_m_per_n"] > 0 and parameters["sd_m2"] > 0
            and parameters["vas_m3"] > 0):
        predicted_vas = 1.18 * 343**2 * parameters["cms_m_per_n"] * parameters["sd_m2"]**2
        if abs(predicted_vas - parameters["vas_m3"]) / parameters["vas_m3"] > 0.1:
            flags.append("vas_cms_sd_mismatch_over_10pct")
    return flags


def parse_record(path):
    parser = ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    source_path = Path(path)
    source_bytes = source_path.read_bytes()
    try:
        text = source_bytes.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = source_bytes.decode("cp1252")
    parser.read_string(text)
    if "Driver" not in parser:
        raise ValueError("missing [Driver] section")
    raw = {key: value.strip() for key, value in parser["Driver"].items()}
    brand, model = raw.get("Brand", "").strip(), raw.get("Model", "").strip()
    if not brand or not model:
        raise ValueError("missing Brand or Model")

    parameters = {}
    for output_key, (source_key, _unit) in PARAMETERS.items():
        if source_key not in raw:
            raise ValueError(f"missing required parameter {source_key}")
        parameters[output_key] = parse_number(raw[source_key])

    digest = hashlib.sha256(source_bytes).hexdigest()
    record_digest = hashlib.sha256(
        source_path.name.casefold().encode("utf-8") + b"\0" + source_bytes
    ).hexdigest()
    identity = f"{brand.casefold()}|{model.casefold()}"
    flags = quality_flags(parameters)
    return {
        "record_id": f"winisd:{record_digest[:20]}",
        "source_file": source_path.name,
        "source_sha256": digest,
        "brand": brand,
        "model": model,
        "manufacturer": raw.get("Manufacturer", ""),
        "provided_by": raw.get("ProvidedBy", ""),
        "comment": raw.get("Comment", ""),
        "date_added": raw.get("DateAdded", ""),
        "date_modified": raw.get("DateModified", ""),
        "identity_key": identity,
        "parameters": parameters,
        "model_ready": not flags,
        "quality_flags": flags,
        "raw_fields": raw,
    }


def import_directory(source_dir=DEFAULT_SOURCE, output_path=DEFAULT_OUTPUT):
    source_dir, output_path = Path(source_dir), Path(output_path)
    files = sorted(source_dir.glob("*.wdr"), key=lambda path: path.name.casefold())
    if not files:
        raise ValueError(f"No .wdr files found in {source_dir}")

    records, failures = [], []
    for path in files:
        try:
            records.append(parse_record(path))
        except (OSError, UnicodeError, ValueError) as error:
            failures.append({"file": path.name, "error": str(error)})
    if failures:
        preview = "; ".join(f"{item['file']}: {item['error']}" for item in failures[:10])
        raise ValueError(f"{len(failures)} of {len(files)} files failed import: {preview}")

    groups = defaultdict(list)
    for record in records:
        groups[record["identity_key"]].append(record["source_file"])
    duplicate_groups = {
        identity: names for identity, names in sorted(groups.items()) if len(names) > 1
    }
    content_hash_counts = defaultdict(int)
    for record in records:
        content_hash_counts[record["source_sha256"]] += 1
    quality_counts = defaultdict(int)
    for record in records:
        for flag in record["quality_flags"]:
            quality_counts[flag.split(":", 1)[0] if ":" in flag else flag] += 1
    for record in records:
        names = duplicate_groups.get(record["identity_key"])
        record["duplicate_identity"] = names is not None
        if names:
            record["duplicate_source_files"] = names

    catalog = {
        "schema_version": 1,
        "catalog_name": "WinISD driver models",
        "source_format": "WinISD .wdr [Driver] INI records",
        "source_directory": str(source_dir.resolve()),
        "imported_at_utc": datetime.now(timezone.utc).isoformat(),
        "record_count": len(records),
        "duplicate_identity_group_count": len(duplicate_groups),
        "duplicate_content_group_count": sum(count > 1 for count in content_hash_counts.values()),
        "model_ready_record_count": sum(record["model_ready"] for record in records),
        "incomplete_model_record_count": sum(not record["model_ready"] for record in records),
        "quality_flag_record_count": sum(bool(record["quality_flags"]) for record in records),
        "quality_flag_counts": dict(sorted(quality_counts.items())),
        "parameter_units": {
            output_key: unit for output_key, (_source_key, unit) in PARAMETERS.items()
        },
        "notes": [
            "Raw source fields are retained verbatim as strings for provenance.",
            "Decimal commas are parsed as decimal points in normalized numeric fields.",
            "Le is interpreted as henries; the remaining mapped parameters use the units stated in the WinISD model format.",
            "Records with duplicate Brand/Model identities are preserved and flagged; none are silently merged.",
            "Records with zero or negative model-critical parameters are retained but flagged as not model-ready.",
            "Basic range and Fs/Qts/Vas consistency checks flag suspicious legacy records; flags are screening aids, not certification.",
            "WinISD entries are separate from Parts Express catalog snapshots; prices and physical cutout data are not inferred.",
        ],
        "drivers": records,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source_dir", nargs="?", default=str(DEFAULT_SOURCE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    catalog = import_directory(args.source_dir, args.output)
    print(f"Imported {catalog['record_count']} WinISD models to {args.output}")
    print(f"Duplicate Brand/Model groups preserved and flagged: "
          f"{catalog['duplicate_identity_group_count']}")


if __name__ == "__main__":
    main()
