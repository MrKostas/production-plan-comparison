import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

import generate_demo
import packaging_data_pipeline as pipeline
from ikp_validation import evaluate_plans


class DemoTests(unittest.TestCase):
    def test_synthetic_files_reproduce_controls(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            with patch.object(generate_demo, "ROOT", root):
                generate_demo.generate()

            sources = root / "sources"
            reference = root / "reference"
            products = reference / "product_info.xlsx"
            site = reference / "site_line_info.xlsx"
            with (
                patch.object(
                    pipeline, "CURRENT_PLAN_DIRECTORY_PATH", sources / "current_version"
                ),
                patch.object(
                    pipeline,
                    "PREVIOUS_PLAN_DIRECTORY_PATH",
                    sources / "previous_version",
                ),
                patch.object(
                    pipeline, "FACTORY_SOURCE_FILE_PATH", sources / "factory-plan.xlsx"
                ),
                patch.object(pipeline, "PRODUCT_INFO_FILE_PATH", products),
                patch.object(pipeline, "SITE_LINE_INFO_FILE_PATH", site),
            ):
                plans = pipeline.build_unified_packaging_dataset()
                orders = pipeline.load_orders_data(sources / "orders апрель 2027.xlsx")
                self.assertEqual(
                    str(pipeline.validate_single_period(plans, orders)), "2027-04"
                )
                pipeline.validate_model_keys(plans, orders)
                with self.assertRaisesRegex(ValueError, "отсутствуют в справочнике"):
                    pipeline.validate_model_keys(
                        plans.assign(material="неизвестный"), orders
                    )

            self.assertEqual(list(plans.columns), pipeline.PACKAGING_COLUMNS)
            self.assertEqual(list(orders.columns), ["mass", "date", "material"])
            self.assertEqual((len(plans), len(orders)), (7, 2))
            lines = pd.read_excel(site, sheet_name="line").assign(siteKey=1)
            norms = pd.read_excel(site, sheet_name="performance_info")
            stops = pd.read_excel(sources / "mandatory_stops.xlsx")
            coverage = pd.read_csv(sources / "stop_coverage.csv")
            contract = pd.read_csv(reference / "ikp_comparison.csv")
            report = evaluate_plans(
                plans, orders, norms, stops, coverage, lines, contract, "2027-04"
            )

            controls = {
                "factory_plan": (20, 1, 2, 100, 0),
                "current_version": (20, 0.5, 2, 117.5, 0),
                "previous_version": (36, 0.5, 2, None, 6),
            }
            for name, expected in controls.items():
                values = report["scenarios"][name]
                self.assertEqual(
                    tuple(
                        values[key]
                        for key in (
                            "mass",
                            "dateMatch",
                            "series",
                            "score",
                            "statusCode",
                        )
                    ),
                    expected,
                )
            self.assertEqual(report["scenarios"]["current_version"]["rawHours"], 20)
            self.assertEqual(
                report["scenarios"]["previous_version"]["overloadedLineDays"], 1
            )
