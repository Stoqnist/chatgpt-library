"""I1 fictional J1-J3 to P3 mock bridge. Never calls live providers."""
from copy import deepcopy

from .health_j1 import FixtureBoundary, run_j1, validate_fixture
from .health_j1_oracle import evaluate_j1
from .health_j23 import ObservedBoundary, run as run_j23, validate as validate_j23
from .health_j23_oracle import evaluate as evaluate_j23
from .simulated_execution import DisposableStore, SimulatedApprovals, SimulatedExecutor, InvalidOperation

# A purchase proposal may only create a MOCK review note, never a real order.
NOTES = {
    ("purchase", "/Purchases/purchase-lifecycle.md"): ("purchase_note", "routine_review"),
    ("health", "/Health/health-longitudinal-log.md"): ("health_note", "followup_needed"),
    ("health", "mock:mental-wellbeing-record"): ("mental_note", "followup_needed"),
}


class MockJourneyIntegration:
    """Current-turn-only previews; simulated decisions must be explicit."""

    def __init__(self, journey, fixture, *, faults=None):
        if journey not in {"j1", "j2", "j3"}:
            raise ValueError("unknown journey")
        self.journey, self.fixture = journey, deepcopy(fixture)
        if journey == "j1":
            validate_fixture(self.fixture)
        else:
            validate_j23(self.fixture)
            if self.fixture["journey"] != journey:
                raise ValueError("journey mismatch")
        self.store = DisposableStore(faults=faults)
        self.approvals = SimulatedApprovals()
        self.executor = SimulatedExecutor(
            self.store, self.approvals,
            recovery_read_allowed=self._mock_recovery_read_allowed)
        self.turn = 0
        self.triage = None
        self._operations = []
        self._previews = []
        self._last_outcomes = {}
        # Immutable prior-turn outcomes are kept separately from current
        # permissions. Revoking consent must not rewrite observed effects.
        self._prior_outcomes = []
        # Only exact operations previously attempted with ambiguous outcomes
        # may be reconciled; no old approval is restored.
        self._prior_uncertain = {}
        # Fictional owner/resource/operation read permissions are independent
        # of the simulated user's write-approval decisions.
        self._recovery_read_permissions = set()

    def _mock_recovery_read_allowed(self, requester_owner, operation):
        op_id = operation["operation_id"]
        grant = (requester_owner, operation["request_id"],
                 op_id, operation["destination"])
        return (grant in self._recovery_read_permissions
                and self._prior_uncertain.get(op_id) == operation)

    def advance(self, turn):
        if type(turn) is not int or turn != self.turn + 1 or turn > len(self.fixture["turns"]):
            raise ValueError("turn must advance by one")
        scenario = deepcopy(self.fixture)
        scenario["turns"] = scenario["turns"][:turn]
        if self.journey == "j1":
            boundary = FixtureBoundary(scenario)
            result = run_j1(scenario, boundary)
            evidence = evaluate_j1(scenario, result, boundary)
            triage = scenario["turns"][-1]["assessment"]
        else:
            boundary = ObservedBoundary()
            result = run_j23(scenario, boundary)
            evidence = evaluate_j23(scenario, result, boundary, "local-unverified")
            triage = scenario["turns"][-1]["triage"]
        if not evidence["passed"]:
            raise InvalidOperation("journey observation check failed")
        observed = [e for e in boundary.events if e["kind"] == "proposal"]
        actions = result["actions"]
        if len(observed) != len(actions):
            raise InvalidOperation("missing observed proposal")
        keys = [(e["turn"], e["operation_id"]) for e in observed]
        if len(keys) != len(set(keys)):
            raise InvalidOperation("duplicate observed proposal")
        events = dict(zip(keys, observed))
        for a in actions:
            e = events.get((a["turn"], a["operation_id"]))
            if e is None or (a["owner"], a["destination"]) != (e["owner"], e["destination"]):
                raise InvalidOperation("untrusted proposed action")
            if a["status"] != ("proposed" if a["turn"] == turn else "blocked"):
                raise InvalidOperation("stale proposal")
            if a["owner"] == "calendar" and a.get("title") != "Personal follow-up":
                raise InvalidOperation("calendar privacy violation")
        ops = []
        if triage == "routine":
            for a in actions:
                if a["status"] != "proposed":
                    continue
                key = (a["owner"], a["destination"])
                if key == ("calendar", "mock:calendar"):
                    change = {"type": "calendar_create",
                              "event_id": f"followup-{self.journey}-t{turn}",
                              "title": "Personal follow-up"}
                elif key in NOTES:
                    kind, code = NOTES[key]
                    change = {"type": kind, "code": code}
                else:
                    raise InvalidOperation("unsupported owner or destination")
                ops.append({"request_id": f"fictional-i1-{self.journey}",
                            "operation_id": a["operation_id"],
                            "owner": a["owner"], "destination": a["destination"],
                            "expected_revision": self.store.state[a["destination"]]["revision"],
                            "change": change})
        elif any(a["status"] == "proposed" for a in actions):
            raise InvalidOperation("non-routine proposal")
        # Authoritative revocation lives in P3's shared approval ledger:
        # a direct executor/store call with an old operation must also fail.
        # Revocation does not erase earlier attempts or their effects.
        withdrawn = [op["operation_id"] for op in self._operations
                     if (op["operation_id"] not in self._last_outcomes or
                         self._last_outcomes[op["operation_id"]].get("reason") == "approval_missing")]
        for op in self._operations:
            self.approvals.revoke(op)
        self._prior_outcomes.extend(
            {"turn": self.turn, **deepcopy(outcome)}
            for outcome in self._last_outcomes.values()
        )
        for old in self._operations:
            result = self._last_outcomes.get(old["operation_id"])
            if (result and result["status"] == "unknown"
                    and "attempted" in result["history"]):
                self._prior_uncertain[old["operation_id"]] = deepcopy(old)
                self._recovery_read_permissions.add(
                    (old["owner"], old["request_id"],
                     old["operation_id"], old["destination"]))
        previews = [self.approvals.preview(op) for op in ops]
        self._operations, self._previews = ops, previews
        self._last_outcomes = {}
        self.turn, self.triage = turn, triage
        return {"simulation": True, "turn": turn, "triage": triage,
                "withdrawn_operation_ids": withdrawn, "previews": deepcopy(previews),
                "prior_outcomes": deepcopy(self._prior_outcomes),
                "approval_inferred": False, "external_actions": 0}

    def decide(self, preview, decision):
        if not isinstance(preview, dict) or preview not in self._previews:
            raise ValueError("stale or unregistered preview")
        self.approvals.decide(preview, decision)

    def reconcile(self, operation_id, *, requester_owner=None):
        """Inspect with separately scoped fictional read permission, never approval."""
        if not isinstance(operation_id, str) or operation_id not in self._prior_uncertain:
            raise ValueError("no superseded unknown attempt available to inspect")
        operation = self._prior_uncertain[operation_id]
        prior = next((o for o in self._prior_outcomes
                      if o["operation_id"] == operation_id
                      and o["request_id"] == operation["request_id"]
                      and o["status"] == "unknown"), None)
        if prior is None:
            raise ValueError("historical unknown outcome is unavailable")
        inspected = self.executor.inspect_only(
            deepcopy(operation), requester_owner=requester_owner)
        if inspected.get("reason") == "recovery_read_not_authorized":
            raise PermissionError("recovery read not authorized")
        if inspected["status"] not in {"verified", "unknown"}:
            raise InvalidOperation("inspection did not match an ambiguous attempt")
        # Preserve the original attempt and unknown state in the history.
        # Never relabel absence of an applied marker as a failed write.
        if "initial_reason" not in prior:
            prior["initial_reason"] = prior["reason"]
        prior["history"].extend(["inspection_only", inspected["status"]])
        prior["status"] = inspected["status"]
        prior["reason"] = "inspection_only"
        if inspected["status"] == "verified":
            del self._prior_uncertain[operation_id]
            self._recovery_read_permissions.discard(
                (operation["owner"], operation["request_id"],
                 operation["operation_id"], operation["destination"]))
        return {"simulation": True, "operation_id": operation_id,
                "status": inspected["status"], "outcome": deepcopy(prior),
                "external_actions": 0}

    def execute(self):
        if self.turn == 0:
            raise ValueError("must plan a turn before execution")
        result = self.executor.execute(deepcopy(self._operations))
        for outcome in result["outcomes"]:
            current = deepcopy(outcome)
            prior = self._last_outcomes.get(current["operation_id"])
            if prior:
                # Keep the first attempted trace when a repeat only inspects
                # an uncertain outcome or reads back an already applied mock.
                current["history"] = prior["history"] + ["rechecked"] + current["history"]
            self._last_outcomes[current["operation_id"]] = current
        cumulative = deepcopy(self._prior_outcomes) + [
            {"turn": self.turn, **deepcopy(outcome)}
            for outcome in self._last_outcomes.values()
        ]
        cumulative_status = ("no_actions" if not cumulative else
                             "verified" if all(o["status"] == "verified" for o in cumulative)
                             else "partial")
        status = result["status"] if self.triage == "routine" else (
            "urgent_escalated" if self.triage == "urgent" else "clarification_needed")
        return {"simulation": True, "mode": "disposable_mock_only",
                "journey": self.journey, "turn": self.turn, "status": status,
                "outcomes": result["outcomes"],
                "prior_outcomes": deepcopy(self._prior_outcomes),
                "cumulative_outcomes": cumulative, "cumulative_status": cumulative_status,
                "external_actions": 0,
                "clinical_validity": "not_evaluated", "promotion_authorized": False}
