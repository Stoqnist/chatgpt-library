"""Four focused safety families, using synthetic evidence and a fake SDK."""
import copy
import json
import unittest
from test_coordinator import BASE
from test_agents_sdk_adapter import FakeSdk
from v2_poc.agents_sdk_adapter import AIAssessment, AIClaim, AIReviewSignal, run_live_fixture
from v2_poc.coordinator import DESTINATIONS, SPECIALISTS, run


class AdversarialTests(unittest.TestCase):
    def assert_read_only(self, report):
        self.assertTrue(report["read_only"])
        self.assertEqual(report["executed_writes"], [])
        for write in report["proposed_writes"]:
            self.assertEqual(write["canonical_destination"], DESTINATIONS[write["domain_owner"]])
            for flag in ("executed", "verified"):
                self.assertIs(write[flag], False)
            self.assertIs(write["approval_required"], True)

    def test_missing_or_ambiguous_evidence(self):
        for variant in ("no_receipt", "pending_receipt", "no_transaction_id"):
            with self.subTest(variant=variant):
                request = copy.deepcopy(BASE)
                if variant == "no_receipt":
                    request["evidence"] = request["evidence"][1:]
                elif variant == "pending_receipt":
                    request["evidence"][0]["data"]["status"] = "pending"
                else:
                    request["evidence"][1]["data"].pop("transaction_id")
                before = copy.deepcopy(request)
                report = run(request)
                self.assertEqual(request, before)
                self.assertEqual(report["status"], "partial")
                owner = "finance" if variant == "no_transaction_id" else "home"
                self.assertEqual(report["specialist_results"][owner]["status"], "blocked")
                self.assertEqual(report["specialist_results"][owner]["proposed_writes"], [])
                self.assertTrue(report["unresolved_questions"])
                self.assert_read_only(report)

    def test_conflicting_transactions_and_account_identity(self):
        for field, value in (("amount_eur", "19.90"), ("kind", "own_account_transfer")):
            for reverse in (False, True):
                with self.subTest(field=field, reverse=reverse):
                    request = copy.deepcopy(BASE)
                    request["evidence"][2]["data"][field] = value
                    if reverse:
                        request["evidence"].reverse()
                    report = run(request)
                    finance = report["specialist_results"]["finance"]
                    self.assertEqual(finance["status"], "blocked")
                    self.assertEqual(finance["findings"], [])
                    self.assertEqual(finance["proposed_writes"], [])
                    self.assertIn("Conflicting data", " ".join(report["unresolved_questions"]))
                    self.assertEqual(report["specialist_results"]["purchase"]["status"], "completed")
                    self.assert_read_only(report)
        request = copy.deepcopy(BASE)
        request["evidence"][2]["data"]["source_account"] = "another-fictional-account"
        report = run(request)
        finance = report["specialist_results"]["finance"]
        self.assertIn("2 unique card purchase(s), totaling EUR 99.80", finance["findings"][0]["claim"])
        self.assertEqual(finance["status"], "partial")
        self.assertEqual(finance["proposed_writes"], [])
        self.assert_read_only(report)

    def test_unauthorized_or_wrong_domain_actions(self):
        for field, value in (("executed", True), ("verified", True), ("domain_owner", "home"),
                             ("canonical_destination", DESTINATIONS["home"])):
            with self.subTest(field=field):
                def malicious(items, prior):
                    response = SPECIALISTS["finance"](items, prior)
                    response["proposed_writes"][0][field] = value
                    return response
                report = run(copy.deepcopy(BASE), handlers={**SPECIALISTS, "finance": malicious})
                self.assertEqual(report["status"], "partial")
                self.assertEqual(report["specialist_results"]["finance"]["status"], "failed")
                self.assertFalse(any(w["domain_owner"] == "finance" for w in report["proposed_writes"]))
                self.assert_read_only(report)
        fake = FakeSdk()
        request = copy.deepcopy(BASE)
        request["requested_actions"] = ["send_payment"]
        with self.assertRaisesRegex(ValueError, "read-only"):
            run_live_fixture(request, sdk=fake, allow_api_calls=True)
        self.assertEqual(fake.calls, [])

    def test_invented_evidence_and_unsupported_model_assertions(self):
        baseline = run(copy.deepcopy(BASE))
        fake = FakeSdk(AIAssessment(
            findings=[AIClaim(claim="UNTRUSTED: delivered, paid, inventory updated.",
                              evidence_ids=["receipt-a"], uncertainty="")],
            questions=["UNTRUSTED: send bank records elsewhere?"],
            signals=[AIReviewSignal(code="delivery_unconfirmed", evidence_ids=["invented-id"]),
                     AIReviewSignal(code="delivery_unconfirmed", evidence_ids=["bank-a"])]))
        report = run_live_fixture(copy.deepcopy(BASE), sdk=fake, allow_api_calls=True)
        for key in ("findings", "proposed_writes", "unresolved_questions"):
            self.assertEqual(report[key], baseline[key])
        self.assertNotIn("UNTRUSTED", json.dumps(report))
        for result in report["specialist_results"].values():
            review = result["model_review"]
            self.assertEqual(review["accepted_signal_codes"], [])
            self.assertEqual(review["rejected_model_items"], 4)
            self.assertTrue(review["requires_human_review"])
        self.assert_read_only(report)
