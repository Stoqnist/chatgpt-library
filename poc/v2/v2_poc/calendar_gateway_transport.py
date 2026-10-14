"""Fixed-destination Google token exchange and exact Calendar readback transport.

Only two HTTPS endpoints are supported. No event POST, search or delete route.
Caller must still independently enforce trusted principal/operation rights.
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request


TOKEN_URL = "https://oauth2.googleapis.com/token"
CALENDAR_API = "https://www.googleapis.com/calendar/v3/calendars/"
EVENT_ID = re.compile(r"[0-9a-v]{5,1024}\Z")


class ProviderReadUnavailable(RuntimeError):
    pass


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class GoogleHTTPS:
    """Injectable HTTPS client with bounded responses; never echo tokens/errors."""

    def __init__(self, *, timeout=10, open_request=None):
        if not 0 < timeout <= 30:
            raise ValueError("invalid HTTPS timeout")
        self.timeout = timeout
        self._open = open_request or urllib.request.build_opener(_NoRedirects()).open

    def _json(self, req):
        try:
            with self._open(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ProviderReadUnavailable("Google request unsuccessful")
                body = response.read(65537)
                if len(body) > 65536:
                    raise ProviderReadUnavailable("Google response too large")
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError()
                return data
        except (ProviderReadUnavailable, urllib.error.URLError, OSError,
                ValueError, TypeError, json.JSONDecodeError):
            raise ProviderReadUnavailable("Google request unavailable") from None

    def exchange(self, form):
        """Authorized OAuth exchange: caller owns state, PKCE and scope checks."""
        if not isinstance(form, dict) or form.get("grant_type") not in (
                "refresh_token", "authorization_code"):
            raise ValueError("unsupported token exchange")
        body = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            TOKEN_URL, data=body, method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded",
                     "Accept": "application/json"})
        return self._json(req)

    def read_event(self, *, calendar_id, event_id, fields, access_token):
        """Read exact event ID, not by title or user-supplied arbitrary URL."""
        if (not isinstance(calendar_id, str) or not 0 < len(calendar_id) <= 256
                or not isinstance(event_id, str)
                or EVENT_ID.fullmatch(event_id) is None
                or not isinstance(access_token, str) or not access_token):
            raise ValueError("invalid Calendar read parameters")
        # No caller-controlled arbitrary field expansion: minimal projection.
        from .calendar_gateway import READ_FIELDS
        if fields != READ_FIELDS:
            raise ValueError("unexpected event fields")
        url = (CALENDAR_API
               + urllib.parse.quote(calendar_id, safe="")
               + "/events/" + urllib.parse.quote(event_id, safe="")
               + "?" + urllib.parse.urlencode({"fields": fields}))
        req = urllib.request.Request(url, method="GET", headers={
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json"})
        return self._json(req)
