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
        self.executor = SimulatedExecutor(self.store, self.approvals)
        self.turn = 0
        self.triage = None
        self._operations = []
        self._previews = []
        self._last_outcomes = {}

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
        previews = [self.approvals.preview(op) for op in ops]
        # A verified or attempted mock effect cannot truthfully be withdrawn.
        # Only not-yet-attempted previews are invalidated by the new turn.
        withdrawn = [op["operation_id"] for op in self._operations
                     if (op["operation_id"] not in self._last_outcomes or
                         self._last_outcomes[op["operation_id"]].get("reason") == "approval_missing")]
        self._operations, self._previews = ops, previews
        self._last_outcomes = {}
        self.turn, self.triage = turn, triage
        return {"simulation": True, "turn": turn, "triage": triage,
                "withdrawn_operation_ids": withdrawn, "previews": deepcopy(previews),
                "approval_inferred": False, "external_actions": 0}

    def decide(self, preview, decision):
        if not isinstance(preview, dict) or preview not in self._previews:
            raise ValueError("stale or unregistered preview")
        self.approvals.decide(preview, decision)

    def execute(self):
        if self.turn == 0:
            raise ValueError("must plan a turn before execution")
        result = self.executor.execute(deepcopy(self._operations))
        self._last_outcomes = {o["operation_id"]: deepcopy(o) for o in result["outcomes"]}
        status = result["status"] if self.triage == "routine" else (
            "urgent_escalated" if self.triage == "urgent" else "clarification_needed")
        return {"simulation": True, "mode": "disposable_mock_only",
                "journey": self.journey, "turn": self.turn, "status": status,
                "outcomes": result["outcomes"], "external_actions": 0,
                "clinical_validity": "not_evaluated", "promotion_authorized": False}
