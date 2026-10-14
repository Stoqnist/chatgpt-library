"""Offline server-side BFF session and explicit consent contract.

NO HTTP routes are wired. The BFF service remains 503 by default. These
functions accept trusted server inputs only, not client-provided JSON; they
never issue Calendar approval proofs or perform external provider effects.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
from html import escape
import json
import secrets
import sqlite3
import time

from .bff_google_oidc import GOOGLE_ISSUERS, VerifiedGoogleIdentity

DENIED = "session or consent not authorized"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def session_cookie(raw_token: str) -> str:
    """Host-only secure cookie for eventual HTTPS BFF response."""
    if (not isinstance(raw_token, str) or not 32 <= len(raw_token) <= 256
            or not all(c.isalnum() or c in "_-" for c in raw_token)):
        raise ValueError("invalid session token")
    return ("__Host-agency_session=" + raw_token +
            "; Path=/; Secure; HttpOnly; SameSite=Lax")


class OfflineBrowserConsent:
    """Single-DB durable local session and browser consent *recording* only.

    A downstream trusted service would still need to authenticate actual
    browser requests, attest true display and sign the matching consent,
    verify authorization/role, and check remote revocations before execution.
    """

    def __init__(self, path, *, oidc_client_id: str, trusted_origin: str,
                 clock=time.time):
        if (not isinstance(oidc_client_id, str) or not oidc_client_id
                or not isinstance(trusted_origin, str)
                or not trusted_origin.startswith("https://")
                or trusted_origin.endswith("/")
                or "/" in trusted_origin[8:]):
            raise ValueError("exact HTTPS origin and client required")
        self.path = str(path)
        self._client_id = oidc_client_id
        self._origin = trusted_origin
        self._clock = clock
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS bff_sessions (
                session_hash TEXT PRIMARY KEY, subject TEXT NOT NULL,
                sid TEXT NOT NULL, expires_at REAL NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('active','revoked'))
            )""")
            db.execute("""CREATE TABLE IF NOT EXISTS bff_consent_challenges (
                challenge_id TEXT PRIMARY KEY, session_hash TEXT NOT NULL,
                plan_sha256 TEXT NOT NULL, display_json TEXT NOT NULL,
                display_sha256 TEXT NOT NULL, csrf_hash TEXT NOT NULL,
                expires_at REAL NOT NULL,
                state TEXT NOT NULL CHECK(
                    state IN ('pending','approved','declined','revoked')),
                FOREIGN KEY(session_hash) REFERENCES bff_sessions(session_hash)
            )""")

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("PRAGMA foreign_keys=ON")
            with db:
                yield db
        finally:
            db.close()

    def _active(self, db, token: str):
        if not isinstance(token, str) or not 32 <= len(token) <= 256:
            raise PermissionError(DENIED)
        row = db.execute("""SELECT subject,sid,expires_at,state
            FROM bff_sessions WHERE session_hash=?""",
                         (_digest(token),)).fetchone()
        if row is None or row[3] != "active" or not self._clock() < row[2]:
            raise PermissionError(DENIED)
        return row

    def create_session(self, *, verified_identity: VerifiedGoogleIdentity):
        """Internal-only bridge after a real vetted Google token exchange.

        No network adapter/callback exists yet; callers MUST NOT construct a
        VerifiedGoogleIdentity from decoded user claims. Tests use fakes.
        """
        if (not isinstance(verified_identity, VerifiedGoogleIdentity)
                or verified_identity.issuer not in GOOGLE_ISSUERS
                or verified_identity.audience != self._client_id
                or not verified_identity.subject
                or type(verified_identity.expires_at) is not int
                or verified_identity.expires_at <= self._clock()):
            raise PermissionError(DENIED)
        token = secrets.token_urlsafe(48)
        sid = secrets.token_urlsafe(24)
        expires = min(self._clock() + 900, verified_identity.expires_at)
        with self._db() as db:
            db.execute("""INSERT INTO bff_sessions VALUES (?,?,?,?, 'active')""",
                       (_digest(token), verified_identity.subject, sid, expires))
        return {"session_token": token, "expires_at": expires, "sid": sid}

    def logout(self, *, session_token: str):
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._active(db, session_token)
            ident = _digest(session_token)
            db.execute("""UPDATE bff_sessions SET state='revoked'
                WHERE session_hash=?""", (ident,))
            db.execute("""UPDATE bff_consent_challenges SET state='revoked'
                WHERE session_hash=? AND state='pending'""", (ident,))
        # This is local browser session revocation only, NOT the existing
        # Calendar approval issuer's external authority tombstone.
        return {"status": "local_session_revoked", "external_actions": 0}

    def begin_consent(self, *, session_token: str, preview: dict,
                      plan_sha256: str):
        """Create a browser challenge for server-computed trusted preview."""
        if (not isinstance(preview, dict) or not preview
                or not isinstance(plan_sha256, str)
                or len(plan_sha256) != 64
                or any(c not in "0123456789abcdef" for c in plan_sha256)):
            raise PermissionError(DENIED)
        display_json = json.dumps(preview, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True)
        if len(display_json) > 8192:
            raise PermissionError(DENIED)
        display_digest = _digest(display_json)
        ident = secrets.token_urlsafe(24)
        csrf = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            session = self._active(db, session_token)
            deadline = min(self._clock() + 120, session[2])
            db.execute("""INSERT INTO bff_consent_challenges VALUES
                (?,?,?,?,?,?,?,'pending')""",
                (ident, _digest(session_token), plan_sha256, display_json,
                 display_digest, _digest(csrf), deadline))
        return {"challenge_id": ident, "csrf_token": csrf,
                "display_sha256": display_digest, "expires_at": deadline,
                "html": self.render_consent(preview, ident, csrf)}

    @staticmethod
    def render_consent(preview: dict, challenge_id: str, csrf_token: str) -> str:
        """Escaped static form. No JavaScript and no implicit approval."""
        def field(label: str, key: str):
            val = preview.get(key, "Not specified")
            if isinstance(val, (dict, list)):
                val = json.dumps(val, ensure_ascii=True, sort_keys=True)
            return ("<dt>" + escape(label) + "</dt><dd>" +
                    escape(str(val), quote=True) + "</dd>")
        body = "".join(field(label, key) for label, key in (
            ("Action", "action"), ("Calendar", "calendar_id"),
            ("Event ID", "event_id"), ("Summary", "summary"),
            ("Start", "start"), ("End", "end"),
            ("Visibility", "visibility"), ("Transparency", "transparency"),
            ("Attendees", "attendees"), ("Conference", "conference_data"),
            ("Reminders", "reminders"), ("Insert options", "insert_params")))
        return ('<!doctype html><html><head><meta charset="utf-8">'
                '<title>Review Calendar action</title></head><body>'
                '<main><h1>Review Calendar action</h1><dl>' + body + '</dl>'
                '<form method="post" action="/consent/decision">'
                '<input type="hidden" name="challenge_id" value="' +
                escape(challenge_id, quote=True) + '">'
                '<input type="hidden" name="csrf_token" value="' +
                escape(csrf_token, quote=True) + '">'
                '<button name="decision" value="approved" type="submit">'
                'Approve</button><button name="decision" value="declined" '
                'type="submit">Decline</button></form></main></body></html>')

    def decide(self, *, session_token: str, origin: str, challenge_id: str,
               csrf_token: str, decision: str, displayed_sha256: str):
        if (origin != self._origin or decision not in ("approved", "declined")
                or not all(isinstance(x, str) for x in (
                    challenge_id, csrf_token, displayed_sha256))):
            raise PermissionError(DENIED)
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._active(db, session_token)
            row = db.execute("""SELECT session_hash,plan_sha256,display_sha256,
                csrf_hash,expires_at,state FROM bff_consent_challenges
                WHERE challenge_id=?""", (challenge_id,)).fetchone()
            if (row is None or row[0] != _digest(session_token)
                    or row[5] != "pending" or self._clock() >= row[4]
                    or not hmac.compare_digest(row[3], _digest(csrf_token))
                    or not hmac.compare_digest(row[2], displayed_sha256)):
                raise PermissionError(DENIED)
            db.execute("""UPDATE bff_consent_challenges SET state=?
                WHERE challenge_id=? AND state='pending'""",
                       (decision, challenge_id))
        return {"status": "recorded_unissued", "decision": decision,
                "plan_sha256": row[1], "display_sha256": row[2],
                "external_actions": 0, "live_write_authorized": False}
