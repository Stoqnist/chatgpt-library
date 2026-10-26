"""Offline state/binder CSRF and replay tests for planned Google callback."""
import tempfile
from pathlib import Path
import unittest
from urllib.parse import parse_qs, urlsplit

from v2_poc.bff_google_login_state import OfflineLoginState

NOW = 1_000_000
CLIENT = "fictional-google-login-client"
REDIRECT = "https://agency.example.invalid/auth/google/callback"


class BrowserBoundGoogleLoginTests(unittest.TestCase):
    def setUp(self):
        t = tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.path = Path(t.name) / "fictional-oidc.sqlite"
        self.now = [NOW]
        self.store = self.open_store()

    def open_store(self):
        return OfflineLoginState(
            self.path, client_id=CLIENT, redirect_uri=REDIRECT,
            clock=lambda: self.now[0])

    def create(self):
        a = self.store.begin()
        state = parse_qs(urlsplit(a["authorization_url"]).query)["state"][0]
        self.assertEqual(state, a["state"])
        self.assertIn("Secure; HttpOnly; SameSite=Lax", a["browser_cookie"])
        self.assertNotIn("Domain=", a["browser_cookie"])
        binding = a["browser_cookie"].split(";")[0].split("=", 1)[1]
        return a, state, binding

    def test_callback_requires_browser_binder_and_is_one_use_after_restart(self):
        _, state, binding = self.create()
        with self.assertRaises(PermissionError):
            self.store.consume(state=state, browser_binding="wrong-browser-binding")
        first = self.open_store().consume(state=state, browser_binding=binding)
        self.assertEqual(first["client_id"], CLIENT)
        self.assertEqual(first["redirect_uri"], REDIRECT)
        self.assertTrue(len(first["nonce"]) >= 32)
        self.assertTrue(len(first["code_verifier"]) >= 43)
        with self.assertRaises(PermissionError):
            self.open_store().consume(state=state, browser_binding=binding)
        with self.store._db() as db:
            rec = db.execute(
                "SELECT state,verifier FROM bff_oidc_transactions").fetchone()
        self.assertEqual(rec[0], "consumed")
        self.assertNotEqual(rec[1], binding)

    def test_old_or_swapped_state_cannot_be_reused(self):
        _, state, binding = self.create()
        _, other, other_binding = self.create()
        with self.assertRaises(PermissionError):
            self.store.consume(state=state, browser_binding=other_binding)
        with self.assertRaises(PermissionError):
            self.store.consume(state=other, browser_binding=binding)
        self.assertTrue(self.store.consume(state=other, browser_binding=other_binding))
        self.assertTrue(self.store.consume(state=state, browser_binding=binding))

    def test_stale_or_malformed_state_fails_closed(self):
        _, state, binding = self.create()
        self.now[0] += 181
        with self.assertRaises(PermissionError):
            self.store.consume(state=state, browser_binding=binding)
        for x, y in ((None, binding), ("x", binding), (state, None),
                     (state, ""), (state, "malformed"),
                     (state + "\u200b", binding),
                     (state, binding + "\u200b"),
                     (state + "\n", binding)):
            with self.subTest(state=x, cookie=y), self.assertRaises(PermissionError):
                self.store.consume(state=x, browser_binding=y)


if __name__ == "__main__":
    unittest.main()
