"""Calendar Gateway offline core: verified caller, durable intent, exact readback.

No server/listener, provider POST, credential storage, or live Google connector.
Separate deployment must authenticate the trusted issuer, bind the private
calendar, verify user approval, and supply the official HTTPS API transport.
"""
from __future__ import annotations

import base64
import binascii
from contextlib import contextmanager
from datetime import datetime
import hashlib
import hmac
import json
import secrets
import sqlite3
import time


READ_FIELDS = "id,status,start(dateTime),end(dateTime),extendedProperties(private)"
DENIED = "calendar recovery not authorized"


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


class VerifiedAgent:
    """Verify a short-lived signed assertion from a separate trusted issuer.

    Agents cannot sign their own permissions; the issuer key must only be
    available to the trusted auth service and this gateway, never an agent.
    """

    def __init__(self, *, signing_key: bytes, audience="agency-calendar-gateway",
                 clock=time.time):
        if not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("signing key must be at least 32 bytes")
        self._key, self._audience, self._clock = signing_key, audience, clock

    def verify(self, proof, *, calendar_id, allowed_roles):
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
                    or claims.get("role") not in allowed_roles
                    or type(claims.get("exp")) not in (int, float)
                    or not now < claims["exp"] <= now + 300):
                raise ValueError()
            return claims["role"]
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error):
            raise PermissionError(DENIED) from None


def _utc_time(value):
    if not isinstance(value, str):
        raise ValueError("invalid event time")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError()
        return dt
    except (ValueError, OverflowError):
        raise ValueError("invalid event time") from None


def _same_instant(observed, expected):
    try:
        return _utc_time(observed) == _utc_time(expected)
    except ValueError:
        return False


class IntentLedger:
    """Small durable SQLite intent/attempt store, only for a designated test DB.

    No claim of an atomic transaction spanning SQLite and Google's API.
    File location, file mode, backups and encryption are deployment concerns.
    """

    def __init__(self, path):
        self.path = str(path)
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_intents (
                operation_id TEXT PRIMARY KEY,
                owner TEXT NOT NULL,
                calendar_id TEXT NOT NULL,
                event_id TEXT NOT NULL UNIQUE,
                marker TEXT NOT NULL,
                start_at TEXT NOT NULL,
                end_at TEXT NOT NULL,
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

    def prepare(self, operation_id, calendar_id, start_at, end_at):
        if (not isinstance(operation_id, str) or not operation_id
                or len(operation_id) > 96 or any(c not in
                "abcdefghijklmnopqrstuvwxyz0123456789-_" for c in operation_id)):
            raise ValueError("invalid operation id")
        _utc_time(start_at)
        _utc_time(end_at)
        if _utc_time(end_at) <= _utc_time(start_at):
            raise ValueError("event end must follow start")
        event_id = "ag" + secrets.token_hex(16)  # Google base32hex-compatible
        marker = secrets.token_hex(16)  # opaque, nonsecret; not a record or token
        with self._db() as db:
            db.execute("""INSERT INTO calendar_intents
                VALUES (?, 'calendar', ?, ?, ?, ?, ?, 'prepared')""",
                (operation_id, calendar_id, event_id, marker, start_at, end_at))
        return self.get(operation_id)

    def get(self, operation_id):
        with self._db() as db:
            row = db.execute("""SELECT operation_id,owner,calendar_id,event_id,
                                marker,start_at,end_at,status
                                FROM calendar_intents WHERE operation_id=?""",
                             (operation_id,)).fetchone()
        return dict(zip(("operation_id", "owner", "calendar_id", "event_id",
                         "marker", "start_at", "end_at", "status"), row)) if row else None

    def mark_attempt(self, operation_id):
        # Must be committed BEFORE calling a provider, never after.
        with self._db() as db:
            result = db.execute("""UPDATE calendar_intents SET status='unknown'
                WHERE operation_id=? AND status='prepared'""", (operation_id,))
            if result.rowcount != 1:
                raise ValueError("operation already attempted or missing")

    def verified(self, operation_id):
        with self._db() as db:
            db.execute("""UPDATE calendar_intents SET status='verified'
                WHERE operation_id=? AND status='unknown'""", (operation_id,))


class CalendarGateway:
    """Bounded preflight / recovery operations; never sends provider writes."""

    def __init__(self, *, calendar_id, verifier, ledger, oauth, read_event,
                 approve_intent=None):
        if not isinstance(calendar_id, str) or not calendar_id:
            raise ValueError("calendar ID must be configured privately")
        self._calendar_id = calendar_id
        self._verify = verifier.verify
        self._ledger = ledger
        self._oauth = oauth
        self._read_event = read_event
        self._approve_intent = approve_intent

    def prepare(self, proof, *, operation_id, start_at, end_at):
        self._verify(proof, calendar_id=self._calendar_id,
                     allowed_roles={"calendar_executor"})
        row = self._ledger.prepare(operation_id, self._calendar_id,
                                   start_at, end_at)
        return self._preview(row)

    @staticmethod
    def _preview(row):
        return {
            "id": row["event_id"], "summary": "Personal follow-up",
            "start": {"dateTime": row["start_at"]},
            "end": {"dateTime": row["end_at"]},
            "attendees": [], "visibility": "private",
            "reminders": {"useDefault": False, "overrides": []},
            "extendedProperties": {"private": {"agencyOp": row["marker"]}},
        }

    def record_attempt(self, proof, *, operation_id):
        """Record a pre-call attempt only after independently verified approval.

        This method performs NO provider write. Real insertion remains disabled.
        """
        self._verify(proof, calendar_id=self._calendar_id,
                     allowed_roles={"calendar_executor"})
        row = self._ledger.get(operation_id)
        if row is None or row["calendar_id"] != self._calendar_id:
            raise PermissionError(DENIED)
        if (self._approve_intent is None
                or self._approve_intent(row) is not True):
            raise PermissionError("write approval unavailable")
        self._ledger.mark_attempt(operation_id)
        return {"status": "unknown", "external_actions": 0}

    def recover(self, proof, *, operation_id):
        """Exact-ID, read-only recovery; unknown is never proof of nonapplication."""
        self._verify(proof, calendar_id=self._calendar_id,
                     allowed_roles={"calendar_recovery"})
        row = self._ledger.get(operation_id)
        if (row is None or row["calendar_id"] != self._calendar_id
                or row["owner"] != "calendar" or row["status"] == "prepared"):
            raise PermissionError(DENIED)
        if row["status"] == "verified":
            return {"status": "verified", "external_actions": 0}
        try:
            token = self._oauth.access_token()
            result = self._read_event(
                calendar_id=self._calendar_id, event_id=row["event_id"],
                fields=READ_FIELDS, access_token=token)
        except Exception:
            return {"status": "unknown", "external_actions": 0}
        expected = self._preview(row)
        props = result.get("extendedProperties") if isinstance(result, dict) else None
        private = props.get("private") if isinstance(props, dict) else None
        if (not isinstance(result, dict)
                or result.get("id") != row["event_id"]
                or result.get("status") != "confirmed"
                or not isinstance(result.get("start"), dict)
                or not isinstance(result.get("end"), dict)
                or not _same_instant(result["start"].get("dateTime"),
                                     row["start_at"])
                or not _same_instant(result["end"].get("dateTime"),
                                     row["end_at"])
                or not isinstance(private, dict)
                or private.get("agencyOp") != row["marker"]):
            return {"status": "unknown", "external_actions": 0}
        self._ledger.verified(operation_id)
        return {"status": "verified", "external_actions": 0}
