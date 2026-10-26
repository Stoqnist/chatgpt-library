"""Offline Calendar Gateway: operation-bound approval ledger and exact readback.

The sole event identity, safe payload and comparator are from calendar_rest_intent.
No provider event write, running listener, live principal issuer or deployment.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import hmac
import json
import sqlite3
import time

from .calendar_rest_intent import READ_FIELDS, plan_insert, verify_exact_readback
from .calendar_approval import plan_digest

DENIED = "calendar recovery not authorized"


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class VerifiedAgent:
    """Verify an operation-bound assertion from a separately trusted issuer.

    Issuer authentication and token replay prevention are NOT implemented here.
    """

    def __init__(self, *, signing_key: bytes, audience="agency-calendar-gateway",
                 clock=time.time):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("signing key must be at least 32 bytes")
        self._key, self._audience, self._clock = signing_key, audience, clock

    def verify(self, proof, *, calendar_id, allowed_roles, operation_id):
        try:
            if not isinstance(proof, str) or len(proof) > 2048:
                raise ValueError()
            body, signature = proof.split(".")
            expected = hmac.new(self._key, body.encode(), hashlib.sha256).digest()
            if not hmac.compare_digest(_unb64(signature), expected):
                raise ValueError()
            claims = json.loads(_unb64(body))
            if not isinstance(claims, dict):
                raise ValueError()
            now = self._clock()
            if (claims.get("aud") != self._audience
                    or claims.get("calendar") != calendar_id
                    or claims.get("operation_id") != operation_id
                    or claims.get("role") not in allowed_roles
                    or type(claims.get("exp")) not in (int, float)
                    or not now < claims["exp"] <= now + 300):
                raise ValueError()
            return claims["role"]
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
            raise PermissionError(DENIED) from None


class IntentLedger:
    """Synthetic SQLite pre-insert attempt ledger; no live provider transaction.

    The planner owns IDs and readback semantics. The ledger stores its complete
    plan rather than creating any competing event identity or marker. Prior
    prototype DB schemas are intentionally not migrated or accepted for use.
    """

    def __init__(self, path, *, require_approval_registry=True, clock=time.time):
        self.path = str(path)
        self._require_registry = require_approval_registry
        self._clock = clock
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_intents (
                operation_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                calendar_id TEXT NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                plan_json TEXT NOT NULL,
                approval_id TEXT UNIQUE,
                status TEXT NOT NULL CHECK (status IN ('prepared','unknown','verified'))
            )""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def prepare(self, operation_id, plan):
        serialized = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        with self._db() as db:
            db.execute("""INSERT INTO calendar_intents
                (operation_id,owner,calendar_id,event_id,plan_json,status)
                VALUES (?, 'calendar', ?, ?, ?, 'prepared')
                ON CONFLICT(operation_id) DO NOTHING""",
                (operation_id, plan["calendar_id"], plan["body"]["id"], serialized))
            row = db.execute("""SELECT owner,calendar_id,event_id,plan_json,status
                FROM calendar_intents WHERE operation_id=?""", (operation_id,)).fetchone()
            if (row is None or row[0] != "calendar"
                    or row[1] != plan["calendar_id"]
                    or row[2] != plan["body"]["id"]
                    or row[3] != serialized):
                raise ValueError("conflicting event intent for operation")
            if row[4] != "prepared":
                raise ValueError("operation already attempted; inspect before retry")
        return self.get(operation_id)

    def get(self, operation_id):
        with self._db() as db:
            row = db.execute("""SELECT operation_id,owner,calendar_id,event_id,
                                       plan_json,status FROM calendar_intents
                                       WHERE operation_id=?""", (operation_id,)).fetchone()
        if row is None:
            return None
        return {"operation_id": row[0], "owner": row[1],
                "calendar_id": row[2], "event_id": row[3],
                "plan": json.loads(row[4]), "status": row[5]}

    @staticmethod
    def _row_identity(row):
        """Match the entire approved/read intent, not just its operation ID."""
        return (
            row["operation_id"], row["owner"], row["calendar_id"],
            row["event_id"],
            json.dumps(row["plan"], sort_keys=True, separators=(",", ":")),
        )

    def mark_attempt(self, expected_row, *, approval_id, signing_key_id):
        """Atomically bind one approval receipt to the exact attempted plan."""
        if (not isinstance(approval_id, str) or not approval_id
                or not isinstance(signing_key_id, str) or not signing_key_id):
            raise ValueError("approval evidence missing")
        # The receipt check and attempt CAS occur in one SQLite transaction.
        # A revocation racing after proof verification but before this lock
        # must prevent marking the operation as attempted.
        with self._db() as db:
            # sqlite3's context manager does not begin a transaction for
            # SELECT. Reserve the write lock BEFORE checking key/receipt
            # status so a quarantine cannot slip between check and CAS.
            db.execute("BEGIN IMMEDIATE")
            if self._require_registry:
                details = db.execute("""SELECT r.state,r.expires_at,
                    r.calendar_id,r.operation_id,r.event_id,r.plan_sha256,
                    r.key_id,k.state,r.subject,r.session_id
                    FROM consent_receipts AS r
                    JOIN consent_signing_keys AS k ON k.key_id=r.key_id
                    WHERE r.approval_id=?""", (approval_id,)).fetchone()
                if (details is None or details[0] != "issued"
                        or not self._clock() < details[1]
                        or details[2:7] != (
                            expected_row["calendar_id"], expected_row["operation_id"],
                            expected_row["event_id"], plan_digest(expected_row["plan"]),
                            signing_key_id)
                        or details[7] not in ("active", "retired")):
                    raise PermissionError("calendar approval unavailable")
                # A separately verified logout/permission-loss event may
                # arrive after an approval proof was issued. Tombstones are
                # checked under the SAME BEGIN IMMEDIATE lock as attempt CAS.
                revoked = db.execute("""SELECT 1 FROM consent_authority_revocations
                    WHERE subject=? AND (scope='principal' OR
                        (scope='session' AND target=?) OR
                        (scope='calendar' AND target=?)) LIMIT 1""",
                    (details[8], details[9], expected_row["calendar_id"]))
                if revoked.fetchone() is not None:
                    raise PermissionError("calendar approval unavailable")
            result = db.execute("""UPDATE calendar_intents
                SET status='unknown', approval_id=?
                WHERE operation_id=? AND owner=? AND calendar_id=?
                  AND event_id=? AND plan_json=? AND status='prepared'
                  AND approval_id IS NULL""",
                (approval_id, *self._row_identity(expected_row)))
            if result.rowcount != 1:
                raise ValueError("operation changed, attempted or missing")
            if self._require_registry:
                consumed = db.execute("""UPDATE consent_receipts
                    SET state='consumed' WHERE approval_id=? AND key_id=?
                    AND state='issued' AND expires_at>?""",
                    (approval_id, signing_key_id, self._clock()))
                if consumed.rowcount != 1:
                    raise PermissionError("calendar approval unavailable")

    def verified(self, expected_row):
        """Only confirm the exact row inspected before fresh event readback."""
        with self._db() as db:
            result = db.execute("""UPDATE calendar_intents SET status='verified'
                WHERE operation_id=? AND owner=? AND calendar_id=?
                  AND event_id=? AND plan_json=?
                  AND status IN ('unknown', 'verified')""",
                self._row_identity(expected_row))
            if result.rowcount != 1:
                raise ValueError("operation changed during readback")


class CalendarGateway:
    """Bounded offline preflight/recovery; no provider insert or other writes."""

    def __init__(self, *, calendar_id, intent_key, verifier, ledger, oauth, read_event,
                 approval_verifier, approve_intent=None):
        if not isinstance(calendar_id, str) or not calendar_id:
            raise ValueError("calendar ID must be configured privately")
        if not isinstance(intent_key, bytes) or len(intent_key) < 32:
            raise ValueError("durable intent key must be at least 32 bytes")
        self._calendar_id = calendar_id
        self._intent_key = intent_key
        self._verify = verifier.verify
        self._ledger = ledger
        self._oauth = oauth
        self._read_event = read_event
        if approval_verifier is None or not callable(getattr(approval_verifier, "verify", None)):
            raise ValueError("independent approval verifier required")
        self._approval_verifier = approval_verifier
        self._approve_intent = approve_intent

    def prepare(self, proof, *, operation_id, request_id, start_at, end_at,
                timezone_name):
        self._verify(proof, calendar_id=self._calendar_id,
                     allowed_roles={"calendar_executor"}, operation_id=operation_id)
        plan = plan_insert(
            secret=self._intent_key, calendar_id=self._calendar_id,
            request_id=request_id, operation_id=operation_id,
            start=start_at, end=end_at, timezone_name=timezone_name)
        row = self._ledger.prepare(operation_id, plan)
        return row["plan"]["body"]

    def record_attempt(self, proof, *, operation_id, approval_evidence):
        """Verify exact, independent approval before a synthetic attempt."""
        self._verify(proof, calendar_id=self._calendar_id,
                     allowed_roles={"calendar_executor"}, operation_id=operation_id)
        row = self._ledger.get(operation_id)
        if (row is None or row["calendar_id"] != self._calendar_id
                or row["owner"] != "calendar"):
            raise PermissionError(DENIED)
        # Optional external policy can veto; it can never replace a signed proof.
        if self._approve_intent is not None and self._approve_intent(deepcopy(row)) is not True:
            raise PermissionError("write approval unavailable")
        # Verify expiry and exact intent immediately before the conditional write.
        # The signer must authenticate real user consent outside this POC.
        approval_id, signing_key_id = self._approval_verifier.verify(
            approval_evidence, expected_row=deepcopy(row))
        self._ledger.mark_attempt(
            row, approval_id=approval_id, signing_key_id=signing_key_id)
        return {"status": "unknown", "external_actions": 0}

    def recover(self, proof, *, operation_id):
        """Read exact event afresh; unknown never permits an automatic retry."""
        self._verify(proof, calendar_id=self._calendar_id,
                     allowed_roles={"calendar_recovery"}, operation_id=operation_id)
        row = self._ledger.get(operation_id)
        if (row is None or row["calendar_id"] != self._calendar_id
                or row["owner"] != "calendar" or row["status"] == "prepared"):
            raise PermissionError(DENIED)
        try:
            token = self._oauth.access_token()
            event = self._read_event(
                calendar_id=self._calendar_id, event_id=row["event_id"],
                fields=READ_FIELDS, access_token=token)
            outcome = verify_exact_readback(
                row["plan"], read_calendar_id=self._calendar_id, event=event)
        except Exception:
            return {"status": "unknown", "external_actions": 0}
        if outcome["status"] != "verified":
            return {"status": "unknown", "external_actions": 0}
        try:
            self._ledger.verified(row)
        except (ValueError, sqlite3.Error):
            # Readback may be valid for an old identity but the stored intent
            # may have changed or disappeared before the status transition.
            return {"status": "unknown", "external_actions": 0}
        return {"status": "verified", "external_actions": 0}
