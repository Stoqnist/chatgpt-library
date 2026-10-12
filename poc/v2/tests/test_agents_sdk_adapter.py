import copy
import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from v2_poc.agents_sdk_adapter import (
    AIClaim, AIAssessment, AgentsSDKAdapter, run_live_fixture,
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

    def test_model_findings_are_inferred_and_bounded(self):
        mock = FakeSdk(AIAssessment(findings=[AIClaim(
            claim="Receipt alone does not prove delivery.",
            evidence_ids=["receipt-a"], uncertainty="Physical receipt was not observed."
        )], questions=[]))
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["model_calls_completed"], 1)
        last = result["findings"][-1]
        self.assertEqual(last["provenance"], "inferred")
        self.assertEqual(last["evidence_ids"], ["receipt-a"])
        self.assertIn("Physical receipt", last["limitation"])

    def test_fake_evidence_reference_is_rejected_without_any_write(self):
        mock = FakeSdk(AIAssessment(findings=[AIClaim(
            claim="Unverified claim", evidence_ids=["made-up-id"], uncertainty="unknown"
        )], questions=[]))
        request = copy.deepcopy(BASE)
        request["domains"] = ["finance"]
        result = run_live_fixture(request, sdk=mock, allow_api_calls=True)
        self.assertEqual(result["status"], "partial")
        self.assertEqual(result["failures_or_blocks"], ["finance"])
        self.assertEqual(result["specialist_results"]["finance"]["status"], "failed")
        self.assertEqual(result["proposed_writes"], [])
        self.assertEqual(result["model_calls_completed"], 0)

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

    def test_no_model_key_or_sdk_required_for_offline_simulation(self):
        from v2_poc.coordinator import run
        self.assertTrue(run(BASE)["simulation"])


if __name__ == "__main__":
    unittest.main()
