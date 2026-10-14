"""Offline inert BFF and Compose exposure regression tests; no HTTP network."""
import io
import json
from pathlib import Path
import unittest
from wsgiref.util import setup_testing_defaults

from v2_poc.bff_offline import application


def call(path, method="GET", *, headers=None):
    env = {"PATH_INFO": path, "REQUEST_METHOD": method,
           "wsgi.input": io.BytesIO(b"")}
    setup_testing_defaults(env)
    for name, value in (headers or {}).items():
        env[name] = value
    captured = {}

    def response(status, response_headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = dict(response_headers)

    captured["body"] = b"".join(application(env, response))
    return captured


class FailClosedBFFTests(unittest.TestCase):
    def test_liveness_is_not_readiness_or_authentication(self):
        result = call("/_internal/live")
        self.assertEqual(result["status"], "200 OK")
        payload = json.loads(result["body"])
        self.assertEqual(payload, {
            "status": "process_alive", "authentication_ready": False,
            "calendar_writes_enabled": False,
        })
        self.assertEqual(call("/_internal/live", "HEAD")["body"], b"")

    def test_all_private_and_authentication_paths_deny_even_with_spoofed_headers(self):
        fake_identity = {
            "HTTP_AUTHORIZATION": "Bearer fake-bearer",
            "HTTP_COOKIE": "agency_session=fake-value",
            "HTTP_CF_ACCESS_AUTHENTICATED_USER_EMAIL": "fictional@example.invalid",
            "HTTP_X_FORWARDED_USER": "fictional",
        }
        for path in (
            "/", "/login", "/auth/google", "/auth/google/callback",
            "/auth/calendar/callback", "/consent", "/consent/approve",
            "/calendar/events", "/api/calendar/insert", "/admin",
            "/_internal/ready", "/debug", "/docs",
        ):
            for method in ("GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"):
                with self.subTest(path=path, method=method):
                    res = call(path, method, headers=fake_identity)
                    self.assertEqual(res["status"], "503 Service Unavailable")
                    self.assertNotIn("fake-bearer", res["body"].decode())
                    self.assertNotIn("fictional@", res["body"].decode())
        self.assertEqual(call("/_internal/live", "POST")["status"],
                         "503 Service Unavailable")

    def test_every_response_is_not_cacheable_and_cannot_be_embedded(self):
        for path in ("/", "/_internal/live", "/consent"):
            with self.subTest(path=path):
                h = call(path)["headers"]
                self.assertIn("no-store", h["Cache-Control"])
                self.assertEqual(h["X-Content-Type-Options"], "nosniff")
                self.assertEqual(h["X-Frame-Options"], "DENY")
                self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])
                self.assertEqual(h["Referrer-Policy"], "no-referrer")

    def test_compose_uses_separate_loopback_port_with_no_secret_mounts(self):
        text = (Path(__file__).resolve().parents[1] /
                "deploy/bff/compose.yaml").read_text()
        self.assertIn('name: agency-bff', text)
        self.assertIn('"127.0.0.1:18000:8000"', text)
        self.assertIn("read_only: true", text)
        self.assertIn("no-new-privileges:true", text)
        self.assertIn("cap_drop:", text)
        self.assertIn('restart: "no"', text)
        for forbidden in ("network_mode: host", "privileged: true",
                          "docker.sock", "stoq-infrastructure", "cloudflared"):
            self.assertNotIn(forbidden, text)


if __name__ == "__main__":
    unittest.main()
