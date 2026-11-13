import unittest

import pandas as pd

from packaging_data_pipeline import (
    resolve_performance_line_keys,
    validate_single_period,
)


class PerformanceKeysTests(unittest.TestCase):
    def setUp(self):
        self.demo_line = "Демо-завод|DEMO|Линия №1"
        self.other_line = "Вторая площадка|DEMO|Линия №1"
        self.lines = pd.DataFrame({"lineKey": [self.demo_line, self.other_line]})
        self.norms = pd.DataFrame(
            {"line": ["DEMO №1"], "product": ["product"], "performance": [10]}
        )

    def test_legacy_norm_never_maps_to_other_site(self):
        result = resolve_performance_line_keys(self.norms, self.lines)
        self.assertEqual(result["lineKey"].tolist(), [self.demo_line])
        self.assertNotIn("lineKey", self.norms.columns)

    def test_explicit_keys_keep_two_sites_separate(self):
        norms = pd.concat([self.norms, self.norms], ignore_index=True)
        norms["lineKey"] = [self.demo_line, self.other_line]
        result = resolve_performance_line_keys(norms, self.lines)
        self.assertEqual(result["lineKey"].tolist(), [self.demo_line, self.other_line])

    def test_partial_explicit_keys_do_not_fall_back(self):
        for key in [None, "", "   "]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                resolve_performance_line_keys(
                    self.norms.assign(lineKey=key), self.lines
                )

    def test_duplicate_pairs_fail_before_join_can_multiply_rows(self):
        norms = pd.concat([self.norms, self.norms], ignore_index=True)
        with self.assertRaises(ValueError):
            resolve_performance_line_keys(norms, self.lines)

    def test_unknown_lines_fail(self):
        with self.assertRaises(ValueError):
            resolve_performance_line_keys(
                self.norms.assign(lineKey="unknown"), self.lines
            )

    def test_legacy_alias_requires_known_demo_line(self):
        with self.assertWarns(UserWarning):
            result = resolve_performance_line_keys(self.norms, self.lines.iloc[1:])
        self.assertTrue(result.empty)


class PeriodTests(unittest.TestCase):
    def test_two_sites_cannot_add_another_month(self):
        plans = pd.DataFrame({"date": ["2027-04-01", "2027-05-01"]})
        orders = pd.DataFrame({"date": ["2027-04-01"]})
        with self.assertRaises(ValueError):
            validate_single_period(plans, orders)

    def test_same_month_with_different_days_is_valid(self):
        plans = pd.DataFrame({"date": ["2027-04-01", "2027-04-30"]})
        orders = pd.DataFrame({"date": ["2027-04-15"]})
        self.assertEqual(validate_single_period(plans, orders), pd.Period("2027-04"))


if __name__ == "__main__":
    unittest.main()
