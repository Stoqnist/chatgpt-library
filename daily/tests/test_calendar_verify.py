"""Offline verification of a single consented Google primary Calendar.

All credentials and event-like data are fictional. No network requests occur.
"""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_verify import (
    CalendarVerifyError, refresh_access, verify_primary_freebusy,
    _read_refresh,
)
from calendar_oauth import FREEBUSY_SCOPE, TOKEN_URL

CLIENT = "123456-test.apps.googleusercontent.com"
SECRET = "GOCSPX-fictional-value-for-tests"
REFRESH = "fictional-refresh-token-never-valid"
ACCESS = "fictional-access-token-never-valid"
NOW = 1793523600


class Response:
    def __init__(self, payload):
        self.payload = io.BytesIO(payload)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, size):
        return self.payload.read(size)


class Transport:
    def __init__(self, payload, error=None):
        self.payload = payload
        self.error = error
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        raw = self.payload if isinstance(self.payload, bytes) else json.dumps(self.payload).encode()
        return Response(raw)


def token_response(**overrides):
    return {"access_token": ACCESS, "token_type": "Bearer",
            "expires_in": 3600, "scope": FREEBUSY_SCOPE, **overrides}


class CalendarVerifyTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.data = Path(self.dir.name)
        self.client = self.data / "calendar-client.json"
        self.grant = self.data / "calendar-grant.json"
        self.client.write_text(json.dumps({"web": {
            "client_id": CLIENT, "client_secret": SECRET,
            "redirect_uris": ["https://stoq.page/daily/api/calendar/callback"],
        }}))
        os.chmod(self.client, 0o600)
        self.grant.write_text(json.dumps({"refresh_token": REFRESH}))
        os.chmod(self.grant, 0o600)

    def tearDown(self):
        self.dir.cleanup()

    def test_only_google_token_refresh_and_freebusy_query(self):
        token = Transport(token_response())
        availability = Transport({"calendars": {"primary": {"busy": [
            {"start": "2026-11-01T10:00:00Z",
             "end": "2026-11-01T11:00:00Z",
             "summary": "PRIVATE APPOINTMENT"},
        ]}}})
        result = verify_primary_freebusy(
            self.data, NOW, token_opener=token, calendar_opener=availability)
        self.assertEqual(result, {
            "verified": True, "scope": "freebusy",
            "calendar_count": 1, "window_hours": 24,
        })
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn(REFRESH, str(result))
        self.assertNotIn(ACCESS, str(result))
        req, timeout = token.calls[0]
        self.assertEqual(req.full_url, TOKEN_URL)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(timeout, 10)
        body = urllib.parse.parse_qs(req.data.decode())
        self.assertEqual(body["grant_type"], ["refresh_token"])
        self.assertEqual(body["client_id"], [CLIENT])
        self.assertEqual(body["client_secret"], [SECRET])
        self.assertEqual(body["refresh_token"], [REFRESH])
        self.assertNotIn("scope", body)
        req, timeout = availability.calls[0]
        self.assertEqual(req.full_url, "https://www.googleapis.com/calendar/v3/freeBusy")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.headers["Authorization"], "Bearer " + ACCESS)
        calendar_body = json.loads(req.data)
        self.assertEqual(calendar_body["items"], [{"id": "primary"}])
        self.assertEqual(timeout, 10)
        self.assertTrue(self.grant.exists())
        self.assertEqual(self.grant.stat().st_mode & 0o777, 0o600)

    def test_refresh_scope_omission_allowed_but_any_extra_scope_rejected(self):
        response = token_response()
        response.pop("scope")
        self.assertEqual(refresh_access(CLIENT, SECRET, REFRESH,
                                         opener=Transport(response)), ACCESS)
        for scope in ("https://www.googleapis.com/auth/calendar",
                      FREEBUSY_SCOPE + " openid", "", 22):
            with self.subTest(scope=scope), self.assertRaises(CalendarVerifyError):
                refresh_access(CLIENT, SECRET, REFRESH,
                               opener=Transport(token_response(scope=scope)))

    def test_bad_refresh_response_fails_closed_and_does_not_leak(self):
        cases = [
            {"token_type": "Other"}, {"access_token": ""},
            {"expires_in": -1}, {"expires_in": True},
            {"expires_in": "3600"}, {"access_token": ["bad"]},
        ]
        for changes in cases:
            with self.subTest(changes=changes), self.assertRaises(CalendarVerifyError):
                refresh_access(CLIENT, SECRET, REFRESH,
                               opener=Transport(token_response(**changes)))
        for error in (urllib.error.URLError("fictional-secret-in-error"),
                      TimeoutError("fictional-secret-in-error")):
            with self.assertRaises(CalendarVerifyError) as caught:
                refresh_access(CLIENT, SECRET, REFRESH,
                               opener=Transport({}, error=error))
            self.assertNotIn("fictional-secret", str(caught.exception))

    def test_bad_private_grant_permissions_or_missing_file_block_network(self):
        token = Transport(token_response())
        availability = Transport({"calendars": {"primary": {"busy": []}}})
        os.chmod(self.grant, 0o644)
        with self.assertRaises(CalendarVerifyError):
            verify_primary_freebusy(self.data, NOW,
                                    token_opener=token, calendar_opener=availability)
        os.chmod(self.grant, 0o600)
        self.grant.unlink()
        with self.assertRaises(CalendarVerifyError):
            verify_primary_freebusy(self.data, NOW,
                                    token_opener=token, calendar_opener=availability)
        self.assertEqual(token.calls, [])
        self.assertEqual(availability.calls, [])

    def test_provider_missing_calendar_is_not_counted_as_available(self):
        token = Transport(token_response())
        invalid = {"calendars": {"primary": {"errors": [
            {"reason": "notFound"}], "busy": []}}}
        with self.assertRaises(CalendarVerifyError):
            verify_primary_freebusy(self.data, NOW,
                                    token_opener=token,
                                    calendar_opener=Transport(invalid))

    def test_oversized_and_invalid_token_payload_rejected(self):
        for data in (b"[]", b"not-json", b"{" + b"x"*16385):
            with self.subTest(length=len(data)), self.assertRaises(CalendarVerifyError):
                refresh_access(CLIENT, SECRET, REFRESH, opener=Transport(data))


if __name__ == "__main__":
    unittest.main()
