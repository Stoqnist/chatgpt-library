"""Scripted ablation tests: zero real model requests, fixed-seed comparability."""
import copy
import json
import unittest
from types import SimpleNamespace

from v2_poc.agents_sdk_adapter import AIAssessment, AIReviewSignal

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

    def test_unscoped_signal_is_rejected_without_new_question_or_writes(self):
        class UnscopedSdk(ScriptedSdk):
            def run_sync(self, agent, prompt, *, max_turns, run_config):
                super().run_sync(agent, prompt, max_turns=max_turns, run_config=run_config)
                return SimpleNamespace(final_output=AIAssessment(signals=[
                    AIReviewSignal(code="receipt_payment_link_unverified",
                                   evidence_ids=["invented-receipt", "invented-bank"])
                ]))
        result = evaluate_case(100, "one_finance_mock", sdk_factory=UnscopedSdk)
        self.assertFalse(result["passed"])
        self.assertIn("scripted model output not fully evidence-gated", result["errors"])
        self.assertEqual(result["additional_policy_questions"], 0)
        self.assertEqual(result["missing_baseline_questions"], [])
        self.assertEqual(result["safety_violations"], ["scripted model output not fully evidence-gated"])

    def test_failed_sdk_is_reported_without_cross_domain_loss(self):
        class FailedSdk(ScriptedSdk):
            def run_sync(self, agent, prompt, *, max_turns, run_config):
                if agent.name == "V2 finance specialist":
                    raise RuntimeError("injected finance error")
                return super().run_sync(agent, prompt, max_turns=max_turns,
                                        run_config=run_config)
        result = evaluate_case(100, "three_specialist_mock", sdk_factory=FailedSdk)
        self.assertFalse(result["passed"])
        self.assertIn("unexpected overall status", result["errors"])
        self.assertEqual(result["mock_calls_completed"], 2)
        self.assertEqual(result["additional_policy_questions"], 0)

    def test_candidate_timing_excludes_reference_validation(self):
        import unittest.mock as mock
        from v2_poc import ablation
        original = ablation.check_result

        def expensive_validation(candidate, expected):
            # Avoid real sleeping; ensure the check occurs after the measured call.
            assert candidate["status"] == "completed"
            return original(candidate, expected)
        with mock.patch.object(ablation, "check_result", side_effect=expensive_validation) as checked:
            result = evaluate_case(100, "deterministic")
        self.assertTrue(result["passed"], result["errors"])
        self.assertIsInstance(result["candidate_elapsed_ms"], float)
        self.assertEqual(checked.call_count, 1)

    def test_existing_questions_are_preserved(self):
        result = evaluate_case(100, "three_specialist_mock")
        self.assertTrue(result["passed"], result["errors"])
        self.assertEqual(result["missing_baseline_questions"], [])

    def test_unknown_variant_and_bad_size_fail(self):
        with self.assertRaisesRegex(ValueError, "unknown ablation"):
            evaluate_case(100, "unknown")
        with self.assertRaises(ValueError):
            run_ablation(cases=0)


if __name__ == "__main__":
    unittest.main()
