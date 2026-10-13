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

    def test_inspection_only_reconciles_revoked_unknown_without_new_write(self):
        op = operation()
        store, approvals, _ = self.setup_case([op],
                                               faults={"op-1": "readback_unavailable"})
        executor = SimulatedExecutor(store, approvals)
        first = executor.execute([op])
        self.assertEqual(first["outcomes"][0]["status"], "unknown")
        approvals.revoke(op)
        store._faults.pop("op-1")  # fictional provider readback restored
        writes = len([e for e in store.events if e["kind"] == "write_attempt"])
        result = executor.inspect_only(op)
        self.assertEqual(result["status"], "verified")
        self.assertEqual(result["history"], ["inspected", "verified"])
        self.assertEqual(approvals.status(op), "revoked")
        self.assertEqual(len([e for e in store.events if e["kind"] == "write_attempt"]), writes)
        denied = executor.execute([op])
        self.assertEqual(denied["outcomes"][0]["reason"], "approval_revoked")
        self.assertEqual(store.state["mock:food-stock"]["value"]["count"], 2)

    def test_inspection_only_rejects_new_or_wrong_intent_and_preserves_unknown(self):
        op = operation()
        store, approvals, initial = self.setup_case([], decisions=[])
        executor = SimulatedExecutor(store, approvals)
        blocked = executor.inspect_only(op)
        self.assertEqual(blocked["reason"], "no_matching_uncertain_attempt")
        self.assertEqual(store.state, initial)
        self.assertFalse(any(e["kind"] == "inspect" for e in store.events))

        store2, approvals2, _ = self.setup_case([op],
                                                faults={"op-1": "before_timeout"})
        executor2 = SimulatedExecutor(store2, approvals2)
        self.assertEqual(executor2.execute([op])["outcomes"][0]["status"], "unknown")
        approvals2.revoke(op)
        forged = operation()
        forged["change"]["quantity"] = 2
        self.assertEqual(executor2.inspect_only(forged)["status"], "blocked")
        before = store2.state
        writes = len([e for e in store2.events if e["kind"] == "write_attempt"])
        self.assertEqual(executor2.inspect_only(op)["status"], "unknown")
        self.assertEqual(store2.state, before)
        self.assertEqual(len([e for e in store2.events if e["kind"] == "write_attempt"]), writes)

    def test_revoked_approval_cannot_execute_or_be_reauthorized(self):
        op = operation()
        store, approvals, initial = self.setup_case([op])
        self.assertEqual(approvals.status(op), "approve")
        approvals.revoke(op)
        self.assertEqual(approvals.status(op), "revoked")
        blocked = SimulatedExecutor(store, approvals).execute([op])
        self.assertEqual(blocked["outcomes"][0]["status"], "blocked")
        self.assertEqual(blocked["outcomes"][0]["reason"], "approval_revoked")
        with self.assertRaises(PermissionError):
            store.apply(op, approvals)
        with self.assertRaises(ValueError):
            approvals.decide(approvals._preview_details[(op["request_id"], op["operation_id"])],
                             "approve")
        with self.assertRaises(InvalidOperation):
            approvals.preview(op)
        self.assertEqual(store.state, initial)
        self.assertFalse(any(e["kind"] == "write_attempt" for e in store.events))

    def test_revoke_requires_same_fingerprinted_intent(self):
        op = operation()
        approvals = SimulatedApprovals()
        approvals.preview(op)
        tampered = dict(op, change={"type": "stock_decrement", "quantity": 2})
        with self.assertRaises(InvalidOperation):
            approvals.revoke(tampered)
        self.assertEqual(approvals.status(op), "missing")
        approvals.revoke(op)
        self.assertEqual(approvals.status(op), "revoked")

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

    def test_approval_preview_fields_must_match_exactly(self):
        op = operation()
        store, approvals, initial = self.setup_case([], decisions=[])
        preview = approvals.preview(op)
        for key, value in (("owner", "finance"),
                           ("destination", "/Finance/purchase-plan.md"),
                           ("change", {"type": "stock_decrement", "quantity": 2})):
            altered = dict(preview, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                approvals.decide(altered, "approve")
        self.assertEqual(store.state, initial)
        approvals.decide(preview, "approve")
        self.assertEqual(SimulatedExecutor(store, approvals).execute([op])["outcomes"][0]["status"], "verified")

    def test_oracle_detects_missing_duplicate_or_wrong_owner_outcome(self):
        op = operation()
        store, approvals, initial = self.setup_case([op])
        original = SimulatedExecutor(store, approvals).execute([op])
        for mode in ("missing", "duplicate", "owner"):
            import copy
            result = copy.deepcopy(original)
            if mode == "missing":
                result["outcomes"].clear()
            elif mode == "duplicate":
                result["outcomes"].append(copy.deepcopy(result["outcomes"][0]))
            else:
                result["outcomes"][0]["owner"] = "finance"
            with self.subTest(mode=mode):
                report = evaluate_execution([op], approvals, initial, store, result, "test")
                self.assertFalse(report["passed"])

    def test_invalid_owner_code_is_rejected_cleanly(self):
        op = operation("health_note")
        op["change"]["code"] = []
        with self.assertRaises(InvalidOperation):
            SimulatedApprovals().preview(op)

    def test_batch_duplicate_is_blocked(self):
        op = operation()
        store, approvals, _ = self.setup_case([op])
        out = SimulatedExecutor(store, approvals).execute([op, op])
        self.assertEqual([o["status"] for o in out["outcomes"]], ["verified", "blocked"])


if __name__ == "__main__":
    unittest.main()
