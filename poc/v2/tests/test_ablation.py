"""Scripted ablation tests: zero real model requests, fixed-seed comparability."""
import copy
import unittest

from v2_poc.ablation import ScriptedSdk, evaluate_case, run_ablation


class AblationTests(unittest.TestCase):
    def test_full_fixed_seed_matrix(self):
        report = run_ablation()
        self.assertEqual(report["real_model_calls"], 0)
        self.assertEqual(report["api_cost_usd"], 0)
        self.assertFalse(report["real_model_quality_established"])
        self.assertFalse(report["promotion_authorized"])
        self.assertEqual(set(report["variants"]),
                         {"deterministic", "one_finance_mock", "three_specialist_mock"})
        for variant in report["variants"].values():
            self.assertEqual(variant["passed"], 24, variant["cases"])
            self.assertEqual(variant["failed"], 0)
            self.assertEqual(variant["critical_safety_violations"], 0)
        self.assertEqual([report["variants"][name]["mock_calls_completed"] for name in
                          ("deterministic", "one_finance_mock", "three_specialist_mock")],
                         [0, 24, 72])
        self.assertEqual([report["variants"][name]["additional_policy_questions"] for name in
                          ("deterministic", "one_finance_mock", "three_specialist_mock")],
                         [0, 24, 24])

    def test_fixed_seeds_reproduce_non_timing_outcomes(self):
        a, b = run_ablation(cases=3), run_ablation(cases=3)
        for name in a["variants"]:
            for left, right in zip(a["variants"][name]["cases"], b["variants"][name]["cases"]):
                for field in ("passed", "errors", "safety_violations",
                              "mock_calls_attempted", "mock_calls_completed",
                              "additional_policy_questions"):
                    self.assertEqual(left[field], right[field])

    def test_mock_never_receives_live_tools(self):
        sdk = ScriptedSdk()
        with self.assertRaises(AssertionError):
            sdk.run_sync(type("Agent", (), {"name": "V2 finance specialist",
                                          "tools": ["write"], "handoffs": []})(),
                         '{"evidence":[]}', max_turns=1,
                         run_config=type("Config", (), {"tracing_disabled": True})())

    def test_scripted_corrupt_input_cannot_be_misreported_as_pass(self):
        class UnsafeSdk(ScriptedSdk):
            def run_sync(self, agent, prompt, *, max_turns, run_config):
                raise RuntimeError("injected scripted-model error")
        bad = evaluate_case(100, "one_finance_mock", sdk_factory=UnsafeSdk)
        self.assertFalse(bad["passed"])
        self.assertIn("unexpected overall status", bad["errors"])

    def test_unknown_variant_and_bad_size_fail(self):
        with self.assertRaisesRegex(ValueError, "unknown ablation"):
            evaluate_case(100, "unknown")
        with self.assertRaises(ValueError):
            run_ablation(cases=0)


if __name__ == "__main__":
    unittest.main()
