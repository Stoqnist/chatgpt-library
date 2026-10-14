"""One-shot browser-bound Google OIDC login state (offline, no token exchange).

A real HTTPS BFF must set the returned binder as an HttpOnly Secure host-only
SameSite=Lax cookie. The callback consumes state under a DB write lock before
the confidential server exchanges the code using the returned PKCE verifier.
No HTTP endpoints, client secrets, credentials or live requests exist here.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import hmac
import secrets
import sqlite3
import time

from .bff_google_oidc import begin_google_login


def _hash(text):
    return hashlib.sha256(text.encode("ascii")).hexdigest()


class OfflineLoginState:
    def __init__(self, path, *, client_id, redirect_uri, clock=time.time):
        self.path = str(path)
        self.client_id = client_id
        self.redirect_uri = redirect_uri
        self.clock = clock
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS bff_oidc_transactions (
                state_hash TEXT PRIMARY KEY,
                browser_hash TEXT NOT NULL,
                nonce TEXT NOT NULL,
                verifier TEXT NOT NULL,
                expires_at REAL NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('pending','consumed'))
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

    def begin(self):
        attempt = begin_google_login(
            client_id=self.client_id, redirect_uri=self.redirect_uri)
        browser_binding = secrets.token_urlsafe(32)
        with self._db() as db:
            db.execute("""INSERT INTO bff_oidc_transactions VALUES
                (?,?,?,?,?,'pending')""",
                (_hash(attempt.state), _hash(browser_binding),
                 attempt.nonce, attempt.code_verifier, self.clock() + 180))
        return {
            "authorization_url": attempt.authorization_url,
            "browser_cookie": ("__Host-agency_oidc_tx=" + browser_binding +
                               "; Path=/; Secure; HttpOnly; SameSite=Lax"),
            # This is not for logging; it belongs in the browser redirect.
            "state": attempt.state,
        }

    def consume(self, *, state, browser_binding):
        """Atomic one-use callback preflight. Must run BEFORE code exchange."""
        if (not isinstance(state, str) or not 30 <= len(state) <= 256
                or not state.isascii()
                or not all(c.isalnum() or c in "-_" for c in state)
                or not isinstance(browser_binding, str)
                or not 30 <= len(browser_binding) <= 256
                or not browser_binding.isascii()
                or not all(c.isalnum() or c in "-_" for c in browser_binding)):
            raise PermissionError("OIDC transaction unavailable")
        with self._db() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("""SELECT browser_hash,nonce,verifier,expires_at,state
                FROM bff_oidc_transactions WHERE state_hash=?""",
                (_hash(state),)).fetchone()
            if (row is None or row[4] != "pending"
                    or self.clock() >= row[3]
                    or not hmac.compare_digest(row[0], _hash(browser_binding))):
                raise PermissionError("OIDC transaction unavailable")
            db.execute("""UPDATE bff_oidc_transactions SET state='consumed'
                WHERE state_hash=? AND state='pending'""", (_hash(state),))
        return {"nonce": row[1], "code_verifier": row[2],
                "redirect_uri": self.redirect_uri, "client_id": self.client_id}
