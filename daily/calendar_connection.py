"""Owner-bound Calendar OAuth consent lifecycle for private Daily.

This module does not read Calendar events or inject model context. It is
inactive until the operator separately installs a mode-0600 Google Web
client JSON under the application's private /data directory. The app routes
and session boundary must be reviewed before this class is enabled.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import stat
import urllib.parse

from calendar_oauth import (
    CALLBACK_URL, CalendarOAuthError, begin_calendar_auth,
    exchange_calendar_code, parse_calendar_callback,
)

PENDING_SECONDS = 600
CORRELATION_COOKIE = "stoq_calendar_correlation"


class CalendarConnectionError(Exception):
    """Fixed provider-safe error, never expose private OAuth values."""


def _hash(value):
    return hashlib.sha256(value.encode("ascii")).hexdigest()


def _read_client(path):
    try:
        if not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError()
        config = json.loads(path.read_text(encoding="utf-8"))
        client = config["web"]
        identifier = client["client_id"]
        secret = client["client_secret"]
        if not isinstance(identifier, str) or not isinstance(secret, str):
            raise ValueError()
        if not isinstance(client["redirect_uris"], list) or CALLBACK_URL not in client["redirect_uris"]:
            raise ValueError()
        # begin_calendar_auth validates the client identifier before any use.
        begin_calendar_auth(identifier)
        if not 8 <= len(secret) <= 4096 or any(ord(x) < 33 for x in secret):
            raise ValueError()
        return identifier, secret
    except (OSError, ValueError, KeyError, TypeError):
        raise CalendarConnectionError("Calendar connection is not configured.") from None


class CalendarOwnerConsent:
    def __init__(self, data, db, clock):
        self.data = Path(data)
        self.db = db  # contextmanager from App; shares its private SQLite store
        self.clock = clock
        self.client = self.data / "calendar-client.json"
        self.grant = self.data / "calendar-grant.json"

    def init_table(self):
        with self.db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS calendar_pending(
                state_hash TEXT PRIMARY KEY,
                verifier TEXT NOT NULL,
                correlation_hash TEXT NOT NULL,
                owner_session TEXT NOT NULL,
                expires REAL NOT NULL
            )""")

    def status(self):
        try:
            _read_client(self.client)
            configured = True
        except CalendarConnectionError:
            configured = False
        return {"configured": configured, "connected": configured and self.grant.is_file()}

    def begin(self, session):
        identifier, _ = _read_client(self.client)
        url, state, verifier = begin_calendar_auth(identifier)
        correlation = secrets.token_urlsafe(32)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM calendar_pending WHERE expires<=?", (self.clock(),))
            db.execute("DELETE FROM calendar_pending WHERE owner_session=?",
                       (session["token"],))
            db.execute("""INSERT INTO calendar_pending
                (state_hash, verifier, correlation_hash, owner_session, expires)
                VALUES (?, ?, ?, ?, ?)""",
                (_hash(state), verifier, _hash(correlation),
                 session["token"], self.clock()+PENDING_SECONDS))
        return url, correlation

    def complete(self, query, cookie, *, exchange=None):
        if (not isinstance(query, str) or len(query) > 8192 or
                not isinstance(cookie, str) or len(cookie) > 256 or
                any(ord(c) < 33 or ord(c) > 126 for c in cookie)):
            raise CalendarConnectionError("Calendar connection could not be verified.")
        # Parse only the state needed to find the pending, owner-bound flow.
        try:
            params = urllib.parse.parse_qs(query, keep_blank_values=True,
                                          strict_parsing=True, max_num_fields=12)
            state = params["state"][0]
            if len(params["state"]) != 1 or not 32 <= len(state) <= 256 or not state.isascii():
                raise ValueError()
        except (ValueError, KeyError, IndexError):
            raise CalendarConnectionError("Calendar connection could not be verified.") from None

        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT p.*,s.token AS live_session
                FROM calendar_pending AS p
                LEFT JOIN sessions AS s ON p.owner_session=s.token AND s.expires>?
                WHERE p.state_hash=?""",
                (self.clock(), _hash(state))).fetchone()
            if not row or row["expires"] <= self.clock() or not row["live_session"] or not cookie or not secrets.compare_digest(
                    row["correlation_hash"], _hash(cookie)):
                raise CalendarConnectionError("Calendar connection could not be verified.")
            # Consume before any provider network call: callback replay cannot
            # retry code exchange, even if the provider times out.
            db.execute("DELETE FROM calendar_pending WHERE state_hash=?", (_hash(state),))
            verifier = row["verifier"]

        try:
            code = parse_calendar_callback(query, state)
        except CalendarOAuthError:
            raise CalendarConnectionError("Calendar authorization was cancelled or invalid.") from None
        identifier, secret = _read_client(self.client)
        try:
            token = (exchange or exchange_calendar_code)(
                identifier, secret, code, verifier)
        except (CalendarOAuthError, ValueError):
            raise CalendarConnectionError("Calendar authorization could not be completed.") from None

        # Store the minimal long-term secret only; access tokens are short-lived
        # and will be obtained on demand in the subsequent read-only phase.
        if not isinstance(token, dict) or not isinstance(token.get("refresh_token"), str):
            raise CalendarConnectionError("Calendar authorization could not be completed.")
        self._save_refresh(token["refresh_token"])
        return True

    def _save_refresh(self, refresh):
        if not 20 <= len(refresh) <= 8192 or any(ord(c) < 33 for c in refresh):
            raise CalendarConnectionError("Calendar authorization could not be completed.")
        tmp = self.data / ("calendar-grant-" + secrets.token_hex(12))
        try:
            fd = os.open(tmp, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as output:
                json.dump({"refresh_token": refresh}, output)
                output.flush()
                os.fsync(output.fileno())
            os.replace(tmp, self.grant)
            os.chmod(self.grant, 0o600)
        except OSError:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise CalendarConnectionError("Calendar authorization could not be stored.") from None

    def disconnect_local(self):
        # Remove capability from this app immediately. A separate Google
        # account settings action may be required to revoke provider consent.
        with self.db() as db:
            db.execute("DELETE FROM calendar_pending")
        try:
            self.grant.unlink(missing_ok=True)
        except OSError:
            raise CalendarConnectionError("Calendar connection could not be removed.") from None
