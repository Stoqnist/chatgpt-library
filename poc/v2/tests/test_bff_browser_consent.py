"""Fictional offline server-session / HTML review / one-shot CSRF tests."""
import hashlib
import tempfile
from pathlib import Path
import unittest

from v2_poc.bff_google_oidc import VerifiedGoogleIdentity
from v2_poc.bff_browser_consent import OfflineBrowserConsent, session_cookie

NOW = 1_000_000
CLIENT = "fictional-google-login-client"
ORIGIN = "https://agency.example.invalid"
IDENTITY = VerifiedGoogleIdentity(
    "https://accounts.google.com", "fictional-user-sub", CLIENT, NOW + 1200)
PREVIEW = {
    "action": "calendar.event.create",
    "calendar_id": "fictional-calendar",
    "event_id": "fictional-event-id",
    "summary": "<img src=x onerror=alert(1)>",
    "start": {"dateTime": "2030-01-02T09:00:00+01:00"},
    "end": {"dateTime": "2030-01-02T09:30:00+01:00"},
    "visibility": "private",
    "transparency": "transparent",
    "attendees": [],
    "conference_data": None,
    "reminders": {"useDefault": False, "overrides": []},
    "insert_params": {"sendUpdates": "none"},
}
PLAN_DIGEST = hashlib.sha256(b"fictional-canonical-plan").hexdigest()


class BrowserConsentTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.db = Path(t.name) / "fictional-bff.sqlite"
        self.now = [NOW]
        self.store = self.new_store()
        self.login = self.store.create_session(verified_identity=IDENTITY)
        self.token = self.login["session_token"]

    def new_store(self):
        return OfflineBrowserConsent(self.db, oidc_client_id=CLIENT,
                                     trusted_origin=ORIGIN,
                                     clock=lambda: self.now[0])

    def consent(self):
        return self.store.begin_consent(
            session_token=self.token, preview=PREVIEW,
            plan_sha256=PLAN_DIGEST)

    def decide(self, c, **changes):
        defaults = {
            "session_token": self.token, "origin": ORIGIN,
            "challenge_id": c["challenge_id"],
            "csrf_token": c["csrf_token"],
            "decision": "approved",
            "displayed_sha256": c["display_sha256"],
        }
        return self.store.decide(**(defaults | changes))

    def test_session_cookie_is_host_only_secure_and_non_revealing_in_db(self):
        cookie = session_cookie(self.token)
        self.assertTrue(cookie.startswith("__Host-agency_session="))
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Lax", cookie)
        self.assertNotIn("Domain=", cookie)
        with self.store._db() as db:
            row = db.execute("SELECT session_hash FROM bff_sessions").fetchone()
            self.assertEqual(row[0], hashlib.sha256(self.token.encode()).hexdigest())
            self.assertNotEqual(row[0], self.token)

    def test_approval_needs_explicit_post_but_never_issues_proof(self):
        c = self.consent()
        page = c["html"]
        self.assertIn("<form method=\"post\"", page)
        self.assertIn('name="decision" value="approved"', page)
        self.assertIn('name="decision" value="declined"', page)
        self.assertNotIn("<img ", page)
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", page)
        self.assertNotIn("<script", page)
        result = self.decide(c)
        self.assertEqual(result, {
            "status": "recorded_unissued", "decision": "approved",
            "plan_sha256": PLAN_DIGEST,
            "display_sha256": c["display_sha256"],
            "external_actions": 0, "live_write_authorized": False,
        })
        with self.assertRaises(PermissionError):
            self.decide(c)

    def test_csrf_origin_session_preview_and_expiry_are_fail_closed(self):
        c = self.consent()
        others = self.store.create_session(verified_identity=IDENTITY)
        for changes in (
            {"origin": "https://attacker.invalid"},
            {"origin": None},
            {"csrf_token": "wrong-csrf"},
            {"challenge_id": "other-challenge"},
            {"displayed_sha256": "0" * 64},
            {"session_token": others["session_token"]},
            {"decision": "yes"},
        ):
            with self.subTest(changes=changes), self.assertRaises(PermissionError):
                self.decide(c, **changes)
        self.assertEqual(self.decide(c, decision="declined")["decision"], "declined")
        with self.assertRaises(PermissionError):
            self.decide(c)

    def test_logout_revokes_pending_consent_and_restart_preserves_denial(self):
        c = self.consent()
        self.assertEqual(self.store.logout(session_token=self.token),
                         {"status": "local_session_revoked", "external_actions": 0})
        reopened = self.new_store()
        with self.assertRaises(PermissionError):
            reopened.decide(session_token=self.token, origin=ORIGIN,
                            challenge_id=c["challenge_id"],
                            csrf_token=c["csrf_token"], decision="approved",
                            displayed_sha256=c["display_sha256"])
        with self.assertRaises(PermissionError):
            reopened.begin_consent(
                session_token=self.token, preview=PREVIEW,
                plan_sha256=PLAN_DIGEST)
        with self.store._db() as db:
            self.assertEqual(db.execute(
                "SELECT state FROM bff_consent_challenges").fetchone(),
                ("revoked",))

    def test_expired_session_and_challenge_never_authorize(self):
        c = self.consent()
        self.now[0] = NOW + 121
        with self.assertRaises(PermissionError):
            self.decide(c)
        self.now[0] = NOW + 901
        with self.assertRaises(PermissionError):
            self.store.begin_consent(
                session_token=self.token, preview=PREVIEW,
                plan_sha256=PLAN_DIGEST)

    def test_no_unverified_google_claims_allowed_to_mint_session(self):
        for ident in ({"sub": "fictional"}, "token", None,
                      VerifiedGoogleIdentity(
                          "https://evil.invalid", "fictional-user", CLIENT,
                          NOW + 300),
                      VerifiedGoogleIdentity(
                          "https://accounts.google.com", "fictional-user",
                          "different-client", NOW + 300),
                      VerifiedGoogleIdentity(
                          "https://accounts.google.com", "fictional-user",
                          CLIENT, NOW - 1)):
            with self.subTest(ident=type(ident).__name__), self.assertRaises(
                    PermissionError):
                self.store.create_session(verified_identity=ident)

    def test_reject_noncanonical_plan_or_oversized_preview(self):
        for bad in ("not-a-sha256", "F" * 64, "", None):
            with self.assertRaises(PermissionError):
                self.store.begin_consent(
                    session_token=self.token, preview=PREVIEW,
                    plan_sha256=bad)
        with self.assertRaises(PermissionError):
            self.store.begin_consent(
                session_token=self.token, preview={"text": "x" * 9000},
                plan_sha256=PLAN_DIGEST)

    def test_no_http_endpoints_are_activated(self):
        from v2_poc.bff_offline import application
        import io
        from wsgiref.util import setup_testing_defaults
        for path in ("/login", "/auth/google", "/auth/google/callback",
                     "/consent", "/consent/decision", "/calendar/events"):
            env = {"PATH_INFO": path, "REQUEST_METHOD": "POST",
                   "wsgi.input": io.BytesIO(b"")}
            setup_testing_defaults(env)
            status = []
            body = b"".join(application(
                env, lambda s, h, exc=None: status.append(s)))
            self.assertEqual(status[0], "503 Service Unavailable")
            self.assertIn(b"not_implemented", body)


if __name__ == "__main__":
    unittest.main()
