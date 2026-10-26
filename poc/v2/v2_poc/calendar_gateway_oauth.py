"""Offline-testable Google OAuth web flow / refresh core.

NO HTTP listener, credentials, live calls, or secret storage is supplied here.
A deployment must inject Google's HTTPS token client and a secure private vault.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlencode


AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"


class ReauthorizationRequired(RuntimeError):
    pass


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


class OfflineOAuth:
    """Exchanges codes and refreshes access tokens without routine user prompts.

    exchange(form) is an injected HTTPS POST to Google's TOKEN_ENDPOINT.
    vault.load()/save(dict) must use separately secured, persistent storage.
    Never expose this object's state or vault to an LLM/agent.
    """

    def __init__(self, *, client_id, client_secret, redirect_uri, scopes,
                 exchange, vault, clock=time.time):
        if (not client_id or not client_secret
                or not redirect_uri.startswith("https://")
                or not scopes or len(set(scopes)) != len(scopes)):
            raise ValueError("invalid OAuth configuration")
        self.client_id = client_id
        self._client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.scopes = frozenset(scopes)
        self._exchange = exchange
        self._vault = vault
        self._clock = clock
        self._pending = None
        self._access = None
        self._expires = 0

    def authorization_url(self):
        """Begin one-use state/PKCE transaction; OAuth callback binding is external."""
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(48)
        challenge = _b64(hashlib.sha256(verifier.encode()).digest())
        self._pending = (state, verifier)
        params = {
            "client_id": self.client_id, "redirect_uri": self.redirect_uri,
            "response_type": "code", "scope": " ".join(sorted(self.scopes)),
            "access_type": "offline", "state": state,
            "code_challenge": challenge, "code_challenge_method": "S256",
        }
        return AUTHORIZATION_ENDPOINT + "?" + urlencode(params)

    def complete(self, *, state, code):
        """One-time callback exchange, with state and granted-scope checks."""
        pending, self._pending = self._pending, None
        if (pending is None or not isinstance(state, str)
                or not hmac.compare_digest(state, pending[0]) or not code):
            raise ReauthorizationRequired("OAuth authorization invalid")
        response = self._exchange({
            "grant_type": "authorization_code", "code": code,
            "redirect_uri": self.redirect_uri,
            "code_verifier": pending[1], "client_id": self.client_id,
            "client_secret": self._client_secret,
        })
        if not isinstance(response, dict) or not response.get("refresh_token"):
            raise ReauthorizationRequired("offline refresh token unavailable")
        granted = frozenset(str(response.get("scope", "")).split())
        if not self.scopes.issubset(granted):
            raise ReauthorizationRequired("required OAuth scopes unavailable")
        self._vault.save({"refresh_token": response["refresh_token"],
                          "scopes": sorted(granted)})
        self._access = None
        self._expires = 0

    def access_token(self):
        """Refresh on demand; refresh token remains private to the vault."""
        now = self._clock()
        if self._access is not None and now + 60 < self._expires:
            return self._access
        stored = self._vault.load()
        if not isinstance(stored, dict) or not stored.get("refresh_token"):
            raise ReauthorizationRequired("Google connection requires authorization")
        granted = frozenset(stored.get("scopes", []))
        if not self.scopes.issubset(granted):
            raise ReauthorizationRequired("stored OAuth grant is insufficient")
        try:
            response = self._exchange({
                "grant_type": "refresh_token",
                "refresh_token": stored["refresh_token"],
                "client_id": self.client_id, "client_secret": self._client_secret,
            })
        except Exception as error:
            raise ReauthorizationRequired("Google token refresh failed") from error
        if not isinstance(response, dict) or not response.get("access_token"):
            raise ReauthorizationRequired("Google token refresh failed")
        if "scope" in response and not self.scopes.issubset(
                frozenset(str(response["scope"]).split())):
            raise ReauthorizationRequired("refreshed OAuth scopes insufficient")
        if "refresh_token" in response:
            if not response["refresh_token"]:
                raise ReauthorizationRequired("invalid rotated refresh token")
            self._vault.save({"refresh_token": response["refresh_token"],
                              "scopes": sorted(granted)})
        self._access = response["access_token"]
        self._expires = now + max(0, int(response.get("expires_in", 0)))
        return self._access
