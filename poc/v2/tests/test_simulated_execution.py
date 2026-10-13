"""P3 simulated execution regressions; no live accounts touched."""
import unittest

from v2_poc.simulated_execution import (
    DisposableStore, SimulatedApprovals, SimulatedExecutor, InvalidOperation,
    SimulatedFailure,
)
from v2_poc.simulated_execution_oracle import evaluate_execution


def operation(kind="stock_decrement", operation_id="op-1", revision=0):
    definitions = {
        "stock_decrement": ("home", "mock:food-stock", {"type": kind, "quantity": 1}),
        "calendar_create": ("calendar", "mock:calendar",
                            {"type": kind, "event_id": "event-one", "title": "Personal follow-up"}),
        "health_note": ("health", "/Health/health-longitudinal-log.md",
                        {"type": kind, "code": "followup_needed"}),
    }
    owner, destination, change = definitions[kind]
    return {"request_id": "fictional-request", "operation_id": operation_id,
            "owner": owner, "destination": destination,
            "expected_revision": revision, "change": change}


class ExecutionTests(unittest.TestCase):
    def setup_case(self, ops, faults=None, decisions=None):
        store, approvals = DisposableStore(faults=faults), SimulatedApprovals()
        initial = store.state
        for op, decision in zip(ops, decisions or ["approve"] * len(ops)):
            approvals.decide(approvals.preview(op), decision)
        return store, approvals, initial

    def test_approved_three_owner_actions_and_readback(self):
        ops = [operation(), operation("calendar_create", "op-2"),
               operation("health_note", "op-3")]
        store, approvals, initial = self.setup_case(ops)
        result = SimulatedExecutor(store, approvals).execute(ops)
        self.assertEqual([r["status"] for r in result["outcomes"]], ["verified"] * 3)
        self.assertEqual(store.state["mock:food-stock"]["value"]["count"], 2)
        self.assertEqual(len(store.state["mock:calendar"]["value"]["events"]), 1)
        self.assertTrue(evaluate_execution(ops, approvals, initial, store, result, "test")["passed"])

    def test_denied_and_missing_approval_do_not_write(self):
        for decision in ("deny", None):
            op = operation()
            store, approvals, initial = self.setup_case([], decisions=[])
            if decision:
                approvals.decide(approvals.preview(op), decision)
            result = SimulatedExecutor(store, approvals).execute([op])
            self.assertEqual(store.state, initial)
            self.assertEqual(result["outcomes"][0]["status"],
                             "denied" if decision else "blocked")

    def test_owner_destination_and_mutated_approval_rejected(self):
        op = operation()
        store, approvals, initial = self.setup_case([op])
        mutated = dict(op, owner="finance")
        with self.assertRaises(InvalidOperation):
            SimulatedExecutor(store, approvals).execute([mutated])
        mutated = dict(op, change={"type": "stock_decrement", "quantity": 2})
        result = SimulatedExecutor(store, approvals).execute([mutated])
        self.assertEqual(result["outcomes"][0]["status"], "blocked")
        self.assertEqual(store.state, initial)

    def test_stale_version_and_replay_prevent_double_stock_decrement(self):
        op = operation()
        store, approvals, _ = self.setup_case([op])
        first = SimulatedExecutor(store, approvals).execute([op])
        second = SimulatedExecutor(store, approvals).execute([op])
        self.assertEqual(first["outcomes"][0]["status"], "verified")
        self.assertEqual(second["outcomes"][0]["status"], "verified")
        self.assertEqual(store.state["mock:food-stock"]["value"]["count"], 2)
        op2 = operation(operation_id="op-2", revision=0)
        approvals.decide(approvals.preview(op2), "approve")
        result = SimulatedExecutor(store, approvals).execute([op2])
        self.assertEqual(result["outcomes"][0]["reason"], "revision_conflict")
        self.assertEqual(store.state["mock:food-stock"]["value"]["count"], 2)

    def test_timeout_before_and_after_are_inspected_not_retried(self):
        for fault, expected, count in [("before_timeout", "unknown", 3),
                                       ("after_timeout", "verified", 2)]:
            op = operation()
            store, approvals, _ = self.setup_case([op], faults={"op-1": fault})
            executor = SimulatedExecutor(store, approvals)
            first = executor.execute([op])
            second = executor.execute([op])
            with self.subTest(fault=fault):
                self.assertEqual(first["outcomes"][0]["status"], expected)
                self.assertEqual(second["outcomes"][0]["status"], expected)
                self.assertEqual(store.state["mock:food-stock"]["value"]["count"], count)
                self.assertEqual(len([e for e in store.events if e["kind"] == "write_attempt"]), 1)

    def test_uncertain_readback_not_called_verified(self):
        op = operation()
        store, approvals, _ = self.setup_case([op], faults={"op-1": "readback_unavailable"})
        out = SimulatedExecutor(store, approvals).execute([op])
        self.assertEqual(out["outcomes"][0]["status"], "unknown")
        self.assertEqual(store.state["mock:food-stock"]["value"]["count"], 2)

    def test_partial_failure_and_duplicate_calendar(self):
        ops = [operation(), operation("calendar_create", "op-2")]
        store, approvals, _ = self.setup_case(ops, faults={"op-2": "before_failure"})
        out = SimulatedExecutor(store, approvals).execute(ops)
        self.assertEqual(out["status"], "partial")
        self.assertEqual([x["status"] for x in out["outcomes"]], ["verified", "failed"])
        store2, approvals2, _ = self.setup_case([operation("calendar_create")])
        op = operation("calendar_create")
        executor = SimulatedExecutor(store2, approvals2)
        executor.execute([op])
        self.assertEqual(executor.execute([op])["outcomes"][0]["status"], "verified")
        self.assertEqual(len(store2.state["mock:calendar"]["value"]["events"]), 1)

    def test_batch_duplicate_is_blocked(self):
        op = operation()
        store, approvals, _ = self.setup_case([op])
        out = SimulatedExecutor(store, approvals).execute([op, op])
        self.assertEqual([o["status"] for o in out["outcomes"]], ["verified", "blocked"])


if __name__ == "__main__":
    unittest.main()
