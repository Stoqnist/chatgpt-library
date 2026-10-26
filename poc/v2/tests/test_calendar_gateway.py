"""Offline-only Calendar Gateway authorization / recovery regression suite."""
import base64
import hashlib
import hmac
import json
import sqlite3
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from v2_poc.calendar_gateway_oauth import OfflineOAuth, ReauthorizationRequired
from v2_poc.calendar_approval import OfflineApprovalVerifier, plan_digest, APPROVAL_ACTION
from v2_poc.calendar_gateway import (
    CalendarGateway, IntentLedger, READ_FIELDS, VerifiedAgent,
)


class Vault:
    def __init__(self):
        self.contents = None
        self.writes = []

    def load(self):
        return self.contents

    def save(self, value):
        self.contents = dict(value)
        self.writes.append(dict(value))


class OAuthTests(unittest.TestCase):
    SCOPES = ("https://www.googleapis.com/auth/calendar.events.owned",)

    def setUp(self):
        self.vault = Vault()
        self.calls = []
        self.clock = 1_000_000

        def exchange(form):
            self.calls.append(dict(form))
            if form["grant_type"] == "authorization_code":
                return {"refresh_token": "refresh-a", "scope": self.SCOPES[0]}
            return {"access_token": "access-1", "expires_in": 3600}
        self.exchange = exchange
        self.broker = OfflineOAuth(
            client_id="fictional-client", client_secret="fictional-secret",
            redirect_uri="https://example.invalid/oauth/callback",
            scopes=self.SCOPES, exchange=self.exchange, vault=self.vault,
            clock=lambda: self.clock)

    def _complete(self):
        url = self.broker.authorization_url()
        params = parse_qs(urlsplit(url).query)
        self.assertEqual(params["access_type"], ["offline"])
        self.assertEqual(params["code_challenge_method"], ["S256"])
        self.assertEqual(params["scope"], [self.SCOPES[0]])
        self.assertNotIn("client_secret", url)
        self.broker.complete(state=params["state"][0], code="one-use-code")
        self.assertNotIn("access_token", self.vault.contents)
        self.assertEqual(self.calls[0]["grant_type"], "authorization_code")
        self.assertEqual(self.calls[0]["code_verifier"] is not None, True)
        return params

    def test_offline_setup_and_silent_refresh_reuses_short_lived_token(self):
        self._complete()
        self.assertEqual(self.broker.access_token(), "access-1")
        self.assertEqual(self.broker.access_token(), "access-1")
        self.assertEqual(len(self.calls), 2)
        self.clock += 3601
        self.assertEqual(self.broker.access_token(), "access-1")
        self.assertEqual(len(self.calls), 3)
        self.assertEqual(self.vault.contents["refresh_token"], "refresh-a")

    def test_callback_state_one_time_wrong_state_and_missing_refresh(self):
        params = parse_qs(urlsplit(self.broker.authorization_url()).query)
        with self.assertRaises(ReauthorizationRequired):
            self.broker.complete(state="not-the-state", code="code")
        with self.assertRaises(ReauthorizationRequired):
            self.broker.complete(state=params["state"][0], code="code")
        self.assertIsNone(self.vault.contents)
        self.broker._exchange = lambda form: {"scope": self.SCOPES[0]}
        correct = parse_qs(urlsplit(self.broker.authorization_url()).query)
        with self.assertRaises(ReauthorizationRequired):
            self.broker.complete(state=correct["state"][0], code="code")
        self.assertIsNone(self.vault.contents)

    def test_scope_reduction_revocation_and_rotation_fail_closed(self):
        self._complete()
        self.broker._exchange = lambda form: {"access_token": "unexpected",
                                              "scope": "scope-not-granted",
                                              "expires_in": 3600}
        with self.assertRaises(ReauthorizationRequired):
            self.broker.access_token()
        self.broker._exchange = lambda form: {
            "access_token": "new-access", "refresh_token": "refresh-rotated",
            "expires_in": 3600, "scope": self.SCOPES[0]}
        self.assertEqual(self.broker.access_token(), "new-access")
        self.assertEqual(self.vault.contents["refresh_token"], "refresh-rotated")
        self.clock += 3601
        self.broker._exchange = lambda form: (_ for _ in ()).throw(
            ValueError("invalid_grant"))
        with self.assertRaises(ReauthorizationRequired):
            self.broker.access_token()
        self.assertEqual(self.vault.contents["refresh_token"], "refresh-rotated")

    def test_missing_persisted_refresh_needs_reauthorization(self):
        with self.assertRaises(ReauthorizationRequired):
            self.broker.access_token()
        with self.assertRaises(ValueError):
            OfflineOAuth(client_id="x", client_secret="y",
                         redirect_uri="http://example.invalid/callback",
                         scopes=self.SCOPES, exchange=self.exchange,
                         vault=self.vault)


KEY = b"gateway-unit-test-key-material-at-least-32"
INTENT_KEY = b"distinct-offline-calendar-identity-secret-32"
APPROVAL_PRIVATE = Ed25519PrivateKey.from_private_bytes(
    hashlib.sha256(b"obviously-fictional-approval-signing-fixture").digest())
APPROVAL_KID = "fictional-approval-k1"
CLOCK = 1_000_000
CALENDAR = "fictional-disposable-calendar"
REQUEST = "test-request-1"
START = "2026-10-20T10:00:00+02:00"
END = "2026-10-20T10:30:00+02:00"
ZONE = "Europe/Amsterdam"


def proof(role="calendar_recovery", calendar=CALENDAR, exp=CLOCK + 120, key=KEY,
          operation_id="test-op-1"):
    claims = {"sub": "trusted-broker", "role": role,
              "aud": "agency-calendar-gateway",
              "calendar": calendar, "operation_id": operation_id, "exp": exp}
    body = base64.urlsafe_b64encode(
        json.dumps(claims, sort_keys=True).encode()).decode().rstrip("=")
    sig = hmac.new(key, body.encode(), hashlib.sha256).digest()
    return body + "." + base64.urlsafe_b64encode(sig).decode().rstrip("=")


class TokenForTests:
    def __init__(self):
        self.calls = 0
        self.available = True

    def access_token(self):
        self.calls += 1
        if not self.available:
            raise RuntimeError("token unavailable")
        return "synthetic-access-token"


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "intents.sqlite"
        self.ledger = IntentLedger(self.db, require_approval_registry=False)
        self.oauth = TokenForTests()
        self.read_calls = []
        self.event = None
        self.approved = False

        def read_event(**kwargs):
            self.read_calls.append(kwargs)
            return self.event

        self.gateway = CalendarGateway(
            calendar_id=CALENDAR, intent_key=INTENT_KEY,
            verifier=VerifiedAgent(signing_key=KEY, clock=lambda: CLOCK),
            ledger=self.ledger, oauth=self.oauth, read_event=read_event,
            approval_verifier=OfflineApprovalVerifier(
                verification_keys={APPROVAL_KID: APPROVAL_PRIVATE.public_key()},
                clock=lambda: CLOCK),
            approve_intent=lambda row: self.approved)

    def prepare(self, op_id="test-op-1", request_id=REQUEST, start=START):
        return self.gateway.prepare(
            proof("calendar_executor", operation_id=op_id), operation_id=op_id,
            request_id=request_id, start_at=start, end_at=END,
            timezone_name=ZONE)

    def consent_proof(self, operation_id="test-op-1", *, changes=None):
        """A test-only fictional signing fixture, NEVER a runtime issuer."""
        row = self.ledger.get(operation_id)
        claims = {
            "iss": "agency-calendar-consent", "aud": "agency-calendar-approval",
            "typ": "agency-calendar-approval-v1", "alg": "EdDSA",
            "kid": APPROVAL_KID,
            "action": APPROVAL_ACTION, "decision": "approved",
            "sub": "fictional-user", "jti": "synthetic-approval-identifier-0001",
            "calendar_id": row["calendar_id"], "operation_id": row["operation_id"],
            "event_id": row["event_id"], "plan_sha256": plan_digest(row["plan"]),
            "exp": CLOCK + 120,
        }
        claims.update(changes or {})
        body = base64.urlsafe_b64encode(
            json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
        ).decode().rstrip("=")
        sig = base64.urlsafe_b64encode(
            APPROVAL_PRIVATE.sign(body.encode())
        ).decode().rstrip("=")
        return body + "." + sig

    def attempt(self):
        self.approved = True
        self.gateway.record_attempt(
            proof("calendar_executor"), operation_id="test-op-1",
            approval_evidence=self.consent_proof())

    def test_single_planner_owns_id_and_safe_body(self):
        from v2_poc.calendar_rest_intent import plan_insert
        event = self.prepare()
        expected = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR, request_id=REQUEST,
            operation_id="test-op-1", start=START, end=END,
            timezone_name=ZONE)
        self.assertEqual(event, expected["body"])
        self.assertRegex(event["id"], r"^[0-9a-v]{32}$")
        self.assertEqual(event["summary"], "Personal follow-up")
        self.assertEqual(event["visibility"], "private")
        self.assertEqual(event["transparency"], "transparent")
        self.assertEqual(event["reminders"], {"useDefault": False, "overrides": []})
        self.assertFalse(set(event) & {"attendees", "conferenceData", "description",
                                       "extendedProperties", "location"})
        self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")
        self.assertEqual(self.prepare(), event)
        self.assertEqual(self.read_calls, [])
        self.assertEqual(self.oauth.calls, 0)

    def test_invalid_claims_and_wrong_calendar_denied_before_lookup(self):
        class NeverReadLedger:
            def get(self, *_):
                raise AssertionError("unauthorized caller read store")
        self.gateway._ledger = NeverReadLedger()
        for token in (proof("health"), proof("calendar_recovery", "other"),
                      proof(exp=CLOCK - 1), proof(exp=CLOCK + 400),
                      proof(key=b"other-key-material-of-sufficient-length"),
                      "invalid", None):
            with self.subTest(token=str(token)[:22]):
                with self.assertRaises(PermissionError) as denied:
                    self.gateway.recover(token, operation_id="known-or-absent")
                self.assertEqual(str(denied.exception),
                                 "calendar recovery not authorized")
        self.assertEqual(self.read_calls, [])

    def test_missing_and_prepared_id_denied_without_provider_inspection(self):
        self.prepare()
        for opid in ("test-op-1", "does-not-exist"):
            with self.subTest(opid=opid):
                with self.assertRaises(PermissionError):
                    self.gateway.recover(proof(operation_id=opid),
                                         operation_id=opid)
        self.assertEqual(self.oauth.calls, 0)

    def test_approval_is_not_inferred_from_plan_or_role(self):
        self.prepare()
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1",
                approval_evidence=self.consent_proof())
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                proof("health"), operation_id="test-op-1",
                approval_evidence=self.consent_proof())
        self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")
        self.attempt()
        with self.assertRaises(ValueError):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1",
                approval_evidence=self.consent_proof())
        self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")

    def test_signed_approval_is_required_and_bound_to_exact_plan(self):
        self.prepare()
        self.approved = True
        invalid = [
            None, "", "not-a-proof",
            self.consent_proof(changes={"decision": "denied"}),
            self.consent_proof(changes={"action": "calendar.event.delete"}),
            self.consent_proof(changes={"iss": "untrusted-issuer"}),
            self.consent_proof(changes={"aud": "other-service"}),
            self.consent_proof(changes={"sub": ""}),
            self.consent_proof(changes={"calendar_id": "different-calendar"}),
            self.consent_proof(changes={"operation_id": "test-op-2"}),
            self.consent_proof(changes={"event_id": "wrong-event-id"}),
            self.consent_proof(changes={"plan_sha256": "0" * 64}),
            self.consent_proof(changes={"jti": "too-short"}),
            self.consent_proof(changes={"exp": CLOCK - 1}),
            self.consent_proof(changes={"exp": CLOCK + 301}),
        ]
        good = self.consent_proof()
        body, sig = good.split(".")
        invalid.append(body + "." + ("a" if sig[0] != "a" else "b") + sig[1:])
        for token in invalid:
            with self.subTest(token=str(token)[:48]):
                with self.assertRaises(PermissionError) as denied:
                    self.gateway.record_attempt(
                        proof("calendar_executor"), operation_id="test-op-1",
                        approval_evidence=token)
                self.assertEqual(str(denied.exception),
                                 "calendar approval unavailable")
                self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")
        self.assertEqual(self.oauth.calls, 0)
        self.assertEqual(self.read_calls, [])

    def test_approval_receipt_persists_and_cannot_reuse_on_other_operation(self):
        self.prepare()
        self.attempt()
        first = self.ledger.get("test-op-1")
        reopened = IntentLedger(self.db, require_approval_registry=False)
        with reopened._db() as db:
            approval_id = db.execute(
                "SELECT approval_id FROM calendar_intents WHERE operation_id=?",
                ("test-op-1",)).fetchone()[0]
        self.assertEqual(approval_id, "synthetic-approval-identifier-0001")
        self.assertEqual(first["status"], "unknown")

        self.gateway._ledger = reopened
        self.prepare(op_id="test-op-2")
        with self.assertRaises(sqlite3.IntegrityError):
            self.gateway.record_attempt(
                proof("calendar_executor", operation_id="test-op-2"),
                operation_id="test-op-2",
                approval_evidence=self.consent_proof("test-op-2"))
        self.assertEqual(reopened.get("test-op-2")["status"], "prepared")
        self.assertEqual(reopened.get("test-op-1")["status"], "unknown")

    def test_approval_checked_after_policy_callback_delay(self):
        self.prepare()
        self.approved = True
        current = [CLOCK]
        self.gateway._approval_verifier._clock = lambda: current[0]

        def expired_during_policy(_row):
            current[0] += 150
            return True

        self.gateway._approve_intent = expired_during_policy
        with self.assertRaisesRegex(PermissionError, "approval unavailable"):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1",
                approval_evidence=self.consent_proof())
        self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")

    def test_exact_identity_and_planner_comparator_are_required(self):
        event = self.prepare()
        self.attempt()
        good = {**event, "status": "confirmed"}
        for candidate in (None, {**good, "status": "cancelled"},
                          {**good, "id": "otherid"},
                          {**good, "start": {**good["start"], "dateTime":
                                               "2026-10-20T10:15:00+02:00"}},
                          {**good, "start": {"dateTime": START}}):
            self.event = candidate
            self.assertEqual(self.gateway.recover(
                proof(), operation_id="test-op-1"),
                {"status": "unknown", "external_actions": 0})
            self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")
        # Provider may convert offsets to UTC, while retaining the IANA zone.
        self.event = {**good, "start": {**event["start"],
                                       "dateTime": "2026-10-20T08:00:00Z"},
                      "end": {**event["end"],
                              "dateTime": "2026-10-20T08:30:00Z"}}
        self.assertEqual(self.gateway.recover(
            proof(), operation_id="test-op-1")["status"], "verified")
        self.assertEqual(self.read_calls[-1]["fields"], READ_FIELDS)
        self.assertEqual(self.read_calls[-1]["event_id"], event["id"])
        self.assertEqual(self.read_calls[-1]["calendar_id"], CALENDAR)
        self.assertEqual(self.ledger.get("test-op-1")["status"], "verified")
        self.event = None
        self.assertEqual(self.gateway.recover(
            proof(), operation_id="test-op-1")["status"], "unknown")
        self.assertEqual(self.ledger.get("test-op-1")["status"], "verified")

    def test_assertion_is_scoped_to_exact_operation_before_record_lookup(self):
        class NeverReadLedger:
            def get(self, *_):
                raise AssertionError("cross-operation lookup occurred")
        self.gateway._ledger = NeverReadLedger()
        with self.assertRaises(PermissionError) as denied:
            self.gateway.recover(proof(operation_id="test-op-1"),
                                 operation_id="test-op-2")
        self.assertEqual(str(denied.exception), "calendar recovery not authorized")
        self.assertEqual(self.oauth.calls, 0)
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                proof("calendar_executor", operation_id="test-op-1"),
                operation_id="test-op-2", approval_evidence="invalid-proof")

    def test_recovery_denies_changed_privacy_or_notifications(self):
        event = self.prepare()
        self.attempt()
        for key, changed in (
                ("summary", "Patient follow-up"),
                ("visibility", "public"),
                ("transparency", "opaque"),
                ("attendees", [{"email": "synthetic@example.invalid"}]),
                ("reminders", {"useDefault": True}),
                ("reminders", {"useDefault": False,
                               "overrides": [{"minutes": 5, "method": "email"}]}),
                ("conferenceData", {"entryPoints": [{"entryPointType": "video"}]}),
                ("hangoutLink", "https://example.invalid/meeting")):
            with self.subTest(key=key):
                self.event = {**event, "status": "confirmed", key: changed}
                self.assertEqual(
                    self.gateway.recover(proof(), operation_id="test-op-1"),
                    {"status": "unknown", "external_actions": 0})

    def test_token_or_provider_failure_remains_unknown_and_no_retry(self):
        self.prepare()
        self.attempt()
        self.oauth.available = False
        self.assertEqual(self.gateway.recover(
            proof(), operation_id="test-op-1")["status"], "unknown")
        self.assertEqual(self.read_calls, [])
        self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")

    def test_prepared_retry_restart_identity_and_changed_intent_rejection(self):
        first = self.prepare()
        reopened = IntentLedger(self.db, require_approval_registry=False)
        self.gateway._ledger = reopened
        self.assertEqual(self.prepare(), first)
        self.assertEqual(reopened.get("test-op-1")["event_id"], first["id"])
        with self.assertRaisesRegex(ValueError, "conflicting event intent"):
            self.prepare(request_id="other-request")
        with self.assertRaisesRegex(ValueError, "conflicting event intent"):
            self.prepare(start="2026-10-20T10:01:00+02:00")
        self.assertNotEqual(self.prepare(op_id="test-op-2")["id"], first["id"])
        self.attempt()
        self.assertEqual(reopened.get("test-op-1")["status"], "unknown")
        with self.assertRaisesRegex(ValueError, "already attempted"):
            self.prepare()
        self.assertEqual(reopened.get("test-op-1")["event_id"], first["id"])
        self.assertEqual(self.oauth.calls, 0)
        self.assertEqual(self.read_calls, [])

    def test_secret_change_cannot_replan_same_operation(self):
        first = self.prepare()
        self.gateway._intent_key = b"changed-offline-hmac-secret-is-32-bytes"
        with self.assertRaisesRegex(ValueError, "conflicting event intent"):
            self.prepare()
        self.assertEqual(self.ledger.get("test-op-1")["event_id"], first["id"])


    def test_approval_cannot_mark_replaced_intent_during_callback(self):
        """Trusted approval of A must never advance substituted intent B."""
        from v2_poc.calendar_rest_intent import plan_insert

        original = self.prepare()
        replacement = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR, request_id="different-request",
            operation_id="test-op-1", start=START, end=END, timezone_name=ZONE)
        self.assertNotEqual(original["id"], replacement["body"]["id"])

        def replace_during_approval(approved_row):
            self.assertEqual(approved_row["event_id"], original["id"])
            with self.ledger._db() as db:
                db.execute("""UPDATE calendar_intents SET event_id=?, plan_json=?
                    WHERE operation_id=?""",
                    (replacement["body"]["id"],
                     json.dumps(replacement, sort_keys=True, separators=(",", ":")),
                     "test-op-1"))
            return True

        self.gateway._approve_intent = replace_during_approval
        with self.assertRaisesRegex(ValueError, "operation changed"):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1",
                approval_evidence=self.consent_proof())
        current = self.ledger.get("test-op-1")
        self.assertEqual(current["event_id"], replacement["body"]["id"])
        self.assertEqual(current["status"], "prepared")
        self.assertEqual(self.read_calls, [])
        self.assertEqual(self.oauth.calls, 0)

    def test_approval_callback_cannot_rewrite_its_approved_snapshot(self):
        """A mutable approval callback cannot retarget an approval to B."""
        from v2_poc.calendar_rest_intent import plan_insert

        self.prepare()
        replacement = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR, request_id="different-request",
            operation_id="test-op-1", start=START, end=END, timezone_name=ZONE)

        def mutate_snapshot_and_store(approved):
            approved["event_id"] = replacement["body"]["id"]
            approved["plan"] = replacement
            with self.ledger._db() as db:
                db.execute("""UPDATE calendar_intents SET event_id=?, plan_json=?
                    WHERE operation_id=?""",
                    (replacement["body"]["id"],
                     json.dumps(replacement, sort_keys=True, separators=(",", ":")),
                     "test-op-1"))
            return True

        self.gateway._approve_intent = mutate_snapshot_and_store
        with self.assertRaisesRegex(ValueError, "operation changed"):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1",
                approval_evidence=self.consent_proof())
        self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")
        self.assertEqual(self.read_calls, [])
        self.assertEqual(self.oauth.calls, 0)

    def test_readback_cannot_verify_intent_replaced_during_provider_read(self):
        """An exact event read of obsolete A cannot verify swapped intent B."""
        from v2_poc.calendar_rest_intent import plan_insert

        original = self.prepare()
        self.attempt()
        replacement = plan_insert(
            secret=INTENT_KEY, calendar_id=CALENDAR, request_id="different-request",
            operation_id="test-op-1", start=START, end=END, timezone_name=ZONE)

        def replace_during_read(**kwargs):
            self.assertEqual(kwargs["event_id"], original["id"])
            with self.ledger._db() as db:
                db.execute("""UPDATE calendar_intents SET event_id=?, plan_json=?
                    WHERE operation_id=?""",
                    (replacement["body"]["id"],
                     json.dumps(replacement, sort_keys=True, separators=(",", ":")),
                     "test-op-1"))
            return {**original, "status": "confirmed"}

        self.gateway._read_event = replace_during_read
        result = self.gateway.recover(proof(), operation_id="test-op-1")
        self.assertEqual(result, {"status": "unknown", "external_actions": 0})
        self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")
        self.assertEqual(self.ledger.get("test-op-1")["event_id"],
                         replacement["body"]["id"])
        self.assertEqual(self.oauth.calls, 1)

    def test_readback_cannot_verify_intent_deleted_during_provider_read(self):
        original = self.prepare()
        self.attempt()

        def delete_during_read(**kwargs):
            with self.ledger._db() as db:
                db.execute("DELETE FROM calendar_intents WHERE operation_id=?",
                           ("test-op-1",))
            return {**original, "status": "confirmed"}

        self.gateway._read_event = delete_during_read
        self.assertEqual(self.gateway.recover(proof(), operation_id="test-op-1"),
                         {"status": "unknown", "external_actions": 0})
        self.assertIsNone(self.ledger.get("test-op-1"))
        self.assertEqual(self.oauth.calls, 1)


if __name__ == "__main__":
    unittest.main()
