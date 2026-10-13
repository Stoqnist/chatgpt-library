import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from v2_poc.agents_sdk_adapter import (
    AIClaim, AIReviewSignal, AIAssessment, AgentsSDKAdapter, run_live_fixture,
)

BASE = json.loads((Path(__file__).resolve().parents[1] / "fixtures/purchase.json").read_text())


class FakeSdk:
    def __init__(self, assessment=None, fail_domain=None):
        self.calls = []
        self.assessment = assessment
        self.fail_domain = fail_domain
        self.Runner = SimpleNamespace(run_sync=self.run_sync)

    def Agent(self, **kwargs):
        self.calls.append({"event": "agent", **kwargs})
        return SimpleNamespace(**kwargs)

    def RunConfig(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def ModelSettings(self, **kwargs):
        return SimpleNamespace(**kwargs)

    def run_sync(self, agent, prompt, *, max_turns, run_config):
        assert run_config.tracing_disabled is True
        assert max_turns == 1
        assert agent.tools == [] and agent.handoffs == []
        payload = json.loads(prompt)
        self.calls.append({"event": "run", "domain": agent.name, "input": payload})
        if agent.name == self.fail_domain:
            raise RuntimeError("synthetic model failure")
        assessment = self.assessment or AIAssessment(findings=[], questions=[])
        return SimpleNamespace(final_output=assessment)


class AdapterTests(unittest.TestCase):
    def test_no_api_calls_without_explicit_authorization(self):
        fake = FakeSdk()
        with self.assertRaisesRegex(PermissionError, "explicit"):
            run_live_fixture(BASE, sdk=fake)
        self.assertEqual(fake.calls, [])

    def test_three_sdk_calls_preserve_authoritative_finance_total_and_read_only(self):
        mock = FakeSdk()
        report = run_live_fixture(copy.deepcopy(BASE), sdk=mock, allow_api_calls=True)
        self.assertEqual(report["status"], "completed")
        self.assertEqual(report["execution_mode"], "mock_sdk")
        self.assertTrue(report["simulation"])
        self.assertEqual(report["model_calls_attempted"], 3)
        self.assertEqual(report["model_calls_completed"], 3)
        self.assertEqual(len([x for x in mock.calls if x["event"] == "run"]), 3)
        self.assertIn("EUR 49.90", report["specialist_results"]["finance"]["findings"][0]["claim"])
        self.assertEqual(report["executed_writes"], [])
        self.assertTrue(all(not w["executed"] and not w["verified"] for w in report["proposed_writes"]))

    def test_scope_and_home_dependency_are_preserved(self):
        mock = FakeSdk()
        run_live_fixture(copy.deepcopy(BASE), sdk=mock, allow_api_calls=True)
        sent = [x for x in mock.calls if x["event"] == "run"]
        self.assertEqual([len(x["input"]["evidence"]) for x in sent], [1, 4, 1])
        self.assertIsNone(sent[0]["input"]["prior_purchase_result"])
        self.assertIsNone(sent[1]["input"]["prior_purchase_result"])
        self.assertEqual(sent[2]["input"]["prior_purchase_result"]["domain_owner"], "purchase")

    def test_free_text_claims_are_quarantined_even_with_real_evidence_id(self):
        mock = FakeSdk(AIAssessment(findings=[AIClaim(
            claim="The receipt proves physical possession and bank reconciliation.",
            evidence_ids=["receipt-a"], uncertainty=""
        )], questions=["Invented free-form question?"]))
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["model_calls_completed"], 1)
        self.assertEqual(len(result["findings"]), 1)  # deterministic only
        self.assertNotIn("proves physical possession", json.dumps(result))
        review = result["specialist_results"]["purchase"]["model_review"]
        self.assertEqual(review["rejected_model_items"], 2)
        self.assertEqual(review["free_text_claims_accepted"], 0)
        self.assertTrue(review["requires_human_review"])

    def test_unknown_evidence_reference_cannot_affect_result(self):
        mock = FakeSdk(AIAssessment(signals=[AIReviewSignal(
            code="delivery_unconfirmed", evidence_ids=["invented-id"]
        )]))
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["specialist_results"]["purchase"]["model_review"]["rejected_model_items"], 1)
        self.assertEqual(result["unresolved_questions"], [])
        self.assertEqual(result["executed_writes"], [])

    def test_typed_delivery_signal_is_checked_and_policy_authored(self):
        mock = FakeSdk(AIAssessment(signals=[AIReviewSignal(
            code="delivery_unconfirmed", evidence_ids=["receipt-a"]
        )]))
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["unresolved_questions"], ["Was desk-lamp actually received into the household?"])
        self.assertEqual(result["specialist_results"]["purchase"]["model_review"]["accepted_signal_codes"],
                         ["delivery_unconfirmed"])

    def test_receipt_payment_relation_requires_explicit_id(self):
        mock = FakeSdk(AIAssessment(signals=[AIReviewSignal(
            code="receipt_payment_link_unverified", evidence_ids=["receipt-a", "bank-a"]
        )]))
        request = copy.deepcopy(BASE)
        request["domains"] = ["finance"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["unresolved_questions"], ["Does card transaction T-001 belong to receipt R-123?"])
        request["evidence"][0]["data"]["transaction_id"] = "T-001"
        resolved = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(resolved["unresolved_questions"], [])
        self.assertEqual(resolved["specialist_results"]["finance"]["model_review"]["rejected_model_items"], 1)

    def test_failed_agent_keeps_other_domains_and_reports_partial(self):
        mock = FakeSdk(fail_domain="V2 finance specialist")
        result = run_live_fixture(copy.deepcopy(BASE), sdk=mock, allow_api_calls=True)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["model_calls_attempted"], 3)
        self.assertEqual(result["model_calls_completed"], 2)
        self.assertEqual(result["specialist_results"]["purchase"]["status"], "completed")
        self.assertEqual(result["specialist_results"]["finance"]["status"], "failed")
        self.assertEqual(result["executed_writes"], [])

    def test_blocked_deterministic_evidence_skips_model_call(self):
        mock = FakeSdk()
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        request["evidence"] = [r for r in request["evidence"] if r["source_type"] != "receipt"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["model_calls_attempted"], 0)
        self.assertTrue(result["simulation"])
        self.assertEqual(result["execution_mode"], "deterministic_fallback")

    def test_no_api_calls_when_preflight_rejects_nonfixture_or_write_action(self):
        for field, value in [("requested_actions", ["send_payment"]),
                             ("source", "https://bank.example/account")]:
            mock = FakeSdk()
            request = copy.deepcopy(BASE)
            if field == "source":
                request["evidence"][0]["source_locator"] = value
            else:
                request[field] = value
            with self.assertRaisesRegex(ValueError, "read-only|synthetic fixture"):
                run_live_fixture(request, sdk=mock, allow_api_calls=True)
            self.assertEqual(mock.calls, [])

    def test_no_full_bank_data_to_purchase_and_home(self):
        mock = FakeSdk()
        request = copy.deepcopy(BASE)
        request["evidence"].append({
            "evidence_id": "bank-sensitive", "source_type": "bank_transaction",
            "source_locator": "fixture://bank-private", "observed_at": "2026-10-01T00:00:00Z",
            "data": {"source_account": "acct", "transaction_id": "SENSITIVE_TAG_XY123",
                     "amount_eur": "0", "kind": "own_account_transfer"},
        })
        run_live_fixture(request, sdk=mock, allow_api_calls=True)
        for item in [x for x in mock.calls if x["event"] == "run"]:
            if item["domain"] in ("V2 purchase specialist", "V2 home specialist"):
                self.assertNotIn("SENSITIVE_TAG_XY123", json.dumps(item["input"]))

    def test_oversized_fixture_stops_before_model_call(self):
        mock = FakeSdk()
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        request["evidence"][0]["data"]["untrusted_text"] = "a" * 20000
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["model_calls_attempted"], 0)
        self.assertEqual(mock.calls, [])

    def test_model_free_form_question_is_quarantined(self):
        repeated = "Was the desk-lamp actually received and physically located within the household?"
        mock = FakeSdk(AIAssessment(questions=[repeated]))
        result = run_live_fixture(copy.deepcopy(BASE), sdk=mock, allow_api_calls=True)
        self.assertEqual(result["model_calls_completed"], 3)
        self.assertEqual(len(result["specialist_results"]["home"]["unresolved_questions"]), 1)
        self.assertEqual(len(result["unresolved_questions"]), 1)
        self.assertEqual(result["unresolved_questions"][0], "Was desk-lamp actually received into the household?")
        self.assertEqual(result["specialist_results"]["home"]["model_review"]["rejected_model_items"], 1)

    def test_specialist_instructions_prohibit_unproven_transaction_linkage(self):
        mock = FakeSdk()
        run_live_fixture(copy.deepcopy(BASE), sdk=mock, allow_api_calls=True)
        agents = [entry for entry in mock.calls if entry["event"] == "agent"]
        self.assertEqual(len(agents), 3)
        for agent in agents:
            self.assertIn("Matching amounts alone do not prove", agent["instructions"])
            self.assertIn("Do not paraphrase", agent["instructions"])

    def test_no_model_key_or_sdk_required_for_offline_simulation(self):
        from v2_poc.coordinator import run
        self.assertTrue(run(BASE)["simulation"])


if __name__ == "__main__":
    unittest.main()
