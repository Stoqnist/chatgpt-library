"""Verify an owner's saved Calendar permission using Google freeBusy only.

No events.list, event titles, persistence, check-in writes, model inputs,
or background activity. Tokens and private availability stay in-process.
A user must explicitly invoke the authenticated verification endpoint.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import stat
import urllib.error
import urllib.parse
import urllib.request

from calendar_connection import _read_client, CalendarConnectionError
from calendar_oauth import TOKEN_URL, FREEBUSY_SCOPE
from calendar_readonly import read_freebusy, CalendarUnavailable

MAX_TOKEN_RESPONSE = 16384


class CalendarVerifyError(Exception):
    """Redacted verification failure; never contains OAuth or event data."""


def _read_refresh(path):
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode) != 0o600:
            raise ValueError()
        obj = json.loads(path.read_text(encoding="utf-8"))
        token = obj["refresh_token"]
        if (not isinstance(token, str) or not 20 <= len(token) <= 8192
                or any(ord(c) < 33 or ord(c) > 126 for c in token)):
            raise ValueError()
        return token
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        raise CalendarVerifyError("Calendar permission is missing or invalid.") from None


def refresh_access(client_id, secret, refresh_token, *, opener=None):
    """Exchange the already-consented grant for a short-lived bearer token.

    The original authorization response was restricted to calendar.freebusy.
    Google may omit 'scope' from refresh responses; when present, it MUST
    still match the exact previously approved scope.
    """
    body = urllib.parse.urlencode({
        "client_id": client_id, "client_secret": secret,
        "refresh_token": refresh_token, "grant_type": "refresh_token",
    }).encode("ascii")
    request = urllib.request.Request(
        TOKEN_URL, data=body, method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=10) as response:
            raw = response.read(MAX_TOKEN_RESPONSE + 1)
        if len(raw) > MAX_TOKEN_RESPONSE:
            raise CalendarVerifyError("Calendar permission could not be verified.")
        result = json.loads(raw)
    except CalendarVerifyError:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            TimeoutError, ValueError, TypeError, UnicodeError):
        raise CalendarVerifyError("Calendar permission could not be verified.") from None

    if not isinstance(result, dict):
        raise CalendarVerifyError("Calendar permission could not be verified.")
    token = result.get("access_token")
    valid_token = (isinstance(token, str) and 20 <= len(token) <= 8192 and
                   all(33 <= ord(c) <= 126 for c in token))
    bearer = isinstance(result.get("token_type"), str) and result["token_type"].lower() == "bearer"
    expires = result.get("expires_in")
    valid_expiry = type(expires) is int and 60 <= expires <= 86400
    scope = result.get("scope")
    valid_scope = "scope" not in result or (isinstance(scope, str) and set(scope.split()) == {FREEBUSY_SCOPE})
    if not (valid_token and bearer and valid_expiry and valid_scope):
        raise CalendarVerifyError("Calendar permission could not be verified.")
    return token


def verify_primary_freebusy(data_dir, now, *, token_opener=None, calendar_opener=None):
    """Check a 24-hour primary-calendar window; return only verification flag.

    No raw availability or credential is sent to the UI, models or files.
    An error means context is unavailable, never 'all free'.
    """
    data = Path(data_dir)
    try:
        client, secret = _read_client(data / "calendar-client.json")
    except CalendarConnectionError:
        raise CalendarVerifyError("Calendar configuration is unavailable.") from None
    refresh = _read_refresh(data / "calendar-grant.json")
    access = refresh_access(client, secret, refresh, opener=token_opener)
    start = datetime.fromtimestamp(now, tz=timezone.utc)
    end = start + timedelta(hours=24)
    try:
        read_freebusy(access, ["primary"], start, end, opener=calendar_opener)
    except (CalendarUnavailable, ValueError, OverflowError, OSError):
        raise CalendarVerifyError("Calendar availability could not be verified.") from None
    return {"verified": True, "scope": "freebusy", "calendar_count": 1,
            "window_hours": 24}
