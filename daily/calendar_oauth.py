"""Minimal Google Calendar OAuth authorization-code/PKCE protocol helpers.

NOT connected to the Daily app, its login sessions, or live Google accounts.
A future reviewed runtime must bind state to the authenticated owner session,
expire and consume it exactly once, and secure refresh tokens on private disk.
No credentials, actual calendar identities or provider data belong in tests.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CALLBACK_URL = "https://stoq.page/daily/api/calendar/callback"
FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
MAX_TOKEN_RESPONSE = 16384


class CalendarOAuthError(Exception):
    """Fixed, nonsensitive error that must not include OAuth values."""


def _client_id(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 256 or not re.fullmatch(
            r"[A-Za-z0-9._-]+\.apps\.googleusercontent\.com", value):
        raise ValueError("Invalid Google OAuth client configuration.")
    return value


def _oauth_value(value, limit=4096):
    if not isinstance(value, str) or not 1 <= len(value) <= limit or any(
            ord(char) < 33 or ord(char) > 126 for char in value):
        raise ValueError("Invalid OAuth parameter.")
    return value


def _pkce_challenge(verifier):
    value = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def begin_calendar_auth(client_id):
    """Return (authorization URL, state, verifier); caller MUST securely bind state.

    The URL asks for free/busy only; approval is never inferred from a Google
    sign-in at Cloudflare or from a connected ChatGPT Calendar integration.
    """
    client_id = _client_id(client_id)
    state = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    query = urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": CALLBACK_URL,
        "response_type": "code",
        "scope": FREEBUSY_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    })
    return AUTH_URL + "?" + query, state, verifier


def parse_calendar_callback(query_string, expected_state):
    """Extract an OAuth code only after constant-time state comparison.

    This is a *parser*, not a callback endpoint. The future server must reject
    requests without an authenticated owner session and one-time, unexpired
    state; it must consume the state even when Google reports an error.
    """
    _oauth_value(expected_state, 256)
    if not isinstance(query_string, str) or len(query_string) > 8192:
        raise CalendarOAuthError("Calendar authorization could not be verified.")
    try:
        pairs = urllib.parse.parse_qsl(
            query_string, keep_blank_values=True, strict_parsing=True,
            max_num_fields=12)
    except ValueError:
        raise CalendarOAuthError("Calendar authorization could not be verified.") from None
    keys = [key for key, _ in pairs]
    if any(keys.count(key) != 1 for key in ("state", "code", "error") if key in keys):
        raise CalendarOAuthError("Calendar authorization could not be verified.")
    params = dict(pairs)
    if "state" not in params or not hmac.compare_digest(
            params["state"], expected_state):
        raise CalendarOAuthError("Calendar authorization could not be verified.")
    if params.get("error") or "code" not in params:
        raise CalendarOAuthError("Calendar authorization was not granted.")
    try:
        return _oauth_value(params["code"], 4096)
    except ValueError:
        raise CalendarOAuthError("Calendar authorization could not be verified.") from None


def exchange_calendar_code(client_id, client_secret, code, verifier, *,
                           opener=None):
    """Exchange a single-use code; return PRIVATE token data for server only.

    The future handler must never echo this result to the browser or logs.
    Verify returned scopes before retaining any token; absence of a refresh
    token means no durable authorization and must be treated as incomplete.
    """
    client_id = _client_id(client_id)
    client_secret = _oauth_value(client_secret)
    code = _oauth_value(code)
    verifier = _oauth_value(verifier, 128)
    if not 43 <= len(verifier) <= 128:
        raise ValueError("Invalid PKCE verifier.")
    body = urllib.parse.urlencode({
        "code": code, "client_id": client_id, "client_secret": client_secret,
        "redirect_uri": CALLBACK_URL, "grant_type": "authorization_code",
        "code_verifier": verifier,
    }).encode()
    req = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(req, timeout=10) as response:
            raw = response.read(MAX_TOKEN_RESPONSE + 1)
        if len(raw) > MAX_TOKEN_RESPONSE:
            raise CalendarOAuthError("Calendar authorization response was invalid.")
        payload = json.loads(raw)
    except CalendarOAuthError:
        raise
    except (OSError, ValueError, UnicodeError, urllib.error.HTTPError):
        raise CalendarOAuthError("Calendar authorization could not be completed.") from None

    if not isinstance(payload, dict) or set(str(payload.get("scope", "")).split()) != {
            FREEBUSY_SCOPE} or payload.get("token_type", "").lower() != "bearer":
        raise CalendarOAuthError("Calendar authorization scope was not verified.")
    try:
        access = _oauth_value(payload.get("access_token"))
        refresh = _oauth_value(payload.get("refresh_token"))
        expires = payload.get("expires_in")
        if type(expires) is not int or not 60 <= expires <= 86400:
            raise ValueError()
    except ValueError:
        raise CalendarOAuthError("Calendar authorization was incomplete.") from None
    return {"access_token": access, "refresh_token": refresh,
            "expires_in": expires, "scope": FREEBUSY_SCOPE}
