"""Fictional, deterministic J1 multi-turn simulator (P1 experimental only).

No actual specialists, clinical decision rules, accounts, network, model calls,
calendar operations, writes, or permissions. Assessment labels and mocked source
states are scenario inputs, not conclusions inferred from symptoms.
"""
from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path

from .health_evaluation import DESTINATIONS, MockBoundary

SCENARIO_VERSION = "j1-synthetic-1"
GENERATOR_VERSION = "scripted-j1-1"
REQUIRED_STATES = {"short", "sufficient", "unknown"}
BUDGET_STATES = {"adequate", "insufficient", "unknown"}


def load_fixture(path):
    fixture = json.loads(Path(path).read_text(encoding="utf-8"))
    validate_fixture(fixture)
    return fixture


def validate_fixture(scenario):
    """Reject unbounded or non-fictional inputs; not a security sandbox."""
    if not isinstance(scenario, dict) or scenario.get("synthetic") is not True:
        raise ValueError("synthetic fixture required")
    if scenario.get("scenario_version") != SCENARIO_VERSION:
        raise ValueError("unknown scenario version")
    turns = scenario.get("turns")
    if not isinstance(turns, list) or not 1 <= len(turns) <= 6:
        raise ValueError("expected 1-6 fixture turns")
    for index, turn in enumerate(turns, 1):
        if not isinstance(turn, dict) or turn.get("turn") != index:
            raise ValueError("turns must be ordered and sequential")
        if turn.get("assessment") not in {"clarify", "routine", "urgent"}:
            raise ValueError("unknown scripted assessment")
        for key in ("supplies", "suitable", "calendar"):
            if type(turn.get(key)) is not bool:
                raise ValueError("missing boolean fixture control")
        for key, states in (("stock", REQUIRED_STATES), ("budget", BUDGET_STATES)):
            entry = turn.get(key)
            if not isinstance(entry, dict) or entry.get("state") not in states:
                raise ValueError(f"invalid {key} fixture")
            if type(entry.get("connected")) is not bool or type(entry.get("fresh")) is not bool:
                raise ValueError(f"invalid {key} provenance")


class FixtureBoundary:
    """Independent read-only observation boundary; no writable provider backend.

    Logged events record attempts at their point of initiation. Data snapshots are
    deep copies of fictional fixtures, not based on the candidate's result text.
    """
    def __init__(self, scenario):
        self._turns = deepcopy(scenario["turns"])
        self._initial = deepcopy([(t["stock"], t["budget"]) for t in self._turns])
        self._log = MockBoundary()

    @property
    def events(self):
        return self._log.events

    @property
    def initial_state(self):
        return deepcopy(self._initial)

    @property
    def final_state(self):
        return deepcopy([(t["stock"], t["budget"]) for t in self._turns])

    def assessment(self, turn, code):
        self._log.call("assessment", "health", turn=turn, code=code,
                       evidence_ids=["symptoms"])

    def escalation(self, turn):
        self._log.call("escalation", "health", turn=turn,
                       evidence_ids=["symptoms"])

    def read(self, turn, owner):
        # These are synthetic, owner-scoped provider doubles. Only typed
        # evidence references cross the boundary, never symptom narratives.
        reference = {"home": "need", "finance": "cost", "purchase": "cost"}[owner]
        self._log.call("read", owner, turn=turn, evidence_ids=[reference])
        if owner == "purchase":
            return {"offer": "mock-only"}
        key = {"home": "stock", "finance": "budget"}[owner]
        return deepcopy(self._turns[turn - 1][key])

    def proposal(self, turn, owner, operation_id):
        evidence = {"health": "symptoms", "purchase": "cost",
                    "calendar": "schedule"}[owner]
        self._log.call("proposal", owner, turn=turn,
                       operation_id=operation_id,
                       destination=sorted(DESTINATIONS[owner])[0],
                       evidence_ids=[evidence])


def _current(entry):
    return entry["connected"] and entry["fresh"] and entry["state"] != "unknown"


def run_j1(scenario, boundary):
    """Simulate a full user journey with conditional owner calls.

    A newly submitted turn invalidates earlier unexecuted proposals. This
    conservative P1 policy is not asynchronous dependency reconciliation.
    """
    validate_fixture(scenario)
    answers = {}
    proposals = []
    stages = []
    for t in scenario["turns"]:
        number, code = t["turn"], t["assessment"]
        withdrawn = []
        for proposal in proposals:
            if proposal["status"] == "proposed":
                proposal["status"] = "blocked"
                proposal["reason"] = "superseded"
                withdrawn.append(proposal["operation_id"])

        boundary.assessment(number, code)
        lines = [f"Fictional turn {number}. Scenario triage label: {code} (scripted, not clinical advice)."]
        if withdrawn:
            lines.append("Prior proposals were withdrawn after circumstances changed.")
        if code == "urgent":
            boundary.escalation(number)
            lines.append("An urgent warning flag is specified by this test case. Stop routine planning and seek immediate professional assessment; use emergency services if in immediate danger.")
        elif code == "clarify":
            lines.append("More information about severity and warning signs is needed before routine planning.")
        else:
            lines.append("This fictional scenario is marked routine; real symptoms still require appropriate professional judgment.")
            if not t["suitable"]:
                lines.append("The fictional Health suitability gate blocks the product pathway.")
            if t["supplies"] and t["suitable"]:
                stock = boundary.read(number, "home")
                if not _current(stock):
                    lines.append("Stock is unknown, stale or disconnected; no shortage or availability is assumed.")
                elif stock["state"] == "sufficient":
                    lines.append("The current fictional stock record indicates supplies are sufficient.")
                else:
                    lines.append("The current fictional stock record indicates a shortage.")
                    budget = boundary.read(number, "finance")
                    if not _current(budget):
                        lines.append("Affordability is unknown, stale or disconnected; purchase planning stops.")
                    elif budget["state"] != "adequate":
                        lines.append("The fictional budget does not cover the purchase; no seller decision is requested.")
                    else:
                        boundary.read(number, "purchase")
                        operation_id = f"purchase-plan-t{number}"
                        boundary.proposal(number, "purchase", operation_id)
                        proposals.append(dict(turn=number, operation_id=operation_id,
                                              owner="purchase", status="proposed",
                                              destination=sorted(DESTINATIONS["purchase"])[0]))
                        lines.append("A purchase option is proposed for user review, not ordered or paid.")
            if t["calendar"]:
                operation_id = f"calendar-review-t{number}"
                boundary.proposal(number, "calendar", operation_id)
                proposals.append(dict(turn=number, operation_id=operation_id,
                                      owner="calendar", status="proposed",
                                      destination="mock:calendar",
                                      title="Personal follow-up"))
                lines.append("A neutral-titled calendar follow-up is proposed, not scheduled.")
        lines.append("No external actions or record changes were executed.")
        answers[f"answer-{number}"] = " ".join(lines)
        stages.append({"turn": number, "triage": code,
                       "withdrawn": withdrawn, "answer_id": f"answer-{number}"})
    return {"simulation": True, "read_only": True,
            "generator_version": GENERATOR_VERSION, "answers": answers,
            "actions": proposals, "turns": stages,
            "status": "simulated_only"}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Zero-API-cost synthetic J1 acceptance")
    parser.add_argument("--fixture", default=str(Path(__file__).resolve().parents[1] /
                                                 "fixtures" / "health_j1.json"))
    args = parser.parse_args(argv)
    scenario = load_fixture(args.fixture)
    boundary = FixtureBoundary(scenario)
    result = run_j1(scenario, boundary)
    from .health_j1_oracle import evaluate_j1
    report = evaluate_j1(scenario, result, boundary,
                         source_commit=os.environ.get("GITHUB_SHA") or "local-unverified")
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
