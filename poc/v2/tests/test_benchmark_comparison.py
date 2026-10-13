"""Offline comparator contract and release-gate regression tests."""
import copy
import unittest

from v2_poc.benchmark import run_suite
from v2_poc.compare_benchmarks import compare, load_report, validate_report


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
        candidate["passed"] -= 1
        result = compare(self.baseline, candidate)
        self.assertFalse(result["comparison_passed"])
        self.assertEqual(result["newly_failed_seeds"], [100])

    def test_critical_safety_blocks_even_without_failed_case(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["cases"][0]["passed"] = False
        candidate["cases"][0]["errors"] = ["unsafe"]
        candidate["cases"][0]["safety_violations"] = ["unsafe"]
        candidate["failed"] = 1
        candidate["passed"] -= 1
        candidate["critical_safety_violations"] = 1
        self.assertFalse(compare(self.baseline, candidate)["comparison_passed"])

    def test_unsupported_claims_never_treated_as_zero(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["unsupported_accepted_claims"] = 1
        self.assertEqual(compare(self.baseline, candidate)["unsupported_claim_gate"], "measured"
                         if self.baseline["unsupported_accepted_claims"] is not None else "not_measured")
        self.assertFalse(compare(self.baseline, candidate)["comparison_passed"])
        self.assertEqual(compare(self.baseline, candidate)["unsupported_claim_gate"], "candidate_measured_baseline_unknown")
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

    def test_report_detects_contradictory_safety_counts(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["cases"][0]["safety_violations"] = ["unsafe"]
        with self.assertRaisesRegex(ValueError, "passed case"):
            validate_report(candidate)
        candidate["cases"][0]["passed"] = False
        candidate["cases"][0]["errors"] = ["unsafe"]
        candidate["failed"] = 1
        candidate["passed"] -= 1
        with self.assertRaisesRegex(ValueError, "safety count contradicts"):
            validate_report(candidate)

    def test_report_rejects_passed_case_with_errors(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["cases"][0]["errors"] = ["ignored"]
        with self.assertRaisesRegex(ValueError, "passed case"):
            validate_report(candidate)

    def test_report_rejects_missing_metamorphic_coverage(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["cases"][0]["metamorphic_checks"] -= 1
        candidate["metamorphic_checks_run"] -= 1
        with self.assertRaisesRegex(ValueError, "incomplete metamorphic"):
            validate_report(candidate)

    def test_report_rejects_aggregate_metamorphic_mismatch(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["metamorphic_checks_run"] -= 1
        with self.assertRaisesRegex(ValueError, "metamorphic count contradicts"):
            validate_report(candidate)

    def test_changed_contract_revision_blocks_comparison(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["benchmark_contract"]["oracle_revision"] = "v2"
        with self.assertRaisesRegex(ValueError, "incompatible benchmark_contract"):
            compare(self.baseline, candidate)

    def test_commit_provenance_is_preserved(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["source_provenance"] = {
            "pr_head_sha": "a" * 40, "tested_merge_sha": None, "base_sha": "b" * 40
        }
        result = compare(self.baseline, candidate)
        self.assertEqual(result["candidate_provenance"], candidate["source_provenance"])
        candidate["source_provenance"]["tested_merge_sha"] = "c" * 40
        with self.assertRaisesRegex(ValueError, "source_commit contradicts"):
            validate_report(candidate)

    def test_timing_change_is_not_release_gate(self):
        candidate = copy.deepcopy(self.baseline)
        candidate["p50_case_elapsed_ms"] = 999999
        self.assertTrue(compare(self.baseline, candidate)["comparison_passed"])


if __name__ == "__main__":
    unittest.main()
