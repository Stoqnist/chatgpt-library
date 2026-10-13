"""Fixed corpus checks for the zero-cost typed-signal counterfactual."""
import unittest
from v2_poc.rule_counterfactual import evaluate, run_probe

class RuleCounterfactualTests(unittest.TestCase):
    def test_fixed_cases_and_negative_controls(self):
        r=run_probe()
        self.assertEqual(r["pass_count"],26,r["cases"]+r["negative_controls"])
        self.assertEqual(r["failed_count"],0)
        self.assertEqual(r["critical_safety_violations"],0)
        self.assertEqual(r["rule_only_questions_total"],24)
        self.assertEqual(r["scripted_mock_questions_total"],24)
        self.assertEqual(r["unique_mock_questions_total"],0)
        self.assertEqual(r["real_model_calls"],0)
        self.assertFalse(r["model_incremental_value_established"])
        self.assertFalse(r["promotion_authorized"])

    def test_explicit_link_removes_question(self):
        r=evaluate(100,linked=True)
        self.assertTrue(r["passed"],r["errors"])
        self.assertEqual(r["rule_only_new_questions"],[])
        self.assertEqual(r["scripted_mock_new_questions"],[])

    def test_missing_identity_blocks_model_calls(self):
        r=evaluate(100,missing_bank_id=True)
        self.assertTrue(r["passed"],r["errors"])
        self.assertEqual(r["mock_calls"],0)
        self.assertEqual(r["rule_only_new_questions"],[])

    def test_alternate_seed(self):
        r=run_probe(seed_start=420,cases=4)
        self.assertEqual(r["failed_count"],0)
        self.assertEqual(r["unique_mock_questions_total"],0)

if __name__=="__main__":
    unittest.main()
