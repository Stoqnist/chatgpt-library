"""I1 offline integration regression; all fixtures and stores are fictional."""
from copy import deepcopy
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from v2_poc.health_i1 import MockJourneyIntegration
from v2_poc.simulated_execution import InvalidOperation

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def make(journey, *, faults=None):
    scenario = json.loads((FIXTURES / f"health_{journey}.json").read_text())
    return MockJourneyIntegration(journey, scenario, faults=faults)


class I1MockIntegrationTests(TestCase):
    def test_j1_proposals_need_explicit_decision_and_are_replay_safe(self):
        session = make("j1")
        self.assertEqual(session.advance(1)["previews"], [])
        stage = session.advance(2)
        self.assertEqual(stage["triage"], "routine")
        self.assertEqual([(p["owner"], p["destination"]) for p in stage["previews"]],
                         [("purchase", "/Purchases/purchase-lifecycle.md"),
                          ("calendar", "mock:calendar")])
        self.assertFalse(stage["approval_inferred"])
        before = session.store.state
        blocked = session.execute()
        self.assertEqual([o["reason"] for o in blocked["outcomes"]],
                         ["approval_missing", "approval_missing"])
        self.assertEqual(session.store.state, before)
        self.assertEqual([e["kind"] for e in session.store.events
                          if e["kind"] == "write_attempt"], [])
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        accepted = session.execute()
        self.assertEqual(accepted["status"], "verified")
        self.assertEqual([o["status"] for o in accepted["outcomes"]], ["verified"] * 2)
        self.assertEqual(session.store.state["/Purchases/purchase-lifecycle.md"]["value"],
                         {"code": "routine_review"})
        self.assertEqual(session.store.state["mock:food-stock"]["value"]["count"], 3)
        self.assertEqual(len(session.store.state["mock:calendar"]["value"]["events"]), 1)
        session.execute()
        self.assertEqual(len([e for e in session.store.events
                              if e["kind"] == "write_applied"]), 2)
        self.assertTrue(all(x["change"]["type"] != "stock_decrement"
                            for x in stage["previews"]))

    def test_urgent_turn_revokes_prior_approved_but_unexecuted_plan(self):
        session = make("j1")
        session.advance(1)
        prior = session.advance(2)
        for preview in prior["previews"]:
            session.decide(preview, "approve")
        before = session.store.state
        urgent = session.advance(3)
        self.assertEqual(urgent["triage"], "urgent")
        self.assertEqual(urgent["previews"], [])
        self.assertEqual(set(urgent["withdrawn_operation_ids"]),
                         {"purchase-plan-t2", "calendar-review-t2"})
        with self.assertRaises(ValueError):
            session.decide(prior["previews"][0], "approve")
        result = session.execute()
        self.assertEqual(result["status"], "urgent_escalated")
        self.assertEqual(result["outcomes"], [])
        self.assertEqual(session.store.state, before)
        self.assertFalse(any(e["kind"] == "write_attempt" for e in session.store.events))

    def test_j2_three_owners_and_urgent_preemption(self):
        session = make("j2")
        stage = session.advance(1)
        self.assertEqual({p["owner"] for p in stage["previews"]},
                         {"purchase", "health", "calendar"})
        changes = {p["owner"]: p["change"] for p in stage["previews"]}
        self.assertEqual(changes["purchase"], {"type": "purchase_note", "code": "routine_review"})
        self.assertEqual(changes["health"], {"type": "health_note", "code": "followup_needed"})
        self.assertEqual(changes["calendar"]["title"], "Personal follow-up")
        for p in stage["previews"]:
            session.decide(p, "approve")
        result = session.execute()
        self.assertEqual(result["status"], "verified")
        self.assertEqual(len(result["outcomes"]), 3)
        applied = session.store.state
        session.advance(2)
        self.assertEqual(session.execute()["status"], "urgent_escalated")
        self.assertEqual(session.store.state, applied)

    def test_j3_mental_record_stays_owner_scoped_and_denial_is_truthful(self):
        session = make("j3")
        self.assertEqual(session.advance(1)["previews"], [])
        stage = session.advance(2)
        self.assertEqual([(p["owner"], p["destination"]) for p in stage["previews"]],
                         [("health", "mock:mental-wellbeing-record"),
                          ("calendar", "mock:calendar")])
        self.assertEqual(stage["previews"][0]["change"],
                         {"type": "mental_note", "code": "followup_needed"})
        self.assertEqual(stage["previews"][1]["change"]["title"], "Personal follow-up")
        session.decide(stage["previews"][0], "approve")
        session.decide(stage["previews"][1], "deny")
        output = session.execute()
        self.assertEqual([x["status"] for x in output["outcomes"]], ["verified", "denied"])
        self.assertEqual(output["status"], "partial")
        self.assertEqual(session.store.state["mock:calendar"]["value"]["events"], [])
        self.assertEqual(session.store.state["mock:mental-wellbeing-record"]["value"],
                         {"code": "followup_needed"})
        self.assertEqual(session.advance(3)["previews"], [])
        self.assertEqual(session.execute()["status"], "urgent_escalated")

    def test_changed_preview_and_wrong_owner_are_blocked(self):
        session = make("j2")
        stage = session.advance(1)
        before = session.store.state
        altered = deepcopy(stage["previews"][0])
        altered["change"]["code"] = "user_report_logged"
        with self.assertRaises(ValueError):
            session.decide(altered, "approve")
        self.assertEqual(session.store.state, before)

        from v2_poc import health_i1
        original = health_i1.run_j23

        def forged(scenario, boundary):
            output = original(scenario, boundary)
            output["actions"][0]["owner"] = "finance"
            return output

        malicious = make("j2")
        with patch.object(health_i1, "run_j23", side_effect=forged):
            with self.assertRaises(InvalidOperation):
                malicious.advance(1)
        self.assertEqual(malicious.turn, 0)
        self.assertEqual(malicious.store.state, before)

    def test_revision_conflict_and_partial_provider_failure(self):
        session = make("j2", faults={"calendar-t1": "before_failure"})
        stage = session.advance(1)
        for p in stage["previews"]:
            session.decide(p, "approve")
        result = session.execute()
        self.assertEqual([o["status"] for o in result["outcomes"]],
                         ["verified", "verified", "failed"])
        self.assertEqual(result["status"], "partial")
        self.assertEqual(session.store.state["mock:calendar"]["value"]["events"], [])
        self.assertFalse(result["promotion_authorized"])
        self.assertEqual(result["external_actions"], 0)

        changed = make("j3")
        changed.advance(1)
        previews = changed.advance(2)["previews"]
        for p in previews:
            changed.decide(p, "approve")
        changed.store._records["mock:calendar"]["revision"] += 1  # fictional competing edit
        report = changed.execute()
        self.assertEqual([o["status"] for o in report["outcomes"]],
                         ["verified", "blocked"])
        self.assertEqual(report["outcomes"][1]["reason"], "revision_conflict")
        self.assertEqual(changed.store.state["mock:calendar"]["value"]["events"], [])

    def test_timeout_is_inspected_without_replay_and_unknown_is_not_verified(self):
        for fault, expected in (("before_timeout", "unknown"),
                                ("after_timeout", "verified")):
            session = make("j2", faults={"calendar-t1": fault})
            stage = session.advance(1)
            for p in stage["previews"]:
                session.decide(p, "approve")
            first = session.execute()
            second = session.execute()
            self.assertEqual(first["outcomes"][2]["status"], expected)
            self.assertEqual(second["outcomes"][2]["status"], expected)
            writes = [e for e in session.store.events
                      if e["kind"] == "write_attempt" and e["operation_id"] == "calendar-t1"]
            self.assertEqual(len(writes), 1)

    def test_no_arbitrary_turn_or_execution_before_planning(self):
        session = make("j3")
        with self.assertRaises(ValueError):
            session.execute()
        with self.assertRaises(ValueError):
            session.advance(2)
        with self.assertRaises(ValueError):
            session.advance(True)
        session.advance(1)
        with self.assertRaises(ValueError):
            session.advance(3)
        with self.assertRaises(ValueError):
            session.decide({"not": "a preview"}, "approve")
