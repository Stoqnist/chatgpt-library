"""Offline, fictional session-bound consent issuer for Calendar I1.

Two *external* trust roots must sign session and UI-consent assertions. Real
authentication and an actual user-facing confirmation UI are NOT implemented.
No endpoints, OAuth, network, event writes or production credential handling.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import binascii
import hashlib
import hmac
import json
import secrets
import re
import sqlite3
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .calendar_approval import APPROVAL_ACTION, APPROVAL_DENIED, plan_digest

_SESSION_AUDIENCE = "agency-calendar-consent-session"
_UI_AUDIENCE = "agency-calendar-consent-confirmation"
_APPROVAL_AUDIENCE = "agency-calendar-approval"
_APPROVAL_TYPE = "agency-calendar-approval-v1"
_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _encode(payload: dict, key: bytes) -> str:
    body = base64.urlsafe_b64encode(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")
    sig = base64.urlsafe_b64encode(hmac.new(
        key, body.encode("ascii"), hashlib.sha256).digest()).decode().rstrip("=")
    return body + "." + sig


def _verified(token, key, *, issuer, audience, now, ttl):
    try:
        if not isinstance(token, str) or len(token) > 4096:
            raise ValueError()
        b64, sig = token.split(".")
        body = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
        supplied = base64.urlsafe_b64decode(sig + "=" * (-len(sig) % 4))
        expected = hmac.new(key, b64.encode("ascii"), hashlib.sha256).digest()
        if not hmac.compare_digest(supplied, expected):
            raise ValueError()
        data = json.loads(body)
        if (not isinstance(data, dict) or data.get("iss") != issuer
                or data.get("aud") != audience
                or type(data.get("exp")) not in (int, float)
                or not now < data["exp"] <= now + ttl):
            raise ValueError()
        return data
    except (ValueError, TypeError, UnicodeError, binascii.Error, KeyError):
        raise PermissionError(APPROVAL_DENIED) from None


def _identity(claims):
    sub, sid = claims.get("sub"), claims.get("sid")
    if (not isinstance(sub, str) or not 1 <= len(sub) <= 128 or not sub.strip()
            or not isinstance(sid, str) or not 16 <= len(sid) <= 128
            or not all(c.isalnum() or c in "-_" for c in sid)):
        raise PermissionError(APPROVAL_DENIED)
    return sub, sid


class OfflineConsentIssuer:
    """Issues only after a verified fictional session and external UI consent.

    Use the SAME synthetic SQLite path as IntentLedger with
    require_approval_registry=True so receipt revocation and attempt CAS share
    one database transaction. Do not use as a deployed authentication service.
    """

    def __init__(self, path, *, session_key: bytes, ui_key: bytes,
                 approval_private_key: Ed25519PrivateKey, approval_key_id: str,
                 clock=time.time):
        if any(not isinstance(k, bytes) or len(k) < 32
               for k in (session_key, ui_key)):
            raise ValueError("independent session and UI signing keys required")
        if session_key == ui_key:
            raise ValueError("session and UI trust keys must differ")
        if not isinstance(approval_private_key, Ed25519PrivateKey):
            raise ValueError("issuer must hold Ed25519 private signing key")
        if not isinstance(approval_key_id, str) or not _KEY_ID.fullmatch(approval_key_id):
            raise ValueError("explicit bounded approval key ID required")
        self.path, self._session, self._ui = str(path), session_key, ui_key
        self._approval_private = approval_private_key
        self._approval_kid = approval_key_id
        self._clock = clock
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS consent_challenges (
                challenge_id TEXT PRIMARY KEY,
                subject TEXT NOT NULL, session_id TEXT NOT NULL,
                calendar_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                event_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL,
                expires_at REAL NOT NULL,
                state TEXT NOT NULL CHECK (state IN
                    ('pending','issued','declined','revoked'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS consent_receipts (
                approval_id TEXT PRIMARY KEY, challenge_id TEXT NOT NULL UNIQUE,
                subject TEXT NOT NULL, session_id TEXT NOT NULL,
                calendar_id TEXT NOT NULL, operation_id TEXT NOT NULL,
                event_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL,
                expires_at REAL NOT NULL,
                key_id TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN
                    ('issued','consumed','revoked'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS consent_signing_keys (
                key_id TEXT PRIMARY KEY, public_key BLOB NOT NULL,
                state TEXT NOT NULL CHECK (state IN
                    ('active','retired','compromised'))
            )""")
            public_bytes = approval_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw)
            db.execute("""INSERT OR IGNORE INTO consent_signing_keys
                (key_id,public_key,state) VALUES (?,?,'active')""",
                (approval_key_id, public_bytes))
            saved = db.execute("""SELECT public_key FROM consent_signing_keys
                WHERE key_id=?""", (approval_key_id,)).fetchone()
            if saved is None or saved[0] != public_bytes:
                raise ValueError("key ID already registered to a different public key")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def _user(self, session_proof):
        claims = _verified(session_proof, self._session,
                           issuer="agency-session", audience=_SESSION_AUDIENCE,
                           now=self._clock(), ttl=3600)
        return _identity(claims)

    def begin(self, *, session_proof, row: dict):
        """Create a short-lived challenge and the exact display representation."""
        subject, sid = self._user(session_proof)
        try:
            plan = row["plan"]
            event = plan["body"]
            if (row["owner"] != "calendar" or row["calendar_id"] != plan["calendar_id"]
                    or row["event_id"] != event["id"]
                    or row["status"] != "prepared"):
                raise ValueError()
            start, end = event["start"], event["end"]
            summary = event["summary"]
        except (TypeError, KeyError, ValueError):
            raise PermissionError(APPROVAL_DENIED) from None
        now = self._clock()
        ident = secrets.token_urlsafe(24)
        digest = plan_digest(plan)
        with self._db() as db:
            db.execute("""INSERT INTO consent_challenges VALUES
                (?,?,?,?,?,?,?,?, 'pending')""",
                (ident, subject, sid, row["calendar_id"],
                 row["operation_id"], row["event_id"], digest, now + 120))
        return {"challenge_id": ident, "plan_sha256": digest,
                "expires_at": now + 120, "display": {
                    "action": APPROVAL_ACTION, "calendar_id": row["calendar_id"],
                    "operation_id": row["operation_id"], "event_id": row["event_id"],
                    "summary": summary, "start": start, "end": end,
                    "visibility": event["visibility"],
                    "transparency": event["transparency"],
                    "attendees": [], "conference_data": None,
                    "reminders": event["reminders"],
                    "insert_params": plan["insert_params"]}}

    def decide(self, *, session_proof, confirmation_proof):
        """Consume one separately signed explicit UI decision; no self-approval."""
        subject, sid = self._user(session_proof)
        now = self._clock()
        choice = _verified(confirmation_proof, self._ui,
                           issuer="agency-consent-ui", audience=_UI_AUDIENCE,
                           now=now, ttl=120)
        if (choice.get("sub") != subject or choice.get("sid") != sid
                or choice.get("action") != APPROVAL_ACTION
                or choice.get("decision") not in ("approved", "declined")):
            raise PermissionError(APPROVAL_DENIED)
        challenge_id = choice.get("challenge_id")
        if not isinstance(challenge_id, str):
            raise PermissionError(APPROVAL_DENIED)
        with self._db() as db:
            challenge = db.execute("""SELECT subject,session_id,calendar_id,
                operation_id,event_id,plan_sha256,expires_at,state
                FROM consent_challenges WHERE challenge_id=?""",
                (challenge_id,)).fetchone()
            if (challenge is None or challenge[0] != subject or challenge[1] != sid
                    or choice.get("plan_sha256") != challenge[5]
                    or not now < challenge[6] or challenge[7] != "pending"):
                raise PermissionError(APPROVAL_DENIED)
            approved = choice["decision"] == "approved"
            if approved:
                state = db.execute("""SELECT state FROM consent_signing_keys
                    WHERE key_id=?""", (self._approval_kid,)).fetchone()
                if state != ("active",):
                    raise PermissionError(APPROVAL_DENIED)
            db.execute("UPDATE consent_challenges SET state=? WHERE challenge_id=?",
                       ("issued" if approved else "declined", challenge_id))
            if not approved:
                return {"status": "declined"}
            approval_id = secrets.token_urlsafe(24)
            expiry = min(now + 60, challenge[6])
            db.execute("""INSERT INTO consent_receipts VALUES
                (?,?,?,?,?,?,?,?,?,?, 'issued')""",
                (approval_id, challenge_id, subject, sid, challenge[2],
                 challenge[3], challenge[4], challenge[5], expiry,
                 self._approval_kid))
        claims = {
            "iss": "agency-calendar-consent", "aud": _APPROVAL_AUDIENCE,
            "typ": _APPROVAL_TYPE, "alg": "EdDSA", "kid": self._approval_kid,
            "sub": subject, "jti": approval_id, "action": APPROVAL_ACTION,
            "decision": "approved", "calendar_id": challenge[2],
            "operation_id": challenge[3], "event_id": challenge[4],
            "plan_sha256": challenge[5], "exp": expiry,
        }
        encoded = base64.urlsafe_b64encode(json.dumps(
            claims, sort_keys=True, separators=(",", ":")).encode()
        ).decode("ascii").rstrip("=")
        signature = self._approval_private.sign(encoded.encode("ascii"))
        proof = encoded + "." + base64.urlsafe_b64encode(
            signature).decode("ascii").rstrip("=")
        return {"status": "issued", "approval_id": approval_id,
                "approval_proof": proof, "expires_at": expiry}

    def set_key_state(self, key_id: str, *, state: str):
        """Simulated operator action: retire or quarantine a signing key.

        NOT a remotely callable admin API. Production requires separately
        authenticated operator authority and public-key trust distribution.
        """
        if state not in ("retired", "compromised"):
            raise ValueError("only retirement and compromise are supported")
        with self._db() as db:
            row = db.execute("""SELECT state FROM consent_signing_keys
                WHERE key_id=?""", (key_id,)).fetchone()
            if (row is None or row[0] == "compromised"
                    or row[0] == "retired" and state != "compromised"):
                raise PermissionError(APPROVAL_DENIED)
            db.execute("""UPDATE consent_signing_keys SET state=?
                WHERE key_id=?""", (state, key_id))
            if state == "compromised":
                db.execute("""UPDATE consent_receipts SET state='revoked'
                    WHERE key_id=? AND state='issued'""", (key_id,))
        return {"status": state}

    def revoke(self, *, session_proof, approval_id):
        """Revoke a still-unconsumed approval; cannot undo attempted actions."""
        subject, sid = self._user(session_proof)
        with self._db() as db:
            result = db.execute("""UPDATE consent_receipts SET state='revoked'
                WHERE approval_id=? AND subject=? AND session_id=?
                AND state='issued'""", (approval_id, subject, sid))
            if result.rowcount != 1:
                raise PermissionError(APPROVAL_DENIED)
        return {"status": "revoked"}
