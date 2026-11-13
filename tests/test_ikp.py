import re
import unittest
from pathlib import Path

import pandas as pd

from ikp_validation import evaluate_plans, relative_components


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.plans = pd.DataFrame(
            [
                [s, "L1", p, "2027-04-01", 10.0]
                for s in ("factory_plan", "candidate")
                for p in ("A", "B")
            ],
            columns=["scenarioKey", "lineKey", "material", "date", "mass"],
        )
        self.orders = pd.DataFrame(
            {"date": ["2027-04-01"] * 2, "material": ["A", "B"], "mass": [10.0] * 2}
        )
        self.norms = pd.DataFrame(
            [
                [line, product, 23.0, 23.0]
                for line in ("L1", "L2")
                for product in ("A", "B", "C")
            ],
            columns=["lineKey", "product", "performance", "workingHours"],
        )
        self.stops = pd.DataFrame(
            columns=[
                "stopID",
                "scenarioKey",
                "lineKey",
                "date",
                "stopType",
                "durationHours",
            ]
        )
        self.coverage = pd.DataFrame(
            [
                [s, line, "2027-04-01", True]
                for s in ("factory_plan", "candidate")
                for line in ("L1", "L2")
            ],
            columns=["scenarioKey", "lineKey", "month", "isComplete"],
        )
        self.lines = pd.DataFrame({"lineKey": ["L1", "L2"], "siteKey": [1, 1]})
        self.contract = pd.DataFrame(
            [
                [
                    s,
                    1,
                    "2027-04-01",
                    "comparison-v1",
                    "ikp-relative-v1",
                    True,
                    True,
                    True,
                ]
                for s in ("factory_plan", "candidate")
            ],
            columns=[
                "scenarioKey",
                "siteKey",
                "month",
                "comparisonSetID",
                "methodVersion",
                "isProvided",
                "referenceApproved",
                "inputsConfirmed",
            ],
        )

    def run_index(self, **kwargs):
        report = evaluate_plans(
            self.plans,
            self.orders,
            self.norms,
            self.stops,
            self.coverage,
            self.lines,
            self.contract,
            "2027-04",
            **kwargs,
        )
        return report["scenarios"]

    def stop(self, hours, day="2027-04-01", line="L1"):
        self.stops = pd.DataFrame(
            [
                [i, s, line, day, "wash", hours]
                for i, s in enumerate(("factory_plan", "candidate"))
            ],
            columns=self.stops.columns,
        )

    def test_identical_reference_is_exactly_100(self):
        result = self.run_index()
        for value in result.values():
            self.assertEqual(value["score"], 100)
            self.assertEqual(value["lineDays"], 1)
            self.assertEqual(value["series"], 2)
            self.assertEqual(value["adjustment"], 0)

    def test_order_and_split_invariance(self):
        before = self.run_index()
        self.plans["mass"] /= 2
        self.plans = pd.concat([self.plans, self.plans]).sample(frac=1, random_state=42)
        after = self.run_index()
        for key in before:
            for metric in (
                "lineDays",
                "series",
                "mass",
                "score",
                "volumeError",
                "rawHours",
            ):
                self.assertEqual(before[key][metric], after[key][metric])

    def test_missing_date_match_is_zero_not_missing(self):
        self.plans.loc[self.plans.scenarioKey.eq("candidate"), "date"] = "2027-04-02"
        value = self.run_index()["candidate"]
        self.assertEqual(value["dateMatch"], 0)
        self.assertEqual(value["score"], 75)

    def test_calendar_gap_does_not_break_series(self):
        self.plans.loc[self.plans.material.eq("B"), "date"] = "2027-04-03"
        extra = self.plans.loc[self.plans.material.eq("B")].assign(
            date="2027-04-07", mass=1
        )
        self.plans = pd.concat([self.plans, extra], ignore_index=True)
        self.assertEqual(self.run_index()["candidate"]["series"], 2)

    def test_volume_changes_do_not_cancel(self):
        candidate = self.plans.scenarioKey.eq("candidate")
        self.plans.loc[candidate & self.plans.material.eq("A"), "mass"] = 9
        self.plans.loc[candidate & self.plans.material.eq("B"), "mass"] = 11
        value = self.run_index()["candidate"]
        self.assertAlmostEqual(value["volumeError"], 0.1)
        self.assertEqual(value["productsOutsideTolerance"], 2)
        self.assertEqual(value["score"], 90)

    def test_tolerance_boundary_and_numerical_epsilon(self):
        mask = self.plans.scenarioKey.eq("candidate") & self.plans.material.eq("A")
        for delta, outside in ((0.5, 0), (0.5000005, 0), (0.500002, 1)):
            with self.subTest(delta=delta):
                self.plans.loc[mask, "mass"] = 10 + delta
                self.assertEqual(
                    self.run_index()["candidate"]["productsOutsideTolerance"], outside
                )

    def test_missing_product_and_extra_product_trigger_cap(self):
        self.plans.loc[
            self.plans.scenarioKey.eq("candidate") & self.plans.material.eq("A"),
            "material",
        ] = "C"
        value = self.run_index()["candidate"]
        self.assertEqual(value["productsOutsideTolerance"], 2)
        self.assertEqual(value["statusCode"], 7)
        self.assertLessEqual(value["score"], 100)

    def test_cap_applies_when_compactness_would_reward_underproduction(self):
        self.norms["performance"] = 230
        self.plans = pd.concat(
            [
                self.plans,
                self.plans.loc[self.plans.scenarioKey.eq("factory_plan")].assign(
                    date="2027-04-02", mass=1
                ),
            ],
            ignore_index=True,
        )
        value = self.run_index()["candidate"]
        self.assertEqual(value["statusCode"], 7)
        self.assertEqual(value["score"], 100)
        self.assertLess(value["adjustment"], 0)

    def test_empty_declared_plan_is_zero(self):
        self.plans = self.plans.loc[self.plans.scenarioKey.eq("factory_plan")]
        value = self.run_index()["candidate"]
        self.assertEqual(value["statusCode"], 8)
        self.assertEqual(value["score"], 0)
        self.assertEqual(value["delta"], -100)

    def test_absent_delivery_is_not_empty_plan(self):
        self.contract.loc[self.contract.scenarioKey.eq("candidate"), "isProvided"] = (
            False
        )
        value = self.run_index()["candidate"]
        self.assertEqual(value["statusCode"], 3)
        self.assertIsNone(value["score"])

    def test_unapproved_or_absent_reference_blocks_all_scores(self):
        for field in ("isProvided", "referenceApproved"):
            self.contract.loc[self.contract.scenarioKey.eq("factory_plan"), field] = (
                False
            )
            self.assertTrue(all(v["score"] is None for v in self.run_index().values()))

    def test_missing_norm_cannot_be_hidden_by_sum(self):
        self.norms.loc[self.norms["product"].eq("A"), "performance"] = float("nan")
        value = self.run_index()["candidate"]
        self.assertIsNone(value["score"])
        self.assertIsNone(value["rawHours"])
        self.assertEqual(value["missingNorms"], 1)

    def test_incomplete_inactive_line_blocks_index(self):
        self.coverage = self.coverage.loc[
            ~(
                self.coverage.scenarioKey.eq("candidate")
                & self.coverage.lineKey.eq("L2")
            )
        ]
        self.assertIsNone(self.run_index()["candidate"]["score"])

    def test_products_must_share_line_daily_fund(self):
        self.plans.loc[self.plans.scenarioKey.eq("candidate"), "mass"] = 15
        value = self.run_index()["candidate"]
        self.assertEqual(value["rawHours"], 30)
        self.assertEqual(value["overloadedLineDays"], 1)
        self.assertEqual(value["statusCode"], 6)
        self.assertIsNone(value["score"])

    def test_overload_not_offset_by_free_days(self):
        self.stop(24, day="2027-04-10", line="L2")
        self.assertTrue(all(v["score"] is None for v in self.run_index().values()))

    def test_stops_do_not_increase_score(self):
        self.stop(1)
        first = self.run_index()["candidate"]["score"]
        self.stop(3)
        self.assertEqual(self.run_index()["candidate"]["score"], first)
        self.stop(4)
        self.assertIsNone(self.run_index()["candidate"]["score"])

    def test_different_stop_inputs_block_comparison(self):
        self.stop(1)
        self.stops.loc[self.stops.scenarioKey.eq("candidate"), "date"] = "2027-04-02"
        value = self.run_index()["candidate"]
        self.assertEqual(value["statusCode"], 4)
        self.assertIsNone(value["score"])

    def test_stop_ids_do_not_define_comparability(self):
        self.stop(1)
        self.stops["stopID"] += 99
        self.assertEqual(self.run_index()["candidate"]["score"], 100)

    def test_repeated_stop_rejected(self):
        self.stop(1)
        self.stops = pd.concat([self.stops, self.stops.iloc[[0]].assign(stopID=99)])
        with self.assertRaises(ValueError):
            self.run_index()

    def test_context_or_missing_orders_blocks_score(self):
        self.assertEqual(
            self.run_index(context_valid=False)["candidate"]["statusCode"], 1
        )
        self.orders = self.orders.iloc[:0]
        self.assertIsNone(self.run_index()["candidate"]["score"])

    def test_contract_version_and_comparison_set_are_enforced(self):
        mask = self.contract.scenarioKey.eq("candidate")
        self.contract.loc[mask, "comparisonSetID"] = "other"
        self.assertEqual(self.run_index()["candidate"]["statusCode"], 4)
        self.contract.loc[mask, "methodVersion"] = "unapproved-v2"
        self.assertEqual(self.run_index()["candidate"]["statusCode"], 3)

    def test_new_scenario_cannot_change_existing_scores(self):
        before = self.run_index()
        self.plans = pd.concat(
            [
                self.plans,
                self.plans.loc[self.plans.scenarioKey.eq("candidate")].assign(
                    scenarioKey="fourth"
                ),
            ]
        )
        self.coverage = pd.concat(
            [
                self.coverage,
                self.coverage.loc[self.coverage.scenarioKey.eq("candidate")].assign(
                    scenarioKey="fourth"
                ),
            ]
        )
        self.contract = pd.concat(
            [
                self.contract,
                self.contract.loc[self.contract.scenarioKey.eq("candidate")].assign(
                    scenarioKey="fourth"
                ),
            ]
        )
        after = self.run_index()
        for s in before:
            self.assertEqual(before[s], after[s])

    def test_malformed_inputs_fail_fast(self):
        for field, invalid in (
            ("mass", float("nan")),
            ("date", "2027-05-01"),
            ("lineKey", "unknown"),
        ):
            original = self.plans.copy()
            self.plans.loc[0, field] = invalid
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_index()
            self.plans = original

    def test_missing_contract_row_blocks_current_plan(self):
        self.contract = self.contract.loc[self.contract.scenarioKey.eq("factory_plan")]
        self.assertEqual(self.run_index()["candidate"]["statusCode"], 3)


class FormulaTests(unittest.TestCase):
    def test_examples(self):
        for c, d, e, expected in (
            (100, 0.8, 0, 100),
            (90, 0.8, 0, 106),
            (90, 0.7, 0, 103.5),
            (100, 0.8, 0.05, 95),
        ):
            parts = relative_components(c, d, 20, 100, 0.8, 20, e)
            self.assertAlmostEqual(100 + sum(parts.values()), expected)

    def test_zero_series_does_not_divide_by_zero(self):
        self.assertEqual(relative_components(1, 0, 0, 1, 0, 0, 0)["series"], 0)

    def test_bounds_for_valid_inputs(self):
        for c in (0, 50, 100, 500):
            for d in (0, 0.5, 1):
                for n in (0, 10, 20, 100):
                    for error in (0, 0.05, 1, 2):
                        raw = max(
                            0,
                            100
                            + sum(
                                relative_components(
                                    c, d, n, 100, 0.8, 20, error
                                ).values()
                            ),
                        )
                        self.assertGreaterEqual(raw, 0)
                        self.assertLessEqual(raw, 200)

    def test_sensitivity_does_not_mutate_default_weights(self):
        default = relative_components(90, 0.7, 20, 100, 0.8, 20, 0)
        other = relative_components(90, 0.7, 20, 100, 0.8, 20, 0, (0.5, 0.35, 0.15))
        self.assertNotEqual(default, other)
        self.assertEqual(default, relative_components(90, 0.7, 20, 100, 0.8, 20, 0))


class DaxCompatibilityTests(unittest.TestCase):
    """Static guards for observed Excel parser errors, not a DAX engine."""

    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / "model/measures.dax"
        cls.dax = path.read_text(encoding="utf-8")

    def test_isfiltered_uses_only_column_references(self):
        arguments = re.findall(r"\bISFILTERED\s*\(\s*([^()]+?)\s*\)", self.dax)
        self.assertTrue(arguments)
        for argument in arguments:
            with self.subTest(argument=argument):
                self.assertRegex(argument, r"^[A-Za-z_][A-Za-z_0-9]*\[[^\]]+\]$")

    def test_ikp_variables_do_not_collide_with_function_names(self):
        block = self.dax.split("-- IKP relative v1", 1)[1]
        variables = re.findall(r"\bVAR\s+([A-Za-z_][A-Za-z_0-9]*)", block)
        self.assertTrue(variables)
        self.assertTrue(all(name.startswith("__Ikp") for name in variables))


if __name__ == "__main__":
    unittest.main()
