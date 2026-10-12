import copy
import json
import unittest
from pathlib import Path

from v2_poc.coordinator import run

BASE = json.loads((Path(__file__).resolve().parents[1] / "fixtures/purchase.json").read_text())


class CoordinatorContractTests(unittest.TestCase):
    def test_multidomain_deduplicates_bank_spending_and_never_writes(self):
        result = run(BASE)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["invoked_domains"], ["purchase", "finance", "home"])
        self.assertIn("EUR 49.90", result["specialist_results"]["finance"]["findings"][0]["claim"])
        self.assertTrue(result["simulation"] and result["read_only"])
        self.assertEqual(result["executed_writes"], [])
        self.assertTrue(all(p["approval_required"] and not p["executed"] for p in result["proposed_writes"]))
        self.assertEqual({p["domain_owner"] for p in result["proposed_writes"]}, {"purchase", "finance"})

    def test_finance_only_never_invokes_irrelevant_agents(self):
        request = copy.deepcopy(BASE)
        request["domains"] = ["finance"]
        result = run(request)
        self.assertEqual(result["invoked_domains"], ["finance"])

    def test_conflicting_amounts_visible_and_no_finance_write_proposed(self):
        request = copy.deepcopy(BASE)
        request["evidence"][0]["data"]["amount_eur"] = "55.00"
        result = run(request)
        finance = result["specialist_results"]["finance"]
        self.assertEqual(finance["status"], "partial")
        self.assertIn("differs", " ".join(result["unresolved_questions"]))
        self.assertEqual(finance["proposed_writes"], [])
        self.assertEqual(result["status"], "partial")

    def test_unconfirmed_receipt_does_not_propose_possession(self):
        request = copy.deepcopy(BASE)
        request["evidence"][0]["data"]["status"] = "pending"
        result = run(request)
        self.assertEqual(result["specialist_results"]["home"]["status"], "blocked")
        self.assertEqual(result["specialist_results"]["home"]["proposed_writes"], [])

    def test_missing_purchase_specialist_blocks_dependent_home(self):
        request = copy.deepcopy(BASE)
        result = run(request, handlers={"finance": lambda *a: {"domain_owner": "finance", "status": "completed", "findings": [], "proposed_writes": [], "unresolved_questions": []},
                                        "home": __import__("v2_poc.coordinator", fromlist=["home_specialist"]).home_specialist})
        self.assertEqual(result["specialist_results"]["purchase"]["status"], "failed")
        self.assertEqual(result["specialist_results"]["home"]["status"], "blocked")
        self.assertEqual(result["status"], "partial")

    def test_conflicting_duplicate_evidence_identity_rejected(self):
        request = copy.deepcopy(BASE)
        conflicting = copy.deepcopy(request["evidence"][0])
        conflicting["data"]["amount_eur"] = "99.99"
        request["evidence"].append(conflicting)
        with self.assertRaisesRegex(ValueError, "conflicting entries"):
            run(request)

    def test_out_of_domain_proposed_write_causes_failure(self):
        request = copy.deepcopy(BASE)
        request["domains"] = ["finance"]
        def malicious(*_):
            return {"domain_owner": "finance", "status": "completed", "findings": [], "unresolved_questions": [],
                    "proposed_writes": [{"domain_owner": "finance", "canonical_destination": "/Health/record.md", "executed": False, "verified": False}]}
        result = run(request, handlers={"finance": malicious})
        self.assertEqual(result["specialist_results"]["finance"]["status"], "failed")
        self.assertEqual(result["proposed_writes"], [])

    def test_no_execution_authority_even_when_user_requests_it(self):
        request = copy.deepcopy(BASE)
        request["requested_actions"] = ["delete_inventory"]
        with self.assertRaisesRegex(ValueError, "read-only"):
            run(request)

    def test_nonfixture_source_rejected(self):
        request = copy.deepcopy(BASE)
        request["evidence"][0]["source_locator"] = "https://real-bank.example/private"
        with self.assertRaisesRegex(ValueError, "synthetic fixture"):
            run(request)


    def test_specialists_only_receive_required_evidence(self):
        observed = {}
        from v2_poc.coordinator import purchase_specialist, finance_specialist, home_specialist
        def wrapper(name, handler):
            def execute(items, prior):
                observed[name] = ([x["source_type"] for x in items], sorted(prior))
                return handler(items, prior)
            return execute
        result = run(BASE, handlers={
            "purchase": wrapper("purchase", purchase_specialist),
            "finance": wrapper("finance", finance_specialist),
            "home": wrapper("home", home_specialist),
        })
        self.assertEqual(result["status"], "completed")
        self.assertEqual(observed["purchase"], (["receipt"], []))
        self.assertEqual(observed["home"], (["receipt"], ["purchase"]))
        self.assertEqual(len(observed["finance"][0]), 4)
        self.assertEqual(observed["finance"][1], [])

    def test_conflicting_bank_transaction_id_blocks_financial_classification(self):
        request = copy.deepcopy(BASE)
        request["evidence"][2]["data"]["amount_eur"] = "19.90"
        result = run(request)
        self.assertEqual(result["specialist_results"]["finance"]["status"], "blocked")
        self.assertIn("Conflicting data", " ".join(result["unresolved_questions"]))
        self.assertEqual(result["specialist_results"]["finance"]["proposed_writes"], [])

    def test_hallucinated_evidence_reference_is_rejected(self):
        request = copy.deepcopy(BASE)
        request["domains"] = ["purchase"]
        def suspect(*_):
            return {"domain_owner": "purchase", "status": "completed", "findings": [
                {"claim": "claimed", "evidence_ids": ["inexistent"], "provenance": "source-verified"}
            ], "proposed_writes": [], "unresolved_questions": []}
        result = run(request, handlers={"purchase": suspect})
        self.assertEqual(result["specialist_results"]["purchase"]["status"], "failed")
        self.assertEqual(result["findings"], [])

    def test_repeat_same_input_is_deterministic_and_has_no_side_effects(self):
        self.assertEqual(run(BASE), run(copy.deepcopy(BASE)))

    def test_missing_receipt_blocks_purchase(self):
        request = copy.deepcopy(BASE)
        request["evidence"] = [e for e in request["evidence"] if e["source_type"] != "receipt"]
        result = run(request)
        self.assertEqual(result["specialist_results"]["purchase"]["status"], "blocked")
        self.assertEqual(result["status"], "partial")


if __name__ == "__main__":
    unittest.main()
