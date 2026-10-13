"""S1 regression: independently authored, fixture-only owner/action expectations.

Do not compute expected values from the shared candidate contract.
"""
import unittest

from v2_poc.owner_contract import (
    CONTRACT_VERSION, DESTINATIONS, OWNERS, ACTION_DESTINATIONS,
)
from v2_poc.health_evaluation import DESTINATIONS as EVALUATION_DESTINATIONS
from v2_poc.health_journey_contract import assess_journey
from v2_poc.simulated_execution import (
    DESTINATIONS as EXECUTION_DESTINATIONS, InvalidOperation,
    SimulatedApprovals, validate_operation,
)


# Independently written specification, not derived from candidate mappings.
EXPECTED = {
    "health": {"/Health/health-longitudinal-log.md", "mock:mental-wellbeing-record"},
    "home": {"mock:food-stock"},
    "finance": {"/Finance/purchase-plan.md"},
    "purchase": {"/Purchases/purchase-lifecycle.md"},
    "calendar": {"mock:calendar"},
}
EXPECTED_TYPES = {
    "stock_decrement": ("home", "mock:food-stock"),
    "health_note": ("health", "/Health/health-longitudinal-log.md"),
    "mental_note": ("health", "mock:mental-wellbeing-record"),
    "finance_review": ("finance", "/Finance/purchase-plan.md"),
    "purchase_note": ("purchase", "/Purchases/purchase-lifecycle.md"),
    "calendar_create": ("calendar", "mock:calendar"),
}


def sample(kind, owner, destination):
    if kind == "stock_decrement":
        change = {"type": kind, "quantity": 1}
    elif kind == "calendar_create":
        change = {"type": kind, "event_id": "test-event", "title": "Personal follow-up"}
    else:
        change = {"type": kind, "code": "routine_review"}
    return {"request_id": "test-request", "operation_id": "test-operation",
            "owner": owner, "destination": destination,
            "expected_revision": 0, "change": change}


class SharedContractTests(unittest.TestCase):
    def test_explicit_expected_owner_destinations(self):
        self.assertEqual(CONTRACT_VERSION, "s1-owner-contract-1")
        self.assertEqual(OWNERS, frozenset(EXPECTED))
        for owner, expected in EXPECTED.items():
            with self.subTest(owner=owner):
                self.assertEqual(set(DESTINATIONS[owner]), expected)
        self.assertIs(DESTINATIONS, EVALUATION_DESTINATIONS)
        self.assertIs(DESTINATIONS, EXECUTION_DESTINATIONS)

    def test_every_kind_matches_independent_owner_specification(self):
        self.assertEqual(ACTION_DESTINATIONS, EXPECTED_TYPES)
        for kind, (owner, destination) in EXPECTED_TYPES.items():
            with self.subTest(kind=kind):
                op = sample(kind, owner, destination)
                self.assertTrue(validate_operation(op))
                SimulatedApprovals().preview(op)
                for invalid_owner, invalid_destination in (
                    ("finance" if owner != "finance" else "health", destination),
                    (owner, "mock:unknown-destination"),
                ):
                    with self.assertRaises(InvalidOperation):
                        validate_operation(sample(kind, invalid_owner, invalid_destination))

    def test_unknown_action_and_changed_intent_denied(self):
        op = sample("health_note", "health", "/Health/health-longitudinal-log.md")
        op["change"]["type"] = "unknown_action"
        with self.assertRaises(InvalidOperation):
            validate_operation(op)
        original = sample("stock_decrement", "home", "mock:food-stock")
        approval = SimulatedApprovals()
        approval.decide(approval.preview(original), "approve")
        original["change"]["quantity"] = 2
        self.assertEqual(approval.status(original), "missing")

    def test_p0_result_contract_rejects_foreign_destination(self):
        result = {"simulation": True, "read_only": True,
                  "reported_facts": [], "unknowns": [], "urgency_assessed": True,
                  "invoked_owners": ["health"],
                  "actions": [{"operation_id": "op-1", "owner": "health",
                               "status": "proposed", "destination": "/Finance/purchase-plan.md"}]}
        self.assertIn("owner destination mismatch", assess_journey(result))


if __name__ == "__main__":
    unittest.main()
