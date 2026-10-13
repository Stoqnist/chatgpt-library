"""P3: disposable, approval-gated execution simulator; NO provider integrations.

This is an in-memory test double, not a security boundary, production adapter,
real user consent, database transaction, or guarantee of provider idempotency.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from hashlib import sha256
import json
import os
import re

from .owner_contract import DESTINATIONS, ACTION_DESTINATIONS as TYPES
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
FIELDS = {"request_id", "operation_id", "owner", "destination", "expected_revision", "change"}


class InvalidOperation(ValueError):
    pass


class RevisionConflict(Exception):
    pass


class SimulatedFailure(Exception):
    pass


def _valid_id(value):
    return isinstance(value, str) and IDENTIFIER.fullmatch(value) is not None


def validate_operation(operation):
    if not isinstance(operation, dict) or set(operation) != FIELDS:
        raise InvalidOperation("invalid operation fields")
    if not _valid_id(operation["request_id"]) or not _valid_id(operation["operation_id"]):
        raise InvalidOperation("invalid stable identifiers")
    if type(operation["expected_revision"]) is not int or operation["expected_revision"] < 0:
        raise InvalidOperation("invalid revision")
    change = operation["change"]
    if not isinstance(change, dict) or not isinstance(change.get("type"), str):
        raise InvalidOperation("invalid change")
    kind = change["type"]
    if kind not in TYPES or (operation["owner"], operation["destination"]) != TYPES[kind]:
        raise InvalidOperation("owner/destination mismatch")
    if kind == "stock_decrement":
        if set(change) != {"type", "quantity"} or type(change["quantity"]) is not int or not 1 <= change["quantity"] <= 5:
            raise InvalidOperation("invalid stock change")
    elif kind == "calendar_create":
        if (set(change) != {"type", "event_id", "title"} or
                not _valid_id(change["event_id"]) or change["title"] != "Personal follow-up"):
            raise InvalidOperation("invalid calendar metadata")
    else:
        if (set(change) != {"type", "code"} or
                not isinstance(change["code"], str) or change["code"] not in {
                    "followup_needed", "routine_review", "user_report_logged"}):
            raise InvalidOperation("invalid owner-scoped code")
    return True


def fingerprint(operation):
    validate_operation(operation)
    data = json.dumps(operation, sort_keys=True, separators=(",", ":"))
    return sha256(data.encode("utf-8")).hexdigest()


def op_key(operation):
    return (operation["request_id"], operation["operation_id"])


class SimulatedApprovals:
    """Explicit fixture decisions, never inferred from a candidate result."""
    def __init__(self):
        self._previews = {}
        self._preview_details = {}
        self._decisions = {}

    def preview(self, operation):
        digest = fingerprint(operation)
        key = op_key(operation)
        if key in self._previews and self._previews[key] != digest:
            raise InvalidOperation("operation ID reused with changed intent")
        self._previews[key] = digest
        preview = {"request_id": key[0], "operation_id": key[1],
                   "owner": operation["owner"], "destination": operation["destination"],
                   "expected_revision": operation["expected_revision"],
                   "change": deepcopy(operation["change"]), "fingerprint": digest,
                   "approval_required": True}
        self._preview_details[key] = deepcopy(preview)
        return preview

    def decide(self, preview, decision):
        """Called only by the *simulated user* in test setup; not by executor."""
        if not isinstance(decision, str) or decision not in {"approve", "deny"} or not isinstance(preview, dict):
            raise ValueError("invalid simulated decision")
        request_id, operation_id = preview.get("request_id"), preview.get("operation_id")
        if not _valid_id(request_id) or not _valid_id(operation_id):
            raise ValueError("invalid preview identifiers")
        key = (request_id, operation_id)
        digest = self._previews.get(key)
        if not digest or preview != self._preview_details.get(key):
            raise ValueError("unregistered or mismatched preview")
        if key in self._decisions:
            if self._decisions[key] != (digest, decision):
                raise ValueError("approval cannot be silently changed")
            return
        self._decisions[key] = (digest, decision)

    def status(self, operation):
        key = op_key(operation)
        if self._previews.get(key) != fingerprint(operation):
            return "missing"
        decision = self._decisions.get(key)
        return decision[1] if decision and decision[0] == fingerprint(operation) else "missing"


class DisposableStore:
    """Provider *simulation*: atomic revisions and operation markers exist only here.

    Tests mutate this store, never a real Library file, Google Sheet or Calendar.
    """
    def __init__(self, *, faults=None):
        defaults = {
            "mock:food-stock": {"count": 3},
            "/Health/health-longitudinal-log.md": {"code": "unset"},
            "mock:mental-wellbeing-record": {"code": "unset"},
            "/Finance/purchase-plan.md": {"code": "unset"},
            "/Purchases/purchase-lifecycle.md": {"code": "unset"},
            "mock:calendar": {"events": []},
        }
        self._records = {key: {"revision": 0, "value": deepcopy(value)}
                         for key, value in defaults.items()}
        self._applied = {}
        self._intents = {}
        self._uncertain = set()
        self._events = []
        self._faults = dict(faults or {})

    @property
    def state(self):
        return deepcopy(self._records)

    @property
    def events(self):
        return deepcopy(self._events)

    def _event(self, kind, operation, **details):
        event = {"index": len(self._events), "kind": kind,
                 "request_id": operation["request_id"],
                 "operation_id": operation["operation_id"],
                 "owner": operation["owner"],
                 "destination": operation["destination"]}
        event.update(details)
        self._events.append(event)

    def register(self, operation):
        key, digest = op_key(operation), fingerprint(operation)
        if key in self._intents and self._intents[key] != digest:
            raise InvalidOperation("replayed ID has different payload")
        self._intents[key] = digest

    def inspect(self, operation):
        self._event("inspect", operation)
        if self._faults.get(operation["operation_id"]) == "inspection_unavailable":
            raise SimulatedFailure("inspection unavailable")
        marker = self._applied.get(op_key(operation))
        return deepcopy(marker) if marker and marker["fingerprint"] == fingerprint(operation) else None

    def readback(self, operation):
        self._event("readback", operation)
        fault = self._faults.get(operation["operation_id"])
        if fault == "readback_unavailable":
            raise SimulatedFailure("readback unavailable")
        value = deepcopy(self._records[operation["destination"]])
        if fault == "stale_readback":
            value["revision"] -= 1
        return value

    def mark_uncertain(self, operation):
        self._uncertain.add(op_key(operation))

    def is_uncertain(self, operation):
        return op_key(operation) in self._uncertain

    def apply(self, operation, approvals):
        """Enforce approval again at the provider simulation boundary."""
        validate_operation(operation)
        self.register(operation)
        if approvals.status(operation) != "approve":
            self._event("rejected_unapproved", operation)
            raise PermissionError("independent simulated approval required")
        key, digest = op_key(operation), fingerprint(operation)
        if key in self._uncertain:
            raise SimulatedFailure("uncertain result requires inspection")
        self._event("write_attempt", operation)
        marker = self._applied.get(key)
        if marker is not None:
            if marker["fingerprint"] != digest:
                raise InvalidOperation("conflicting replay")
            self._event("deduplicated", operation)
            return deepcopy(marker)
        entry = self._records[operation["destination"]]
        if entry["revision"] != operation["expected_revision"]:
            self._event("version_conflict", operation)
            raise RevisionConflict("record changed since preview")
        fault = self._faults.get(operation["operation_id"])
        if fault == "before_timeout":
            self._event("timeout_before", operation)
            raise TimeoutError("ambiguous timeout before provider write")
        if fault == "before_failure":
            self._event("failed_before", operation)
            raise SimulatedFailure("simulated provider rejected the write")
        change = operation["change"]
        value = deepcopy(entry["value"])
        if change["type"] == "stock_decrement":
            if value["count"] < change["quantity"]:
                self._event("insufficient_stock", operation)
                raise RevisionConflict("stock no longer sufficient")
            value["count"] -= change["quantity"]
        elif change["type"] == "calendar_create":
            if any(e["event_id"] == change["event_id"] for e in value["events"]):
                self._event("duplicate_event_id", operation)
                raise RevisionConflict("calendar event ID already exists")
            value["events"].append({"event_id": change["event_id"], "title": change["title"]})
        else:
            value["code"] = change["code"]
        entry["value"] = value
        entry["revision"] += 1
        marker = {"fingerprint": digest, "revision": entry["revision"],
                  "value": deepcopy(value)}
        self._applied[key] = deepcopy(marker)
        self._event("write_applied", operation, revision=entry["revision"])
        if fault == "after_timeout":
            self._event("timeout_after", operation)
            raise TimeoutError("ambiguous timeout after provider write")
        return deepcopy(marker)


class SimulatedExecutor:
    """Serial owner-scoped dispatch; unknown operations never blindly retried."""
    def __init__(self, store, approvals):
        self.store, self.approvals = store, approvals

    def _verify(self, operation, marker):
        try:
            observed = self.store.readback(operation)
        except SimulatedFailure:
            self.store.mark_uncertain(operation)
            return "unknown"
        if observed != {"revision": marker["revision"], "value": marker["value"]}:
            self.store.mark_uncertain(operation)
            return "unknown"
        return "verified"

    def execute(self, operations):
        outcomes = []
        seen = set()
        for op in operations:
            # Reject malformed/scope-escalating requests before touching store.
            validate_operation(op)
            key = op_key(op)
            if key in seen:
                outcomes.append({"request_id": key[0], "operation_id": key[1],
                                 "owner": op["owner"], "destination": op["destination"],
                                 "status": "blocked", "history": ["proposed", "blocked"],
                                 "reason": "duplicate_operation_in_batch"})
                continue
            seen.add(key)
            item = {"request_id": key[0], "operation_id": key[1],
                    "owner": op["owner"], "destination": op["destination"],
                    "status": "proposed", "history": ["proposed"]}
            try:
                self.store.register(op)
            except InvalidOperation:
                item.update(status="blocked", reason="conflicting_operation_id")
                item["history"].append("blocked")
                outcomes.append(item)
                continue
            approval = self.approvals.status(op)
            if approval != "approve":
                item.update(status="denied" if approval == "deny" else "blocked",
                            reason="approval_denied" if approval == "deny" else "approval_missing")
                item["history"].append(item["status"])
                outcomes.append(item)
                continue
            item["history"].append("authorized")
            if self.store.is_uncertain(op):
                # Inspection only; never automatically repeat a timed-out write.
                item["history"].append("inspected")
                try:
                    marker = self.store.inspect(op)
                except SimulatedFailure:
                    marker = None
                state = self._verify(op, marker) if marker else "unknown"
                item.update(status=state, reason="inspection_after_unknown")
                item["history"].append(state)
                outcomes.append(item)
                continue
            item["history"].append("attempted")
            try:
                marker = self.store.apply(op, self.approvals)
                state = self._verify(op, marker)
                item.update(status=state, reason="readback" if state == "verified" else "unverified_readback")
            except TimeoutError:
                self.store.mark_uncertain(op)
                item["history"].append("inspected")
                try:
                    marker = self.store.inspect(op)
                except SimulatedFailure:
                    marker = None
                state = self._verify(op, marker) if marker else "unknown"
                item.update(status=state, reason="timeout_inspected")
            except RevisionConflict:
                item.update(status="blocked", reason="revision_conflict")
            except SimulatedFailure:
                item.update(status="failed", reason="provider_failure")
            item["history"].append(item["status"])
            outcomes.append(item)
        status = ("verified" if outcomes and all(o["status"] == "verified" for o in outcomes)
                  else "partial" if outcomes else "no_actions")
        return {"simulation": True, "external_actions": 0, "status": status,
                "outcomes": outcomes}


def demo_report():
    from .simulated_execution_oracle import evaluate_execution
    store = DisposableStore()
    approvals = SimulatedApprovals()
    ops = [
        {"request_id": "fictional-request", "operation_id": "stock-1",
         "owner": "home", "destination": "mock:food-stock", "expected_revision": 0,
         "change": {"type": "stock_decrement", "quantity": 1}},
        {"request_id": "fictional-request", "operation_id": "calendar-1",
         "owner": "calendar", "destination": "mock:calendar", "expected_revision": 0,
         "change": {"type": "calendar_create", "event_id": "fictional-followup",
                    "title": "Personal follow-up"}},
        {"request_id": "fictional-request", "operation_id": "health-1",
         "owner": "health", "destination": "/Health/health-longitudinal-log.md",
         "expected_revision": 0,
         "change": {"type": "health_note", "code": "followup_needed"}},
    ]
    initial = store.state
    for op in ops:
        # Fixture deliberately models explicit simulated-user consent.
        approvals.decide(approvals.preview(op), "approve")
    outcome = SimulatedExecutor(store, approvals).execute(ops)
    return evaluate_execution(ops, approvals, initial, store, outcome,
                              source_commit=os.environ.get("GITHUB_SHA") or "local-unverified")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Offline disposable execution simulation")
    parser.parse_args(argv)
    report = demo_report()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
