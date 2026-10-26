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
        # Independent golden digest for the complete exact preview intent,
        # authored separately from P3's candidate fingerprint function.
        self.assertEqual(stage["previews"][0]["fingerprint"],
                         "ee530ba572206752fe0c6bfea727e8422890bdadb389b9da298d96ca8d2c31b7")
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
        after = session.advance(2)
        self.assertEqual(after["withdrawn_operation_ids"], [])
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

    def test_superseded_approved_operation_is_rejected_at_both_p3_boundaries(self):
        session = make("j1")
        session.advance(1)
        prior = session.advance(2)
        preview = prior["previews"][0]
        operation = {key: deepcopy(preview[key]) for key in (
            "request_id", "operation_id", "owner", "destination",
            "expected_revision", "change")}
        session.decide(preview, "approve")
        self.assertEqual(session.approvals.status(operation), "approve")
        before = session.store.state

        session.advance(3)  # scripted urgent; old permission is revoked
        self.assertEqual(session.approvals.status(operation), "revoked")
        with self.assertRaises(ValueError):
            session.approvals.decide(preview, "approve")
        with self.assertRaises(InvalidOperation):
            session.approvals.preview(operation)

        # Bypass the I1 current-turn routing list deliberately. P3 itself
        # must refuse the old positive decision before any write attempt.
        denied = session.executor.execute([operation])
        self.assertEqual(denied["outcomes"][0]["status"], "blocked")
        self.assertEqual(denied["outcomes"][0]["reason"], "approval_revoked")
        with self.assertRaises(PermissionError):
            session.store.apply(operation, session.approvals)
        self.assertEqual(session.store.state, before)
        self.assertFalse(any(e["kind"] == "write_attempt" for e in session.store.events))

    def test_verified_and_attempted_outcomes_survive_urgent_supersession(self):
        session = make("j2", faults={"calendar-t1": "before_failure"})
        stage = session.advance(1)
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        first = session.execute()
        self.assertEqual([o["status"] for o in first["outcomes"]],
                         ["verified", "verified", "failed"])
        self.assertIn("attempted", first["outcomes"][2]["history"])
        recorded = deepcopy(first["outcomes"])
        existing_state = session.store.state
        urgent = session.advance(2)
        self.assertEqual(urgent["withdrawn_operation_ids"], [])
        self.assertEqual([o["status"] for o in urgent["prior_outcomes"]],
                         ["verified", "verified", "failed"])
        self.assertTrue(all(o["turn"] == 1 for o in urgent["prior_outcomes"]))
        for prior, original in zip(urgent["prior_outcomes"], recorded):
            for field in ("request_id", "operation_id", "status", "reason", "history"):
                self.assertEqual(prior[field], original[field])
        final = session.execute()
        self.assertEqual(final["status"], "urgent_escalated")
        self.assertEqual(final["outcomes"], [])
        self.assertEqual(final["prior_outcomes"], urgent["prior_outcomes"])
        self.assertEqual(final["cumulative_outcomes"], urgent["prior_outcomes"])
        self.assertEqual(final["cumulative_status"], "partial")
        self.assertEqual(session.store.state, existing_state)

    def test_unknown_timeout_survives_new_urgent_turn_without_retry(self):
        session = make("j2", faults={"calendar-t1": "before_timeout"})
        stage = session.advance(1)
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        result = session.execute()
        self.assertEqual([o["status"] for o in result["outcomes"]],
                         ["verified", "verified", "unknown"])
        uncertain = deepcopy(result["outcomes"][2])
        self.assertIn("attempted", uncertain["history"])
        before = session.store.state
        urgent = session.advance(2)
        self.assertEqual(urgent["withdrawn_operation_ids"], [])
        self.assertEqual(urgent["prior_outcomes"][2]["status"], "unknown")
        self.assertEqual(urgent["prior_outcomes"][2]["history"], uncertain["history"])
        final = session.execute()
        self.assertEqual(final["cumulative_outcomes"][2]["status"], "unknown")
        self.assertEqual(final["cumulative_outcomes"][2]["history"], uncertain["history"])
        self.assertEqual(final["cumulative_status"], "partial")
        self.assertEqual(session.store.state, before)
        attempts = [e for e in session.store.events
                    if e["kind"] == "write_attempt" and e["operation_id"] == "calendar-t1"]
        self.assertEqual(len(attempts), 1)

    def test_rechecked_unknown_preserves_original_attempt_history(self):
        session = make("j2", faults={"calendar-t1": "before_timeout"})
        stage = session.advance(1)
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        session.execute()
        second = session.execute()
        session.advance(2)
        prior = session.execute()["prior_outcomes"]
        self.assertEqual(prior[2]["status"], "unknown")
        self.assertIn("attempted", prior[2]["history"])
        self.assertIn("rechecked", prior[2]["history"])
        self.assertEqual(second["outcomes"][2]["status"], "unknown")

    def test_superseded_unknown_can_be_readback_verified_without_reapproval(self):
        session = make("j2", faults={"calendar-t1": "readback_unavailable"})
        stage = session.advance(1)
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        before = session.execute()
        self.assertEqual([o["status"] for o in before["outcomes"]],
                         ["verified", "verified", "unknown"])
        attempt_history = deepcopy(before["outcomes"][2]["history"])
        self.assertIn("attempted", attempt_history)
        old_preview = stage["previews"][2]
        old_operation = {k: deepcopy(old_preview[k]) for k in (
            "request_id", "operation_id", "owner", "destination",
            "expected_revision", "change")}
        snapshot = session.store.state
        session.advance(2)  # scripted urgency revokes all prior approvals
        self.assertEqual(session.approvals.status(old_operation), "revoked")
        self.assertEqual(session.executor.execute([old_operation])["outcomes"][0]["reason"],
                         "approval_revoked")
        session.store._faults.pop("calendar-t1")  # provider readback becomes accessible
        prior_attempts = len([e for e in session.store.events
                              if e["kind"] == "write_attempt"])
        inspected = session.reconcile("calendar-t1", requester_owner="calendar")
        self.assertEqual(inspected["status"], "verified")
        self.assertEqual(inspected["outcome"]["initial_reason"], "unverified_readback")
        self.assertEqual(inspected["outcome"]["history"][:len(attempt_history)],
                         attempt_history)
        self.assertEqual(inspected["outcome"]["history"][-2:],
                         ["inspection_only", "verified"])
        self.assertEqual(session.approvals.status(old_operation), "revoked")
        with self.assertRaises(PermissionError):
            session.reconcile("calendar-t1", requester_owner="calendar")  # no eligible read grant
        cumulative = session.execute()
        self.assertEqual([o["status"] for o in cumulative["cumulative_outcomes"]],
                         ["verified", "verified", "verified"])
        self.assertEqual(cumulative["cumulative_status"], "verified")
        self.assertEqual(cumulative["status"], "urgent_escalated")
        self.assertEqual(session.store.state, snapshot)
        self.assertEqual(len([e for e in session.store.events
                              if e["kind"] == "write_attempt"]), prior_attempts)

    def test_superseded_unapplied_unknown_remains_unknown_and_is_never_retried(self):
        session = make("j2", faults={"calendar-t1": "before_timeout"})
        stage = session.advance(1)
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        first = session.execute()
        self.assertEqual(first["outcomes"][2]["status"], "unknown")
        before_state = session.store.state
        session.advance(2)
        writes = len([e for e in session.store.events if e["kind"] == "write_attempt"])
        first_inspection = session.reconcile("calendar-t1", requester_owner="calendar")
        second_inspection = session.reconcile("calendar-t1", requester_owner="calendar")
        self.assertEqual([first_inspection["status"], second_inspection["status"]],
                         ["unknown", "unknown"])
        report = session.execute()
        old = report["cumulative_outcomes"][2]
        self.assertEqual(old["status"], "unknown")
        self.assertIn("attempted", old["history"])
        self.assertEqual(old["history"].count("inspection_only"), 2)
        self.assertEqual(report["cumulative_status"], "partial")
        self.assertEqual(session.store.state, before_state)
        self.assertEqual(len([e for e in session.store.events
                              if e["kind"] == "write_attempt"]), writes)
        with self.assertRaises(PermissionError):
            session.reconcile("purchase-t1")  # verified, no recovery read grant
        with self.assertRaises(PermissionError):
            session.reconcile("arbitrary-id")

    def test_foreign_or_unpermitted_requester_cannot_recover_j2_calendar_evidence(self):
        session = make("j2", faults={"calendar-t1": "readback_unavailable"})
        stage = session.advance(1)
        for preview in stage["previews"]:
            session.decide(preview, "approve")
        result = session.execute()
        self.assertEqual(result["outcomes"][2]["status"], "unknown")
        session.advance(2)  # urgent, all old write approvals revoked
        old = deepcopy(session.execute()["prior_outcomes"][2])
        before = session.store.state
        inspection_events = [e for e in session.store.events
                             if e["kind"] in {"inspect", "readback"}]
        for requester in ("health", "purchase", None, "unrecognized-owner"):
            with self.subTest(requester=requester):
                with self.assertRaises(PermissionError):
                    session.reconcile("calendar-t1", requester_owner=requester)
        # Even the correct owner loses access when its independent MOCK read
        # permission is absent; old approved writes do not grant inspection.
        grant = ("calendar", "fictional-i1-j2", "calendar-t1", "mock:calendar")
        session._recovery_read_permissions.remove(grant)
        with self.assertRaises(PermissionError):
            session.reconcile("calendar-t1", requester_owner="calendar")
        self.assertEqual([e for e in session.store.events
                          if e["kind"] in {"inspect", "readback"}],
                         inspection_events)
        self.assertEqual(session.store.state, before)
        self.assertEqual(session.execute()["prior_outcomes"][2], old)
        self.assertEqual(session.approvals.status({
            key: deepcopy(stage["previews"][2][key]) for key in (
                "request_id", "operation_id", "owner", "destination",
                "expected_revision", "change")}), "revoked")
        self.assertEqual(len([e for e in session.store.events
                              if e["kind"] == "write_attempt"]), 3)

    def test_unauthorized_known_and_absent_recovery_ids_are_indistinguishable(self):
        session = make("j2", faults={"calendar-t1": "readback_unavailable"})
        for preview in session.advance(1)["previews"]:
            session.decide(preview, "approve")
        self.assertEqual(session.execute()["outcomes"][2]["status"], "unknown")
        session.advance(2)  # old operation exists, but its write approval is revoked
        self.assertIn("calendar-t1", session._prior_uncertain)
        before_history = deepcopy(session._prior_outcomes)
        before_state = session.store.state
        before_events = session.store.events
        before_grants = set(session._recovery_read_permissions)

        class NoRecordLookup:
            def get(self, *_):
                raise AssertionError("unauthorized lookup read recovery record")
            def __getitem__(self, *_):
                raise AssertionError("unauthorized lookup read recovery record")
            def __contains__(self, *_):
                raise AssertionError("unauthorized lookup checked recovery record")
            def __iter__(self):
                raise AssertionError("unauthorized lookup read outcome history")

        def denials(cases):
            responses = []
            with (patch.object(session, "_prior_uncertain", NoRecordLookup()),
                  patch.object(session, "_prior_outcomes", NoRecordLookup()),
                  patch.object(session.executor, "inspect_only",
                               side_effect=AssertionError("unauthorized provider inspection")),
                  patch.object(session.store, "inspect",
                               side_effect=AssertionError("unauthorized record inspection")),
                  patch.object(session.store, "readback",
                               side_effect=AssertionError("unauthorized record readback"))):
                for requester, operation_id in cases:
                    with self.subTest(requester=requester, operation_id=operation_id):
                        with self.assertRaises(PermissionError) as denied:
                            session.reconcile(operation_id, requester_owner=requester)
                        responses.append((type(denied.exception), str(denied.exception)))
            self.assertTrue(responses)
            self.assertEqual(len(set(responses)), 1)
            self.assertEqual(responses[0],
                             (PermissionError, "recovery read not authorized"))

        # A foreign owner, absent requester and unknown operation ID all
        # produce the same outward failure, with no access to internal records.
        denials([
            ("health", "calendar-t1"), ("health", "not-a-real-recovery"),
            (None, "calendar-t1"), (None, "not-a-real-recovery"),
            ("calendar", "not-a-real-recovery"),
        ])

        # Possessing the correct owner name is still insufficient without
        # independent recovery-read permission, regardless of ID existence.
        grant = ("calendar", "fictional-i1-j2", "calendar-t1", "mock:calendar")
        session._recovery_read_permissions.remove(grant)
        denials([
            ("calendar", "calendar-t1"), ("calendar", "not-a-real-recovery"),
            ("health", "calendar-t1"), ("health", "not-a-real-recovery"),
        ])

        self.assertEqual(session._prior_outcomes, before_history)
        self.assertEqual(session.store.state, before_state)
        self.assertEqual(session.store.events, before_events)
        self.assertEqual(session._prior_uncertain["calendar-t1"]["owner"], "calendar")
        self.assertEqual(before_grants - session._recovery_read_permissions, {grant})
        self.assertEqual(len([e for e in session.store.events
                              if e["kind"] == "write_attempt"]), 3)

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
