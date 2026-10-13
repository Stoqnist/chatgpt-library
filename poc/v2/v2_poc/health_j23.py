"""Scripted fictional J2 wound and J3 wellbeing journeys; no clinical engine.

Controls are authored fixture labels. Neither images nor reported feelings
establish a diagnosis, treatment suitability, or mental state.
"""
from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path
from .health_evaluation import MockBoundary

VERSION = "j2-j3-synthetic-1"
OWNED = {"j2": "/Health/health-longitudinal-log.md",
         "j3": "mock:mental-wellbeing-record"}


def validate(s):
    if not isinstance(s, dict) or s.get("synthetic") is not True or s.get("version") != VERSION:
        raise ValueError("invalid synthetic scenario")
    if not isinstance(s.get("journey"), str) or s["journey"] not in OWNED:
        raise ValueError("invalid journey")
    turns = s.get("turns")
    if not isinstance(turns, list) or not 1 <= len(turns) <= 6:
        raise ValueError("invalid turns")
    for n, t in enumerate(turns, 1):
        if (not isinstance(t, dict) or type(t.get("turn")) is not int or
                t["turn"] != n or not isinstance(t.get("triage"), str) or
                t["triage"] not in {"clarify", "routine", "urgent"}):
            raise ValueError("invalid scripted triage")
        if not isinstance(t.get("observation"), str) or t["observation"] not in {"none", "uncertain", "conflicting", "user_report"}:
            raise ValueError("invalid observation")
        for key in ("suitable", "needs_supplies", "calendar", "record_proposal", "monitoring_consent"):
            if type(t.get(key)) is not bool:
                raise ValueError("invalid fixture bool")
        if not isinstance(t.get("stock"), str) or t["stock"] not in {"sufficient", "short", "unknown", "expired", "unavailable"}:
            raise ValueError("invalid stock")
        if not isinstance(t.get("budget"), str) or t["budget"] not in {"adequate", "insufficient", "unknown"}:
            raise ValueError("invalid budget")


class ObservedBoundary:
    def __init__(self):
        self.log = MockBoundary()
        self._state = {"stock": {}, "records": {}, "calendar": {}}

    @property
    def events(self):
        return self.log.events

    @property
    def initial_state(self):
        return {"stock": {}, "records": {}, "calendar": {}}

    @property
    def final_state(self):
        return deepcopy(self._state)

    def event(self, kind, owner, turn, evidence_ids, **extra):
        return self.log.call(kind, owner, turn=turn, evidence_ids=evidence_ids, **extra)

    def attempt_write(self, turn, owner):
        self.event("write", owner, turn, ["need"])


def run(s, boundary):
    validate(s)
    answers, actions = {}, []
    for t in s["turns"]:
        n, triage = t["turn"], t["triage"]
        for a in actions:
            if a["status"] == "proposed":
                a["status"] = "blocked"
                a["reason"] = "superseded"
        boundary.event("assessment", "health", n, ["symptoms"], code=triage)
        lines = [f"Fictional {s['journey']} turn {n}. Scripted urgency: {triage}; not a diagnosis."]
        if triage == "urgent":
            boundary.event("escalation", "health", n, ["symptoms"])
            lines.append("Stop routine tasks. Seek urgent professional help; contact emergency services when immediate danger exists.")
        elif triage == "clarify":
            lines.append("Ask about warning signs and relevant missing details before relying on routine advice.")
        else:
            if t["observation"] in {"uncertain", "conflicting"}:
                lines.append("Observation or image evidence is inconclusive and cannot establish a condition or mental state.")
            if not t["suitable"]:
                lines.append("Health suitability is not established: no product recommendation or purchase.")
            if t["needs_supplies"] and t["suitable"]:
                boundary.event("read", "home", n, ["need"])
                if t["stock"] in {"unknown", "expired", "unavailable"}:
                    lines.append("Supplies cannot be confirmed usable or available; do not assume inventory.")
                elif t["stock"] == "short":
                    boundary.event("read", "finance", n, ["cost"])
                    if t["budget"] == "adequate":
                        boundary.event("read", "purchase", n, ["cost"])
                        op = f"purchase-t{n}"
                        boundary.event("proposal", "purchase", n, ["cost"],
                                       operation_id=op,
                                       destination="/Purchases/purchase-lifecycle.md")
                        actions.append({"operation_id": op, "owner": "purchase",
                                        "turn": n, "status": "proposed",
                                        "destination": "/Purchases/purchase-lifecycle.md"})
                        lines.append("An optional purchase is proposed only, not placed.")
                    else:
                        lines.append("Affordability is insufficient or unknown; no purchase proposal.")
            if t["record_proposal"]:
                op = f"health-t{n}"
                boundary.event("proposal", "health", n, ["symptoms"],
                               operation_id=op, destination=OWNED[s["journey"]])
                actions.append({"operation_id": op, "owner": "health", "turn": n,
                                "status": "proposed", "destination": OWNED[s["journey"]]})
                lines.append("Health-owned record update proposed; not saved.")
            if t["calendar"]:
                op = f"calendar-t{n}"
                boundary.event("proposal", "calendar", n, ["schedule"],
                               operation_id=op, destination="mock:calendar")
                actions.append({"operation_id": op, "owner": "calendar", "turn": n,
                                "status": "proposed", "destination": "mock:calendar",
                                "title": "Personal follow-up"})
                lines.append("Neutral calendar follow-up proposed; nothing scheduled.")
            if s["journey"] == "j3" and not t["monitoring_consent"]:
                lines.append("No ongoing mental-state monitoring was started.")
        lines.append("No record write, notification, purchase or external action occurred.")
        answers[f"answer-{n}"] = " ".join(lines)
    return {"simulation": True, "read_only": True, "answers": answers,
            "actions": actions, "status": "simulated_only", "generator_version": VERSION}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", required=True)
    a = parser.parse_args(argv)
    s = json.loads(Path(a.fixture).read_text())
    b = ObservedBoundary()
    result = run(s, b)
    from .health_j23_oracle import evaluate
    report = evaluate(s, result, b, os.getenv("GITHUB_SHA") or "local-unverified")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
