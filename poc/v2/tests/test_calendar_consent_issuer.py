"""Fictional, fully offline consent issuer and registry CAS regression tests."""
import tempfile
from pathlib import Path
import sqlite3
import unittest

from v2_poc.calendar_approval import APPROVAL_ACTION, plan_digest
from v2_poc.calendar_consent_issuer import (
    OfflineConsentIssuer, _encode, _SESSION_AUDIENCE, _UI_AUDIENCE,
)
from v2_poc.calendar_gateway import CalendarGateway, IntentLedger
from v2_poc.calendar_rest_intent import plan_insert


NOW = 1_000_000
SESSION_KEY = b"synthetic-independent-session-root-32"
UI_KEY = b"synthetic-independent-ui-consent-root-32"
ISSUER_KEY = b"synthetic-independent-approval-root-32"
INTENT_KEY = b"synthetic-calendar-identity-key-32bytes"
CALENDAR = "fictional-calendar-for-consent"
SUBJECT = "fictional-subject"
SID = "fictional-session-identifier-a"
START = "2030-01-15T09:00:00+01:00"
END = "2030-01-15T09:30:00+01:00"
ZONE = "Europe/Amsterdam"


class PermitSyntheticRole:
    def verify(self, token, *, calendar_id, allowed_roles, operation_id):
        if token != "synthetic-executor" or "calendar_executor" not in allowed_roles:
            raise PermissionError("role denied")
        return "calendar_executor"


class ConsentIssuerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name) / "synthetic.sqlite"
        self.now = [NOW]
        self.ledger = IntentLedger(
            self.path, require_approval_registry=True, clock=lambda: self.now[0])
        self.issuer = self.make_issuer()
        self.plan = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR,
            operation_id="fictional-operation-a", request_id="fictional-request-a",
            start=START, end=END, timezone_name=ZONE)
        self.ledger.prepare("fictional-operation-a", self.plan)
        self.gateway = CalendarGateway(
            calendar_id=CALENDAR, intent_key=INTENT_KEY,
            verifier=PermitSyntheticRole(), ledger=self.ledger,
            oauth=None, read_event=None, approval_verifier=self.issuer)

    def make_issuer(self):
        return OfflineConsentIssuer(
            self.path, session_key=SESSION_KEY, ui_key=UI_KEY,
            approval_key=ISSUER_KEY, clock=lambda: self.now[0])

    def session(self, *, sub=SUBJECT, sid=SID, key=SESSION_KEY, exp=None):
        return _encode({
            "iss": "agency-session", "aud": _SESSION_AUDIENCE, "sub": sub,
            "sid": sid, "exp": exp if exp is not None else self.now[0] + 600,
        }, key)

    def confirmation(self, challenge, *, session=None, decision="approved",
                     changes=None, key=UI_KEY):
        session = session or (SUBJECT, SID)
        claims = {
            "iss": "agency-consent-ui", "aud": _UI_AUDIENCE,
            "sub": session[0], "sid": session[1],
            "action": APPROVAL_ACTION, "decision": decision,
            "challenge_id": challenge["challenge_id"],
            "plan_sha256": challenge["plan_sha256"],
            "exp": self.now[0] + 60,
        }
        claims.update(changes or {})
        return _encode(claims, key)

    def prepare_approval(self):
        row = self.ledger.get("fictional-operation-a")
        ch = self.issuer.begin(session_proof=self.session(), row=row)
        token = self.confirmation(ch)
        issued = self.issuer.decide(
            session_proof=self.session(), confirmation_proof=token)
        return row, ch, issued

    def test_exact_session_and_ui_proof_issue_once_with_safe_preview(self):
        row = self.ledger.get("fictional-operation-a")
        challenge = self.issuer.begin(session_proof=self.session(), row=row)
        self.assertEqual(challenge["display"]["event_id"], self.plan["body"]["id"])
        self.assertEqual(challenge["display"]["start"], self.plan["body"]["start"])
        self.assertEqual(challenge["display"]["visibility"], "private")
        self.assertEqual(challenge["display"]["reminders"],
                         {"useDefault": False, "overrides": []})
        self.assertEqual(challenge["plan_sha256"], plan_digest(self.plan))
        issued = self.issuer.decide(
            session_proof=self.session(),
            confirmation_proof=self.confirmation(challenge))
        self.assertEqual(issued["status"], "issued")
        self.assertEqual(self.issuer.verify(
            issued["approval_proof"], expected_row=row), issued["approval_id"])
        with self.assertRaises(PermissionError):
            self.issuer.decide(
                session_proof=self.session(),
                confirmation_proof=self.confirmation(challenge))
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")

    def test_untrusted_session_wrong_ui_session_and_decline_fail_closed(self):
        row = self.ledger.get("fictional-operation-a")
        with self.assertRaises(PermissionError):
            self.issuer.begin(session_proof=self.session(key=UI_KEY), row=row)
        with self.assertRaises(PermissionError):
            self.issuer.begin(session_proof=self.session(sid="bad"), row=row)
        ch = self.issuer.begin(session_proof=self.session(), row=row)
        for changes in (
            {"sub": "another-subject"},
            {"sid": "different-session-identifier"},
            {"plan_sha256": "0" * 64},
            {"action": "calendar.event.delete"},
            {"aud": "not-this-service"},
            {"exp": self.now[0] - 1},
        ):
            with self.subTest(changes=changes), self.assertRaises(PermissionError):
                self.issuer.decide(
                    session_proof=self.session(),
                    confirmation_proof=self.confirmation(ch, changes=changes))
        with self.assertRaises(PermissionError):
            self.issuer.decide(
                session_proof=self.session(),
                confirmation_proof=self.confirmation(ch, key=SESSION_KEY))
        declined = self.issuer.decide(
            session_proof=self.session(),
            confirmation_proof=self.confirmation(ch, decision="declined"))
        self.assertEqual(declined, {"status": "declined"})
        with self.assertRaises(PermissionError):
            self.issuer.decide(
                session_proof=self.session(),
                confirmation_proof=self.confirmation(ch))
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")

    def test_challenge_and_receipt_expiry_restart_replay_and_revocation(self):
        row = self.ledger.get("fictional-operation-a")
        ch = self.issuer.begin(session_proof=self.session(), row=row)
        self.now[0] += 121
        with self.assertRaises(PermissionError):
            self.issuer.decide(
                session_proof=self.session(),
                confirmation_proof=self.confirmation(ch))
        self.now[0] = NOW
        row, _, issued = self.prepare_approval()
        rebooted = self.make_issuer()
        self.assertEqual(rebooted.verify(
            issued["approval_proof"], expected_row=row), issued["approval_id"])
        with self.assertRaises(PermissionError):
            rebooted.revoke(session_proof=self.session(
                sub="another-person"), approval_id=issued["approval_id"])
        self.assertEqual(rebooted.revoke(
            session_proof=self.session(),
            approval_id=issued["approval_id"]), {"status": "revoked"})
        with self.assertRaises(PermissionError):
            rebooted.verify(issued["approval_proof"], expected_row=row)
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")
        with self.assertRaises(PermissionError):
            rebooted.revoke(session_proof=self.session(),
                            approval_id=issued["approval_id"])

    def test_atomic_attempt_consumes_receipt_and_blocks_revoke_race(self):
        row, _, issued = self.prepare_approval()
        reopened = IntentLedger(
            self.path, require_approval_registry=True,
            clock=lambda: self.now[0])
        self.gateway._ledger = reopened
        result = self.gateway.record_attempt(
            "synthetic-executor", operation_id="fictional-operation-a",
            approval_evidence=issued["approval_proof"])
        self.assertEqual(result, {"status": "unknown", "external_actions": 0})
        self.assertEqual(reopened.get("fictional-operation-a")["status"], "unknown")
        with self.issuer._db() as db:
            receipt = db.execute(
                "SELECT state FROM consent_receipts WHERE approval_id=?",
                (issued["approval_id"],)).fetchone()
        self.assertEqual(receipt, ("consumed",))
        with self.assertRaises(PermissionError):
            self.issuer.revoke(
                session_proof=self.session(), approval_id=issued["approval_id"])
        with self.assertRaises(PermissionError):
            self.issuer.verify(issued["approval_proof"], expected_row=row)

    def test_revocation_between_verify_and_cas_never_marks_attempted(self):
        _, _, issued = self.prepare_approval()
        issuer = self.issuer
        class RevokingVerifier:
            def verify(self, proof, *, expected_row):
                ident = issuer.verify(proof, expected_row=expected_row)
                issuer.revoke(
                    session_proof=self_outer.session(), approval_id=ident)
                return ident
        self_outer = self
        self.gateway._approval_verifier = RevokingVerifier()
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")
        with issuer._db() as db:
            self.assertEqual(db.execute(
                "SELECT state FROM consent_receipts WHERE approval_id=?",
                (issued["approval_id"],)).fetchone(), ("revoked",))

    def test_receipt_expiry_between_verify_and_cas_fails_closed(self):
        _, _, issued = self.prepare_approval()
        issuer = self.issuer
        class DelayedVerifier:
            def verify(self, proof, *, expected_row):
                ident = issuer.verify(proof, expected_row=expected_row)
                now_ref[0] += 61
                return ident
        now_ref = self.now
        self.gateway._approval_verifier = DelayedVerifier()
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")


if __name__ == "__main__":
    unittest.main()
