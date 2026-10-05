import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from scripts.project_paths import ROOT
from scripts.system_design.design_workflow import assess_brief, run


def base_brief(enclosure_path, system_path=None, measurement_metadata=None):
    return {
        "schema_version": 1,
        "project_name": "User-selected four-way",
        "ways": 4,
        "target": {"low_hz": 30, "high_hz": 20000,
                   "target_spl_db": 100, "distance_m": 2},
        "drivers": [
            {"role": f"way-{index}", "name": f"Chosen driver {index}",
             "part_number": f"P-{index}", "source": "measured_ts",
             "quantity": 1, "series": 1, "parallel": 1,
             "price": 22.50 + index, "fs_hz": 70, "qes": 0.4, "qms": 4,
             "re_ohm": 4, "vas_m3": 0.002, "sd_m2": 0.005}
            for index in range(4)
        ],
        "enclosure_config": str(enclosure_path),
        "system_config": str(system_path) if system_path else None,
        "bill_of_materials": [
            {"item": f"Chosen part {index}", "quantity": 1, "price": 12.0 + index}
            for index in range(4)
        ],
        "fabrication": {
            "geometry_type": "rectangular",
            "external_dimensions_mm": [250, 900, 350],
            "net_volume_l": 40,
            "wall_thickness_mm": 18,
            "material": "user-selected birch plywood",
            "cutouts": [{"part_number": f"P-{index}", "diameter_mm": 120 + index}
                        for index in range(4)],
        },
        "measurement_metadata": measurement_metadata or {},
    }


class DesignWorkflowTests(unittest.TestCase):
    def test_incomplete_brief_returns_questions(self):
        plan = assess_brief({})
        self.assertEqual(plan["status"], "NEEDS_INPUT")
        self.assertTrue(plan["questions"])

    def test_blank_template_prompts_for_user_driver_data(self):
        template = json.loads((ROOT / "data/configs/design_brief_template.json").read_text(encoding="utf-8"))
        plan = assess_brief(template)
        self.assertEqual(plan["status"], "NEEDS_INPUT")
        self.assertNotIn("budget", plan["missing_inputs"])
        self.assertTrue(any("user-selected driver record" in question for question in plan["questions"]))

    def test_malformed_brief_sections_return_questions_not_tracebacks(self):
        plan = assess_brief({"schema_version": 1, "project_name": "x", "ways": 2,
                             "target": "30-20000 Hz", "fabrication": None})
        self.assertEqual(plan["status"], "NEEDS_INPUT")
        self.assertIn("target", plan["missing_inputs"])
        self.assertIn("fabrication", plan["missing_inputs"])

    def test_system_config_driver_mismatch_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            enclosure = root / "box.json"
            system = root / "system.json"
            enclosure.write_text(json.dumps({"driver_role": "way-0",
                                             "driver": {"part_number": "P-0"}}), encoding="utf-8")
            system.write_text(json.dumps({"branches": [
                {"name": f"branch-{index}", "part_number": f"OTHER-{index}"}
                for index in range(4)
            ]}), encoding="utf-8")
            plan = assess_brief(base_brief(enclosure, system))
        self.assertEqual(plan["status"], "NEEDS_INPUT")
        self.assertTrue(any("system_config branch" in item for item in plan["missing_inputs"]))

    def test_invalid_source_specific_ts_value_is_blocked(self):
        with tempfile.TemporaryDirectory() as folder:
            enclosure = Path(folder) / "box.json"
            enclosure.write_text(json.dumps({"driver_role": "way-0",
                                             "driver": {"part_number": "P-0"}}), encoding="utf-8")
            brief = base_brief(enclosure)
            brief["drivers"][0]["fs_hz"] = "unknown"
            plan = assess_brief(brief)
        self.assertEqual(plan["status"], "NEEDS_INPUT")
        self.assertIn("drivers[0].fs_hz", plan["missing_inputs"])

    def test_user_parts_prices_and_any_way_count_are_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            enclosure = Path(folder) / "box.json"
            enclosure.write_text(json.dumps({"driver_role": "way-0",
                                             "driver": {"part_number": "P-0"}}), encoding="utf-8")
            plan = assess_brief(base_brief(enclosure))
        self.assertEqual(plan["status"], "PROTOTYPE_ONLY")
        self.assertEqual(plan["ways"], 4)
        self.assertEqual(plan["drivers"][0]["name"], "Chosen driver 0")
        self.assertEqual(plan["drivers"][0]["price"], 22.5)
        self.assertTrue(plan["missing_measurements"])

    def test_attested_metadata_alone_never_marks_assessment_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            enclosure = Path(folder) / "box.json"
            enclosure.write_text(json.dumps({"driver_role": "way-0",
                                             "driver": {"part_number": "P-0"}}), encoding="utf-8")
            system_design = {"branches": [
                {"name": f"branch-{index}", "part_number": f"P-{index}"}
                for index in range(4)
            ]}
            metadata = {
                "on_baffle": True, "measurement_voltage_v": 2.83,
                "reference_distance_m": 1.0, "time_reference": "IR start",
                "microphone_orientation_degrees": 0,
            }
            brief = base_brief(enclosure, measurement_metadata=metadata)
            brief["system_design"] = system_design
            plan = assess_brief(brief)
        self.assertEqual(plan["status"], "PROTOTYPE_ONLY")
        self.assertFalse(plan["missing_inputs"])
        self.assertFalse(plan["missing_measurements"])

    def test_run_only_marks_ready_after_full_coverage_system_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            brief_path = root / "brief.json"
            output = root / "package"
            brief = base_brief(root / "unused.json", measurement_metadata={
                "on_baffle": True, "measurement_voltage_v": 2.83,
                "reference_distance_m": 1.0, "time_reference": "IR start",
                "microphone_orientation_degrees": 0,
            })
            brief.pop("enclosure_config")
            brief["box_design"] = {"kind": "sealed", "volume_m3": 0.04,
                                    "driver_role": "way-0"}
            brief["system_design"] = {"branches": [
                {"name": f"branch-{index}", "part_number": f"P-{index}"}
                for index in range(4)
            ]}
            brief_path.write_text(json.dumps(brief), encoding="utf-8")

            def fake_system_run(config_path, output_path):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text("frequency,measurement_covered\n1000,True\n", encoding="utf-8")
                return output_path

            with patch("scripts.system_design.design_workflow.run_system", side_effect=fake_system_run):
                plan = run(brief_path, output)
        self.assertEqual(plan["status"], "READY_FOR_PROTOTYPE_VALIDATION")
        self.assertEqual(plan["measured_coverage_fraction"], 1.0)

    def test_rectangular_volume_uses_user_displacement_ledger(self):
        with tempfile.TemporaryDirectory() as folder:
            enclosure = Path(folder) / "box.json"
            enclosure.write_text(json.dumps({"driver_role": "way-0",
                                             "driver": {"part_number": "P-0"}}), encoding="utf-8")
            brief = base_brief(enclosure)
            brief["fabrication"].pop("net_volume_l")
            brief["fabrication"]["displacements_l"] = {
                "drivers": 4.0, "port": 1.0, "braces": 0.5, "crossover": 0.2
            }
            plan = assess_brief(brief)
        self.assertIsNotNone(plan["fabrication_volume"])
        expected_gross = ((250 - 36) * (900 - 36) * (350 - 36)) / 1e6
        self.assertAlmostEqual(plan["fabrication_volume"]["gross_volume_l"], expected_gross)
        self.assertAlmostEqual(plan["fabrication_volume"]["net_volume_l"], expected_gross - 5.7)

    def test_custom_cad_net_volume_does_not_require_rectangular_dimensions(self):
        with tempfile.TemporaryDirectory() as folder:
            enclosure = Path(folder) / "box.json"
            enclosure.write_text(json.dumps({"driver_role": "way-0",
                                             "driver": {"part_number": "P-0"}}), encoding="utf-8")
            brief = base_brief(enclosure)
            fabrication = brief["fabrication"]
            fabrication.update(geometry_type="custom", geometry_reference="cad/custom_box.step",
                               net_volume_l=39.2)
            fabrication.pop("external_dimensions_mm")
            fabrication.pop("wall_thickness_mm")
            plan = assess_brief(brief)
        self.assertNotIn("fabrication.external_dimensions_mm", plan["missing_inputs"])
        self.assertNotIn("fabrication.wall_thickness_mm", plan["missing_inputs"])
        self.assertAlmostEqual(plan["fabrication"]["net_volume_l"], 39.2)

    def test_run_writes_auditable_incomplete_package(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            brief_path = root / "brief.json"
            output = root / "package"
            brief_path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
            plan = run(brief_path, output)
            self.assertEqual(plan["status"], "NEEDS_INPUT")
            self.assertTrue((output / "design_plan.json").is_file())
            self.assertTrue((output / "BUILD_NOTES.md").is_file())
            self.assertTrue((output / "inputs" / "design_brief.json").is_file())
            self.assertTrue((output / "design_report.md").is_file())
            self.assertTrue((output / "design_report.tex").is_file())
            self.assertTrue(plan["generated_report"]["temporary_context_removed"])
            report_text = (output / "design_report.md").read_text(encoding="utf-8")
            self.assertIn("readiness", report_text.lower())
            self.assertIn("Reference Sources", report_text)
            self.assertIsNotNone(plan["generated_report"]["latex"])
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["input_files"]), 1)
            self.assertFalse(manifest["portable"])
            self.assertIn("not bundled", manifest["reproduction_note"])

    def test_user_brief_generates_box_config_and_calculation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            brief_path = root / "brief.json"
            output = root / "package"
            brief = base_brief(root / "not-used-box-config.json")
            brief.pop("enclosure_config")
            brief["fabrication"].pop("net_volume_l")
            brief["fabrication"]["displacements_l"] = {
                "woofer": 0.4, "crossover": 0.2, "braces": 0.1
            }
            brief["drivers"] = [{
                "role": "woofer", "name": "User-selected 4-inch driver",
                "part_number": "USER-4", "source": "datasheet_ts",
                "quantity": 1, "series": 1, "parallel": 1,
                "fs_hz": 70, "qes": 0.45, "qms": 4.0, "re_ohm": 4.0,
                "vas_m3": 0.004, "sd_m2": 0.005, "le_h": 0.0003,
                "xmax_m": 0.004,
            }]
            brief["ways"] = 1
            brief["box_design"] = {"kind": "sealed", "volume_m3": None,
                                    "driver_role": "woofer"}
            brief["box_simulation"] = {
                "start_hz": 20, "stop_hz": 500, "points": 80,
                "reference_band_hz": [150, 300],
            }
            brief["measurement_metadata"] = {}
            brief_path.write_text(json.dumps(brief), encoding="utf-8")
            plan = run(brief_path, output)
            result_exists = (output / "results" / "low_frequency.csv").is_file()
        self.assertEqual(plan["status"], "PROTOTYPE_ONLY")
        self.assertAlmostEqual(plan["box_design"]["volume_m3"],
                       plan["fabrication_volume"]["net_volume_l"] / 1000)
        self.assertIn("results/low_frequency.csv", plan["generated_calculations"])
        self.assertTrue(result_exists)


if __name__ == "__main__":
    unittest.main()