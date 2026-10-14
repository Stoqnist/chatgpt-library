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

from v2_poc.calendar_gateway_oauth import OfflineOAuth, ReauthorizationRequired
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
CLOCK = 1_000_000
CALENDAR = "fictional-disposable-calendar"


def proof(role="calendar_recovery", calendar=CALENDAR, exp=CLOCK + 120, key=KEY):
    claims = {"sub": "trusted-broker", "role": role,
              "aud": "agency-calendar-gateway",
              "calendar": calendar, "exp": exp}
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
        self.ledger = IntentLedger(self.db)
        self.oauth = TokenForTests()
        self.read_calls = []
        self.event = None
        self.approved = False

        def read_event(**kwargs):
            self.read_calls.append(kwargs)
            return self.event

        self.gateway = CalendarGateway(
            calendar_id=CALENDAR,
            verifier=VerifiedAgent(signing_key=KEY, clock=lambda: CLOCK),
            ledger=self.ledger, oauth=self.oauth, read_event=read_event,
            approve_intent=lambda row: self.approved)

    def prepare(self, op_id="test-op-1"):
        return self.gateway.prepare(
            proof("calendar_executor"), operation_id=op_id,
            start_at="2026-10-20T10:00:00+02:00",
            end_at="2026-10-20T10:30:00+02:00")

    def test_plan_event_has_stable_valid_google_id_and_no_notifications(self):
        event = self.prepare()
        self.assertRegex(event["id"], r"^ag[0-9a-f]{32}$")
        self.assertEqual(event["summary"], "Personal follow-up")
        self.assertEqual(event["attendees"], [])
        self.assertEqual(event["reminders"], {"useDefault": False,
                                               "overrides": []})
        self.assertNotIn("conferenceData", event)
        self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")
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
                    self.gateway.recover(proof(), operation_id=opid)
        self.assertEqual(self.oauth.calls, 0)

    def test_approval_is_not_inferred_from_plan_or_role(self):
        self.prepare()
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1")
        with self.assertRaises(PermissionError):
            self.gateway.record_attempt(proof("health"), operation_id="test-op-1")
        self.assertEqual(self.ledger.get("test-op-1")["status"], "prepared")
        self.approved = True
        self.gateway.record_attempt(
            proof("calendar_executor"), operation_id="test-op-1")
        with self.assertRaises(ValueError):
            self.gateway.record_attempt(
                proof("calendar_executor"), operation_id="test-op-1")
        self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")

    def test_exact_id_and_marker_are_required_for_recovery(self):
        event = self.prepare()
        self.approved = True
        self.gateway.record_attempt(
            proof("calendar_executor"), operation_id="test-op-1")
        for candidate in (None, {**event, "status": "cancelled"},
                          {**event, "id": "different"},
                          {**event, "extendedProperties": {"private":
                              {"agencyOp": "wrong"}}},
                          {**event, "start":
                              {"dateTime": "2026-10-20T10:15:00+02:00"}}):
            self.event = candidate
            self.assertEqual(
                self.gateway.recover(proof(), operation_id="test-op-1"),
                {"status": "unknown", "external_actions": 0})
            self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")
        self.event = {**event, "status": "confirmed"}
        # Provider may normalize the original +02:00 times to UTC.
        self.event = {**event, "status": "confirmed",
                      "start": {"dateTime": "2026-10-20T08:00:00Z"},
                      "end": {"dateTime": "2026-10-20T08:30:00Z"}}
        self.assertEqual(self.gateway.recover(
            proof(), operation_id="test-op-1")["status"], "verified")
        self.assertEqual(self.read_calls[-1]["fields"], READ_FIELDS)
        self.assertEqual(self.read_calls[-1]["event_id"], event["id"])
        self.assertEqual(self.read_calls[-1]["calendar_id"], CALENDAR)
        self.assertEqual(self.ledger.get("test-op-1")["status"], "verified")
        self.assertEqual(self.gateway.recover(
            proof(), operation_id="test-op-1")["status"], "verified")

    def test_token_or_provider_failure_remains_unknown_and_no_retry(self):
        self.prepare()
        self.approved = True
        self.gateway.record_attempt(
            proof("calendar_executor"), operation_id="test-op-1")
        self.oauth.available = False
        self.assertEqual(self.gateway.recover(
            proof(), operation_id="test-op-1")["status"], "unknown")
        self.assertEqual(self.read_calls, [])
        self.assertEqual(self.ledger.get("test-op-1")["status"], "unknown")

    def test_restart_does_not_erase_attempt_identity(self):
        event = self.prepare()
        self.approved = True
        self.gateway.record_attempt(
            proof("calendar_executor"), operation_id="test-op-1")
        reopened = IntentLedger(self.db)
        self.assertEqual(reopened.get("test-op-1")["event_id"], event["id"])
        self.assertEqual(reopened.get("test-op-1")["status"], "unknown")
        with self.assertRaises(sqlite3.IntegrityError):
            reopened.prepare("test-op-1", CALENDAR,
                             "2026-10-20T10:00:00+02:00",
                             "2026-10-20T10:30:00+02:00")


if __name__ == "__main__":
    unittest.main()
