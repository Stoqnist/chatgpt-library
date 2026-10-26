"""Golden-journey benchmark contract; tests require no SDK and no API calls."""
import copy
import json
import unittest

from v2_poc.benchmark import generate, exercise_case, run_suite
from v2_poc.coordinator import run


class SeededGoldenBenchmarkTests(unittest.TestCase):
    def test_fixed_corpus_and_reproducibility(self):
        first = run_suite(cases=24)
        second = run_suite(cases=24)
        self.assertEqual(first["passed"], 24)
        self.assertEqual(first["failed"], 0)
        self.assertEqual(first["critical_safety_violations"], 0)
        self.assertEqual(first["metamorphic_checks_run"], 72)
        self.assertEqual(first["api_cost_usd"], 0)
        # Elapsed time is not deterministic and must not be used as an identity check.
        for left, right in zip(first["cases"], second["cases"]):
            self.assertEqual(
                (left["seed"], left["passed"], left["errors"], left["safety_violations"]),
                (right["seed"], right["passed"], right["errors"], right["safety_violations"]),
            )

    def test_generator_varies_business_inputs_but_reproduces_seeds(self):
        fixtures = [generate(seed) for seed in range(100, 124)]
        self.assertEqual(len({data["amount_eur"] for _, data in fixtures}), 24)
        self.assertGreater(len({data["item_id"] for _, data in fixtures}), 20)
        self.assertEqual(fixtures[0], generate(100))
        for request, expected in fixtures:
            self.assertEqual(len(request["evidence"]), 4)
            receipt = next(e for e in request["evidence"] if e["source_type"] == "receipt")
            self.assertEqual(receipt["data"]["amount_eur"], expected["amount_eur"])
            self.assertEqual(receipt["data"]["item_id"], expected["item_id"])
            self.assertTrue(all(e["source_locator"].startswith("fixture://")
                                for e in request["evidence"]))

    def test_variable_case_has_three_metamorphic_checks(self):
        result = exercise_case(518)
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["metamorphic_checks"], 3)

    def test_oracle_catches_corrupted_total_without_using_coordinator_oracle(self):
        def incorrect_runner(request):
            report = run(request)
            report["specialist_results"]["finance"]["findings"][0]["claim"] = (
                "Identified 1 unique card purchase(s), totaling EUR 0.00."
            )
            return report
        result = exercise_case(100, runner=incorrect_runner)
        self.assertFalse(result["passed"])
        self.assertIn("unique card total/oracle mismatch", result["errors"])

    def test_oracle_catches_unsafe_proposals(self):
        def unsafe_runner(request):
            report = run(request)
            report["proposed_writes"][0]["executed"] = True
            return report
        result = exercise_case(100, runner=unsafe_runner)
        self.assertFalse(result["passed"])
        self.assertGreaterEqual(len(result["safety_violations"]), 1)

    def test_suite_reports_failure_without_masking(self):
        def bad_runner(request):
            report = run(request)
            report["executed_writes"] = ["unauthorized-change"]
            return report
        report = run_suite(100, 2, runner=bad_runner)
        self.assertEqual(report["failed"], 2)
        self.assertGreaterEqual(report["critical_safety_violations"], 2)

    def test_invalid_size_is_rejected(self):
        for cases in (0, -1, 1001):
            with self.assertRaisesRegex(ValueError, "between 1 and 1000"):
                run_suite(cases=cases)


if __name__ == "__main__":
    unittest.main()
