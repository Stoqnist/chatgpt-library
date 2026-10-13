"""Offline comparator contract and release-gate regression tests."""
import copy
import unittest

from v2_poc.benchmark import run_suite
from v2_poc.compare_benchmarks import compare


class BenchmarkComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.baseline = run_suite()

    def test_identical_reports_pass_without_authorizing_promotion(self):
        result = compare(self.baseline, copy.deepcopy(self.baseline))
        self.assertTrue(result["comparison_passed"])
        self.assertFalse(result["promotion_authorized"])
        self.assertEqual(result["seed_count"], 24)
        self.assertEqual(result["unsupported_claim_gate"], "not_measured")

    def test_new_case_failure_blocks(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["cases"][0]["passed"] = False
        candidate["cases"][0]["errors"] = ["synthetic regression"]
        candidate["failed"] = 1
        result = compare(self.baseline, candidate)
        self.assertFalse(result["comparison_passed"])
        self.assertEqual(result["newly_failed_seeds"], [100])

    def test_critical_safety_blocks_even_without_failed_case(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["critical_safety_violations"] = 1
        self.assertFalse(compare(self.baseline, candidate)["comparison_passed"])

    def test_unsupported_claims_never_treated_as_zero(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["unsupported_accepted_claims"] = 1
        self.assertEqual(compare(self.baseline, candidate)["unsupported_claim_gate"], "measured"
                         if self.baseline["unsupported_accepted_claims"] is not None else "not_measured")
        self.assertTrue(compare(self.baseline, candidate)["comparison_passed"])
        base = copy.deepcopy(self.baseline)
        base["unsupported_accepted_claims"] = 0
        self.assertFalse(compare(base, candidate)["comparison_passed"])

    def test_rejects_changed_seed_corpus_and_configuration(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["cases"][0]["seed"] = 999
        with self.assertRaisesRegex(ValueError, "seed corpus"):
            compare(self.baseline, candidate)
        candidate = copy.deepcopy(self.baseline)
        candidate["configuration"] = "model_backed"
        with self.assertRaisesRegex(ValueError, "incompatible"):
            compare(self.baseline, candidate)

    def test_timing_change_is_not_release_gate(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["p50_case_elapsed_ms"] = 999999
        self.assertTrue(compare(self.baseline, candidate)["comparison_passed"])


if __name__ == "__main__":
    unittest.main()
