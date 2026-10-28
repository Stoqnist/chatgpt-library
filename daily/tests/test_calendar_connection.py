"""Fake-only end-to-end tests for owner-linked Calendar OAuth routes.

No real Google account, code exchange or Calendar contents are accessed.
"""
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
import urllib.parse
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, password_hash
from calendar_oauth import FREEBUSY_SCOPE, CalendarOAuthError

CLIENT = "123456-test.apps.googleusercontent.com"
SECRET = "GOCSPX-fake-calendar-client-secret"
REDIRECT = "https://stoq.page/daily/api/calendar/callback"
ACCESS_CODE = "fictional-owner-access-code"


class CalendarConsentIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.login_hash = password_hash(ACCESS_CODE)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.now = 100000
        self.app = App(self.tmp.name, "https://stoq.page", self.login_hash,
                       clock=lambda: self.now)
        self.owner_cookie = ""
        self.csrf = ""

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.tmp.cleanup()

    def request(self, path, payload=None, *, cookie=None, csrf=None,
                origin="https://stoq.page", query=""):
        blob = json.dumps(payload).encode() if payload is not None else b""
        environ = {
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "REQUEST_METHOD": "POST" if payload is not None else "GET",
            "CONTENT_TYPE": "application/json",
            "CONTENT_LENGTH": str(len(blob)),
            "wsgi.input": io.BytesIO(blob),
            "HTTP_ORIGIN": origin,
            "HTTP_X_CSRF_TOKEN": self.csrf if csrf is None else csrf,
            "HTTP_COOKIE": self.owner_cookie if cookie is None else cookie,
        }
        found = {}
        def start(status, headers):
            found.update(status=int(status.split()[0]), headers=dict(headers))
        body = b"".join(self.app(environ, start))
        found["body"] = body
        if found["headers"]["Content-Type"] == "application/json":
            found["json"] = json.loads(body)
        return found

    def login(self):
        result = self.request("/daily/api/login", {"password": ACCESS_CODE})
        self.assertEqual(result["status"], 200)
        self.owner_cookie = result["headers"]["Set-Cookie"].split(";")[0]
        self.csrf = self.request("/daily/api/state")["json"]["csrf"]

    def configure(self):
        path = self.app.calendar.client
        path.write_text(json.dumps({"web": {
            "client_id": CLIENT, "client_secret": SECRET,
            "redirect_uris": [REDIRECT]}}))
        os.chmod(path, 0o600)

    def begin(self):
        result = self.request("/daily/api/calendar/connect", {})
        self.assertEqual(result["status"], 200, result)
        correlation_cookie = result["headers"]["Set-Cookie"].split(";")[0]
        url = result["json"]["authorization_url"]
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)
        return result, correlation_cookie, query["state"][0]

    def callback(self, state, cookie, code="fictional-google-authorization-code"):
        query = urllib.parse.urlencode({"state": state, "code": code})
        return self.request("/daily/api/calendar/callback",
                            cookie=cookie, query=query)

    def test_disabled_without_client_configuration(self):
        self.login()
        status = self.request("/daily/api/state")["json"]["calendar"]
        self.assertEqual(status, {"configured": False, "connected": False})
        self.assertEqual(
            self.request("/daily/api/calendar/connect", {})["status"], 503)
        self.assertFalse(self.app.calendar.grant.exists())

    def test_owner_and_csrf_required_before_google_redirect(self):
        self.configure()
        self.assertEqual(self.request("/daily/api/calendar/connect", {})["status"], 401)
        self.login()
        self.assertEqual(self.request(
            "/daily/api/calendar/connect", {}, csrf="wrong")["status"], 403)
        self.assertEqual(self.request(
            "/daily/api/calendar/connect", {}, origin="https://wrong.example")["status"], 403)
        self.assertEqual(self.request("/daily/api/state")["json"]["calendar"],
                         {"configured": True, "connected": False})

    def test_config_must_be_private_and_exact_redirect(self):
        self.configure()
        self.login()
        os.chmod(self.app.calendar.client, 0o644)
        self.assertEqual(self.request("/daily/api/calendar/connect", {})["status"], 503)
        os.chmod(self.app.calendar.client, 0o600)
        self.app.calendar.client.write_text(json.dumps({"web": {
            "client_id": CLIENT, "client_secret": SECRET,
            "redirect_uris": ["https://example.invalid/callback"]}}))
        self.assertEqual(self.request("/daily/api/calendar/connect", {})["status"], 503)

    def test_complete_without_strict_daily_cookie_and_replay_denied(self):
        self.configure()
        self.login()
        response, corr_cookie, state = self.begin()
        self.assertIn("HttpOnly", response["headers"]["Set-Cookie"])
        self.assertIn("SameSite=Lax", response["headers"]["Set-Cookie"])
        self.assertIn("Secure", response["headers"]["Set-Cookie"])
        self.assertEqual(
            urllib.parse.parse_qs(urllib.parse.urlparse(
                response["json"]["authorization_url"]).query)["scope"],
            [FREEBUSY_SCOPE])
        tokens = {
            "refresh_token": "fictional-refresh-token-value",
            "access_token": "fictional-access-token-value",
            "expires_in": 3600, "scope": FREEBUSY_SCOPE}
        # No owner cookie is included on this callback: SameSite=Strict isn't
        # sent when Google navigates cross-site back to Daily.
        with patch("calendar_connection.exchange_calendar_code", return_value=tokens) as exchange:
            callback = self.callback(state, corr_cookie)
        self.assertEqual(callback["status"], 303, callback)
        self.assertEqual(callback["headers"]["Location"], "/daily/?calendar=connected")
        self.assertEqual(exchange.call_count, 1)
        self.assertEqual(
            self.app.calendar.grant.stat().st_mode & 0o777, 0o600)
        grant = json.loads(self.app.calendar.grant.read_text())
        self.assertEqual(grant, {"refresh_token": tokens["refresh_token"]})
        self.assertNotIn("fictional", str(callback))
        self.assertEqual(self.request("/daily/api/state")["json"]["calendar"],
                         {"configured": True, "connected": True})
        with patch("calendar_connection.exchange_calendar_code") as replayed:
            self.assertEqual(self.callback(state, corr_cookie)["status"], 403)
        replayed.assert_not_called()

    def test_wrong_cookie_and_wrong_state_never_exchange(self):
        self.configure(); self.login()
        _, correlation, state = self.begin()
        with patch("calendar_connection.exchange_calendar_code") as exchange:
            self.assertEqual(self.callback(state, "stoq_calendar_correlation=wrong")["status"], 403)
            self.assertEqual(self.callback("different-state", correlation)["status"], 403)
        exchange.assert_not_called()
        self.assertFalse(self.app.calendar.grant.exists())

    def test_expired_or_logged_out_owner_cannot_link_google(self):
        self.configure(); self.login()
        _, cookie, state = self.begin()
        self.now += 601
        with patch("calendar_connection.exchange_calendar_code") as exchange:
            self.assertEqual(self.callback(state, cookie)["status"], 403)
        exchange.assert_not_called()

        self.now -= 601
        _, cookie2, state2 = self.begin()
        self.assertEqual(self.request("/daily/api/logout", {})["status"], 200)
        with patch("calendar_connection.exchange_calendar_code") as exchange:
            self.assertEqual(self.callback(state2, cookie2)["status"], 403)
        exchange.assert_not_called()

    def test_cancelled_consent_is_consumed_without_token_storage(self):
        self.configure(); self.login()
        _, cookie, state = self.begin()
        query = urllib.parse.urlencode({"state": state, "error": "access_denied"})
        with patch("calendar_connection.exchange_calendar_code") as exchange:
            response = self.request("/daily/api/calendar/callback", cookie=cookie, query=query)
            self.assertEqual(response["status"], 403)
            self.assertEqual(self.callback(state, cookie)["status"], 403)
        exchange.assert_not_called()
        self.assertFalse(self.app.calendar.grant.exists())

    def test_provider_failure_does_not_store_or_retry(self):
        self.configure(); self.login()
        _, cookie, state = self.begin()
        with patch("calendar_connection.exchange_calendar_code",
                   side_effect=CalendarOAuthError("fictional secret")) as exchange:
            result = self.callback(state, cookie)
        self.assertEqual(result["status"], 403)
        self.assertNotIn(b"secret", result["body"])
        self.assertEqual(exchange.call_count, 1)
        self.assertEqual(self.callback(state, cookie)["status"], 403)
        self.assertFalse(self.app.calendar.grant.exists())

    def test_disconnect_local_only_and_requires_owner(self):
        self.configure()
        self.assertEqual(self.request("/daily/api/calendar/disconnect", {})["status"], 401)
        self.login()
        self.app.calendar._save_refresh("fictional-refresh-token-value")
        self.assertEqual(self.request("/daily/api/calendar/disconnect", {},
                                      csrf="invalid")["status"], 403)
        response = self.request("/daily/api/calendar/disconnect", {})
        self.assertEqual(response["status"], 200)
        self.assertIn("Google Account", response["json"]["note"])
        self.assertFalse(self.app.calendar.grant.exists())
        self.assertFalse(self.request("/daily/api/state")["json"]["calendar"]["connected"])

    def test_duplicate_begin_invalidates_prior_pending_state(self):
        self.configure(); self.login()
        _, old_cookie, old_state = self.begin()
        _, new_cookie, new_state = self.begin()
        with patch("calendar_connection.exchange_calendar_code",
                   side_effect=CalendarOAuthError("fictional provider error")) as exchange:
            self.assertEqual(self.callback(old_state, old_cookie)["status"], 403)
            self.assertEqual(self.callback(new_state, new_cookie)["status"], 403)
        # Only the latest state may reach token exchange, and it is consumed
        # even if Google rejects the new authorization.
        self.assertEqual(exchange.call_count, 1)

if __name__ == "__main__":
    unittest.main()
