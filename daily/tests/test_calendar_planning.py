"""Opt-in Calendar-to-Planning contract tests. Fully fictional, no network."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import App, RESULT_SCHEMA, ROUTE_SCHEMA, PLAN_SCHEMA, password_hash
from calendar_verify import CalendarVerifyError
from calendar_planning import planning_freebusy
from test_daily import FakeProvider
from test_calendar_verify import Transport, token_response, CLIENT, SECRET, REFRESH, NOW

PROMPT = ('Help me plan my day. I slept well. I want to tidy the kitchen. '
          'I have an hour this morning.')
CONTEXT = {
    "status": "verified", "calendar": "primary",
    "timezone": "Europe/Amsterdam",
    "sample_free_windows": [
        {"start": "2026-10-28T10:00+01:00",
         "end": "2026-10-28T11:00+01:00"}
    ],
    "window_hours": 24,
    "interpretation": "Only calendar-free, never a confirmed commitment."
}


class PlanningOptinTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.login_hash = password_hash("fictional-test-owner")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.provider = FakeProvider()
        self.app = App(self.tmp.name, "https://stoq.page", self.login_hash, self.provider)
        self.app.key_path.write_text("sk-" + "x" * 30)
        self.cookie, self.csrf = "", ""

    def tearDown(self):
        self.app.pool.shutdown(wait=True)
        self.tmp.cleanup()

    def request(self, path, body=None, *, cookie=None, csrf=None,
                origin="https://stoq.page"):
        blob = json.dumps(body).encode() if body is not None else b""
        env = {
            "PATH_INFO": path, "REQUEST_METHOD": "POST" if body is not None else "GET",
            "CONTENT_TYPE": "application/json", "CONTENT_LENGTH": str(len(blob)),
            "wsgi.input": io.BytesIO(blob), "HTTP_ORIGIN": origin,
            "HTTP_X_CSRF_TOKEN": self.csrf if csrf is None else csrf,
            "HTTP_COOKIE": self.cookie if cookie is None else cookie,
        }
        found = {}
        def start(status, headers):
            found["status"] = int(status.split()[0])
        found["raw"] = b"".join(self.app(env, start))
        found["data"] = json.loads(found["raw"])
        return found

    def login(self):
        raw = json.dumps({"password": "fictional-test-owner"}).encode()
        env = {"PATH_INFO": "/daily/api/login", "REQUEST_METHOD": "POST",
               "HTTP_ORIGIN": "https://stoq.page", "CONTENT_TYPE": "application/json",
               "CONTENT_LENGTH": str(len(raw)), "wsgi.input": io.BytesIO(raw)}
        found = {}
        def start(status, headers):
            found.update(status=int(status.split()[0]), headers=dict(headers))
        list(self.app(env, start))
        self.assertEqual(found["status"], 200)
        self.cookie = found["headers"]["Set-Cookie"].split(";")[0]
        self.csrf = self.request("/daily/api/state")["data"]["csrf"]

    def configure_grant(self):
        client = self.app.calendar.client
        client.write_text(json.dumps({"web": {
            "client_id": CLIENT, "client_secret": SECRET,
            "redirect_uris": ["https://stoq.page/daily/api/calendar/callback"],
        }}))
        os.chmod(client, 0o600)
        self.app.calendar._save_refresh(REFRESH)

    def submit(self, prompt=PROMPT):
        response = self.request("/daily/api/run", {
            "prompt": prompt, "request_id": str(uuid.uuid4()),
        })
        self.assertEqual(response["status"], 202, response)
        self.app.pool.shutdown(wait=True)
        return self.request("/daily/api/state")["data"]["runs"][0]

    def test_default_off_and_no_calendar_read(self):
        self.login()
        self.assertFalse(self.request("/daily/api/state")["data"]["calendar"]["planning_enabled"])
        with patch("app.planning_freebusy") as read:
            result = self.submit()
        read.assert_not_called()
        self.assertEqual(result["status"], "completed")
        self.assertIn("Your check-in only", result["result"]["source"])
        self.assertFalse(any("calendar_availability" in p[1] for p in self.provider.calls))

    def test_toggle_requires_owner_csrf_and_live_grant(self):
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True})["status"], 401)
        self.login()
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True},
                                      csrf="bad")["status"], 403)
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True},
                                      origin="https://untrusted.example")["status"], 403)
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True})["status"], 409)
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": "true"})["status"], 400)
        self.configure_grant()
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True})["status"], 200)
        self.assertTrue(self.request("/daily/api/state")["data"]["calendar"]["planning_enabled"])
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": False})["status"], 200)
        self.assertFalse(self.app.calendar_planning_enabled())

    def test_opt_in_is_persistent_across_restart(self):
        self.configure_grant();self.login()
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True})["status"], 200)
        self.app.pool.shutdown(wait=True)
        self.app = App(self.tmp.name, "https://stoq.page", self.login_hash, self.provider)
        self.assertTrue(self.app.calendar_planning_enabled())

    def test_enabled_only_planning_receives_sanitized_availability(self):
        self.configure_grant();self.login()
        self.assertEqual(self.request("/daily/api/calendar/planning", {"enabled": True})["status"], 200)
        with patch("app.planning_freebusy", return_value=CONTEXT) as read:
            result = self.submit()
        read.assert_called_once()
        self.assertEqual(result["status"], "completed")
        self.assertIn("primary-calendar free/busy", result["result"]["source"])
        self.assertNotIn("sample_free_windows", json.dumps(result))
        self.assertEqual(self.provider.calls[0][2], ROUTE_SCHEMA)
        self.assertNotIn("calendar_availability", self.provider.calls[0][1])
        specialists = [(instructions, payload) for instructions, payload, schema
                       in self.provider.calls if schema is RESULT_SCHEMA]
        self.assertEqual(len(specialists), 3)
        calendar_calls = [p for _, p in specialists if "calendar_availability" in p]
        self.assertEqual(len(calendar_calls), 1)
        self.assertEqual(calendar_calls[0]["calendar_availability"], CONTEXT)
        self.assertEqual(calendar_calls[0]["user_reported_excerpts"],
                         ["I have an hour this morning."])
        final = [p for _, p, schema in self.provider.calls if schema is PLAN_SCHEMA][0]
        self.assertNotIn("calendar_availability", final)
        self.assertNotIn("sample_free_windows", json.dumps(final))

    def test_failed_calendar_read_falls_back_to_text_only(self):
        self.configure_grant();self.login()
        self.request("/daily/api/calendar/planning", {"enabled": True})
        with patch("app.planning_freebusy", side_effect=CalendarVerifyError("secret")):
            result = self.submit()
        self.assertEqual(result["status"], "completed")
        self.assertIn("could not be verified", result["result"]["source"])
        self.assertNotIn("secret", json.dumps(result))
        self.assertFalse(any("calendar_availability" in p[1] for p in self.provider.calls))

    def test_urgent_and_unrelated_routes_do_not_read_calendar(self):
        for route in (
            {"urgent": True, "tasks": []},
            {"urgent": False, "tasks": [
                {"domain": "wellbeing", "excerpts": ["I slept well."]}]},
        ):
            with self.subTest(route=route):
                self.app.pool.shutdown(wait=True)
                self.app = App(self.tmp.name, "https://stoq.page", self.login_hash,
                               FakeProvider(route=route))
                self.app.key_path.write_text("sk-"+"x"*30)
                self.configure_grant()
                self.login()
                self.request("/daily/api/calendar/planning", {"enabled": True})
                with patch("app.planning_freebusy") as read:
                    result = self.submit()
                read.assert_not_called()
                self.assertEqual(result["status"],
                                 "needs_attention" if route["urgent"] else "completed")

    def test_disconnect_resets_optin(self):
        self.configure_grant();self.login()
        self.request("/daily/api/calendar/planning", {"enabled": True})
        self.assertEqual(self.request("/daily/api/calendar/disconnect", {})["status"], 200)
        self.assertFalse(self.app.calendar_planning_enabled())
        self.configure_grant()
        self.assertFalse(self.app.calendar_planning_enabled())


class PlanningFreebusySanitizationTest(unittest.TestCase):
    def test_primary_only_no_event_data_and_europe_amsterdam_zone(self):
        with tempfile.TemporaryDirectory() as folder:
            data = Path(folder)
            client = data / "calendar-client.json"
            grant = data / "calendar-grant.json"
            client.write_text(json.dumps({"web":{
                "client_id":CLIENT,"client_secret":SECRET,
                "redirect_uris":["https://stoq.page/daily/api/calendar/callback"]}}))
            grant.write_text(json.dumps({"refresh_token":REFRESH}))
            os.chmod(client, 0o600)
            os.chmod(grant, 0o600)
            token = Transport(token_response())
            calendar = Transport({"calendars":{"primary":{"busy":[{
                "start":"2026-11-01T10:00:00Z",
                "end":"2026-11-01T11:00:00Z",
                "summary":"PRIVATE DESCRIPTION",
            }]}}})
            result = planning_freebusy(
                data, NOW, token_opener=token, calendar_opener=calendar)
            self.assertEqual(result["calendar"], "primary")
            self.assertEqual(result["timezone"], "Europe/Amsterdam")
            self.assertLessEqual(len(result["sample_free_windows"]), 6)
            self.assertNotIn("PRIVATE DESCRIPTION", json.dumps(result))
            self.assertNotIn(SECRET, json.dumps(result))
            self.assertNotIn(REFRESH, json.dumps(result))
            self.assertEqual(len(calendar.calls), 1)
            self.assertEqual(json.loads(calendar.calls[0][0].data)["items"],
                             [{"id":"primary"}])


if __name__ == "__main__":
    unittest.main()
