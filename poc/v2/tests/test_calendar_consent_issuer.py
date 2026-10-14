"""Fictional, fully offline consent issuer and registry CAS regression tests."""
import tempfile
from contextlib import contextmanager
import hashlib
import hmac
import json
import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pathlib import Path
import sqlite3
import unittest

from v2_poc.calendar_approval import APPROVAL_ACTION, plan_digest, OfflineApprovalVerifier
from v2_poc.calendar_consent_issuer import (
    OfflineConsentIssuer, _encode, _SESSION_AUDIENCE, _UI_AUDIENCE,
)
from v2_poc.calendar_gateway import CalendarGateway, IntentLedger
from v2_poc.calendar_rest_intent import plan_insert


NOW = 1_000_000
SESSION_KEY = b"synthetic-independent-session-root-32"
UI_KEY = b"synthetic-independent-ui-consent-root-32"
APPROVAL_PRIVATE = Ed25519PrivateKey.from_private_bytes(
    hashlib.sha256(b"fictional-consent-signing-key-one").digest())
APPROVAL_PRIVATE_NEW = Ed25519PrivateKey.from_private_bytes(
    hashlib.sha256(b"fictional-consent-signing-key-two").digest())
KID1 = "fictional-consent-v1"
KID2 = "fictional-consent-v2"
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
        self.public_verifier = self.make_verifier()
        self.plan = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR,
            operation_id="fictional-operation-a", request_id="fictional-request-a",
            start=START, end=END, timezone_name=ZONE)
        self.ledger.prepare("fictional-operation-a", self.plan)
        self.gateway = CalendarGateway(
            calendar_id=CALENDAR, intent_key=INTENT_KEY,
            verifier=PermitSyntheticRole(), ledger=self.ledger,
            oauth=None, read_event=None,
            approval_verifier=self.public_verifier)

    def make_issuer(self, *, private=APPROVAL_PRIVATE, kid=KID1):
        return OfflineConsentIssuer(
            self.path, session_key=SESSION_KEY, ui_key=UI_KEY,
            approval_private_key=private, approval_key_id=kid,
            clock=lambda: self.now[0])

    def make_verifier(self, *, include_second=False):
        ring = {KID1: APPROVAL_PRIVATE.public_key()}
        if include_second:
            ring[KID2] = APPROVAL_PRIVATE_NEW.public_key()
        return OfflineApprovalVerifier(
            verification_keys=ring, clock=lambda: self.now[0])

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
        self.assertEqual(challenge["display"]["transparency"], "transparent")
        self.assertEqual(challenge["display"]["attendees"], [])
        self.assertEqual(challenge["display"]["insert_params"], self.plan["insert_params"])
        self.assertEqual(challenge["plan_sha256"], plan_digest(self.plan))
        issued = self.issuer.decide(
            session_proof=self.session(),
            confirmation_proof=self.confirmation(challenge))
        self.assertEqual(issued["status"], "issued")
        self.assertEqual(self.public_verifier.verify(
            issued["approval_proof"], expected_row=row), (issued["approval_id"], KID1))
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
        self.assertEqual(self.make_verifier().verify(
            issued["approval_proof"], expected_row=row), (issued["approval_id"], KID1))
        with self.assertRaises(PermissionError):
            rebooted.revoke(session_proof=self.session(
                sub="another-person"), approval_id=issued["approval_id"])
        self.assertEqual(rebooted.revoke(
            session_proof=self.session(),
            approval_id=issued["approval_id"]), {"status": "revoked"})
        # Revocation is registry state, not a signature failure.
        self.assertEqual(self.public_verifier.verify(
            issued["approval_proof"], expected_row=row),
            (issued["approval_id"], KID1))
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
        # Consumed receipt cannot authorize a second attempt despite a valid signature.
        self.assertEqual(self.public_verifier.verify(
            issued["approval_proof"], expected_row=row),
            (issued["approval_id"], KID1))

    def test_revocation_between_verify_and_cas_never_marks_attempted(self):
        _, _, issued = self.prepare_approval()
        issuer = self.issuer
        public = self.public_verifier
        class RevokingVerifier:
            def verify(self, proof, *, expected_row):
                ident, kid = public.verify(proof, expected_row=expected_row)
                issuer.revoke(
                    session_proof=self_outer.session(), approval_id=ident)
                return ident, kid
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
        public = self.public_verifier
        class DelayedVerifier:
            def verify(self, proof, *, expected_row):
                ident, kid = public.verify(proof, expected_row=expected_row)
                now_ref[0] += 61
                return ident, kid
        now_ref = self.now
        self.gateway._approval_verifier = DelayedVerifier()
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")


    def test_issuer_rotation_retains_old_receipts_and_requires_new_public_trust(self):
        row, _, old = self.prepare_approval()
        new_issuer = self.make_issuer(private=APPROVAL_PRIVATE_NEW, kid=KID2)
        self.assertEqual(self.issuer.set_key_state(KID1, state="retired"),
                         {"status": "retired"})
        self.assertEqual(self.public_verifier.verify(
            old["approval_proof"], expected_row=row), (old["approval_id"], KID1))
        # A retired key can verify preexisting short-lived receipts, but
        # cannot issue new approvals.
        pending = self.issuer.begin(session_proof=self.session(), row=row)
        with self.assertRaises(PermissionError):
            self.issuer.decide(
                session_proof=self.session(),
                confirmation_proof=self.confirmation(pending))

        other = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR, request_id="fictional-request-b",
            operation_id="fictional-operation-b",
            start=START, end=END, timezone_name=ZONE)
        self.ledger.prepare("fictional-operation-b", other)
        new_row = self.ledger.get("fictional-operation-b")
        challenge = new_issuer.begin(session_proof=self.session(), row=new_row)
        new = new_issuer.decide(
            session_proof=self.session(),
            confirmation_proof=self.confirmation(challenge))
        with self.assertRaises(PermissionError):
            self.public_verifier.verify(
                new["approval_proof"], expected_row=new_row)
        self.gateway._approval_verifier = self.make_verifier(include_second=True)
        self.assertEqual(self.gateway.record_attempt(
            "synthetic-executor", operation_id="fictional-operation-b",
            approval_evidence=new["approval_proof"])["status"], "unknown")
        self.assertEqual(self.gateway.record_attempt(
            "synthetic-executor", operation_id="fictional-operation-a",
            approval_evidence=old["approval_proof"])["status"], "unknown")
        with new_issuer._db() as db:
            rows = dict(db.execute(
                "SELECT key_id,state FROM consent_signing_keys").fetchall())
        self.assertEqual(rows, {KID1: "retired", KID2: "active"})

    def test_compromised_key_quarantines_unconsumed_approval(self):
        row, _, issued = self.prepare_approval()
        self.assertEqual(self.public_verifier.verify(
            issued["approval_proof"], expected_row=row),
            (issued["approval_id"], KID1))
        self.assertEqual(self.issuer.set_key_state(KID1, state="compromised"),
                         {"status": "compromised"})
        with self.issuer._db() as db:
            self.assertEqual(db.execute(
                "SELECT state FROM consent_receipts WHERE approval_id=?",
                (issued["approval_id"],)).fetchone(), ("revoked",))
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")
        with self.assertRaises(PermissionError):
            self.issuer.set_key_state(KID1, state="retired")
        with self.assertRaises(PermissionError):
            self.issuer.set_key_state(KID1, state="compromised")
        with self.assertRaises(PermissionError):
            self.issuer.decide(
                session_proof=self.session(), confirmation_proof=self.confirmation(
                    self.issuer.begin(
                        session_proof=self.session(),
                        row=self.ledger.get("fictional-operation-a"))))

    def test_compromise_between_verification_and_cas_fails_closed(self):
        _, _, issued = self.prepare_approval()
        public, issuer = self.public_verifier, self.issuer

        class CompromiseBetweenReads:
            def verify(self, proof, *, expected_row):
                validated = public.verify(proof, expected_row=expected_row)
                issuer.set_key_state(KID1, state="compromised")
                return validated

        self.gateway._approval_verifier = CompromiseBetweenReads()
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")

    def test_signer_spoof_and_key_id_receipt_mismatch_denied(self):
        row, _, issued = self.prepare_approval()
        body, sig = issued["approval_proof"].split(".")
        claims = json.loads(base64.urlsafe_b64decode(
            body + "=" * (-len(body) % 4)))
        for changes in ({"kid": KID2}, {"alg": "HS256"},
                        {"typ": "unexpected"}, {"plan_sha256": "0" * 64}):
            altered = dict(claims, **changes)
            encoded = base64.urlsafe_b64encode(json.dumps(
                altered, sort_keys=True, separators=(",", ":")).encode()
            ).decode().rstrip("=")
            with self.subTest(changes=changes):
                with self.assertRaises(PermissionError):
                    self.make_verifier(include_second=True).verify(
                        encoded + "." + sig, expected_row=row)
        with self.assertRaises(ValueError):
            OfflineApprovalVerifier(
                verification_keys={KID1: APPROVAL_PRIVATE})
        with self.assertRaises(ValueError):
            self.make_issuer(private=APPROVAL_PRIVATE_NEW, kid=KID1)

        # An old signing key cannot claim a receipt whose provenance is
        # registered to the new signing key, even when all intent fields match.
        newer = self.make_issuer(private=APPROVAL_PRIVATE_NEW, kid=KID2)
        second = newer.decide(
            session_proof=self.session(),
            confirmation_proof=self.confirmation(newer.begin(
                session_proof=self.session(), row=row)))
        new_body = second["approval_proof"].split(".")[0]
        new_claims = json.loads(base64.urlsafe_b64decode(
            new_body + "=" * (-len(new_body) % 4)))
        new_claims["kid"] = KID1
        old_body = base64.urlsafe_b64encode(json.dumps(
            new_claims, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        old_sig = base64.urlsafe_b64encode(
            APPROVAL_PRIVATE.sign(old_body.encode())).decode().rstrip("=")
        self.gateway._approval_verifier = self.make_verifier(include_second=True)
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=old_body + "." + old_sig)
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "prepared")


    def test_key_policy_read_is_under_write_lock_before_attempt_cas(self):
        """A second connection cannot quarantine after a stale policy SELECT."""
        _, _, issued = self.prepare_approval()
        original_db = self.ledger._db
        testcase, path = self, self.path
        observed = []

        @contextmanager
        def guarded_db():
            with original_db() as db:
                class ConnectionSpy:
                    def execute(self, sql, params=()):
                        if "SELECT r.state,r.expires_at" in sql:
                            other = sqlite3.connect(path, timeout=0)
                            try:
                                with testcase.assertRaises(sqlite3.OperationalError):
                                    other.execute("""UPDATE consent_signing_keys
                                        SET state='compromised'
                                        WHERE key_id=?""", (KID1,))
                                observed.append("locked-before-read")
                            finally:
                                other.close()
                        return db.execute(sql, params)
                yield ConnectionSpy()

        self.ledger._db = guarded_db
        result = self.gateway.record_attempt(
            "synthetic-executor", operation_id="fictional-operation-a",
            approval_evidence=issued["approval_proof"])
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(observed, ["locked-before-read"])

    def test_challenge_decision_is_serialized_before_pending_read(self):
        row = self.ledger.get("fictional-operation-a")
        challenge = self.issuer.begin(session_proof=self.session(), row=row)
        original_db = self.issuer._db
        testcase, path = self, self.path
        observed = []

        @contextmanager
        def guarded_db():
            with original_db() as db:
                class ConnectionSpy:
                    def execute(self, sql, params=()):
                        if "SELECT subject,session_id,calendar_id" in sql:
                            other = sqlite3.connect(path, timeout=0)
                            try:
                                with testcase.assertRaises(sqlite3.OperationalError):
                                    other.execute("""UPDATE consent_challenges
                                        SET state='declined' WHERE challenge_id=?""",
                                        (challenge["challenge_id"],))
                                observed.append("locked-before-decision")
                            finally:
                                other.close()
                        return db.execute(sql, params)
                yield ConnectionSpy()

        self.issuer._db = guarded_db
        result = self.issuer.decide(
            session_proof=self.session(),
            confirmation_proof=self.confirmation(challenge))
        self.assertEqual(result["status"], "issued")
        self.assertEqual(observed, ["locked-before-decision"])


    def test_legacy_hmac_approval_is_not_accepted(self):
        row, _, issued = self.prepare_approval()
        body = issued["approval_proof"].split(".")[0]
        claims = json.loads(base64.urlsafe_b64decode(
            body + "=" * (-len(body) % 4)))
        claims["alg"] = "HS256"
        altered = base64.urlsafe_b64encode(json.dumps(
            claims, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        old_hmac = base64.urlsafe_b64encode(hmac.new(
            b"synthetic-retired-hmac-approval-secret",
            altered.encode(), hashlib.sha256).digest()).decode().rstrip("=")
        with self.assertRaises(PermissionError):
            self.public_verifier.verify(
                altered + "." + old_hmac, expected_row=row)

    def test_compromise_after_consumption_cannot_undo_attempt_history(self):
        _, _, issued = self.prepare_approval()
        self.gateway.record_attempt(
            "synthetic-executor", operation_id="fictional-operation-a",
            approval_evidence=issued["approval_proof"])
        self.issuer.set_key_state(KID1, state="compromised")
        self.assertEqual(self.ledger.get("fictional-operation-a")["status"],
                         "unknown")
        with self.issuer._db() as db:
            self.assertEqual(db.execute(
                "SELECT state FROM consent_receipts WHERE approval_id=?",
                (issued["approval_id"],)).fetchone(), ("consumed",))
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                "synthetic-executor", operation_id="fictional-operation-a",
                approval_evidence=issued["approval_proof"])


if __name__ == "__main__":
    unittest.main()
