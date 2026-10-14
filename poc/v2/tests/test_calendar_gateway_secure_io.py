"""Offline secure vault + Google HTTP transport tests, no network or secrets."""
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
import urllib.error
from urllib.parse import parse_qs, urlsplit

from v2_poc.calendar_gateway import READ_FIELDS
from v2_poc.calendar_gateway_oauth import OfflineOAuth
from v2_poc.calendar_gateway_transport import (
    GoogleHTTPS, ProviderReadUnavailable, TOKEN_URL, CALENDAR_API, _NoRedirects,
)
from v2_poc.calendar_gateway_vault import EncryptedFileVault, VaultUnavailable


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.dir = Path(self.temp.name)
        os.chmod(self.dir, 0o700)
        self.file = self.dir / "calendar-token.enc"
        self.key = b"\x01" * 32
        self.vault = EncryptedFileVault(self.file, key=self.key)
        self.item = {"refresh_token": "fictional-refresh-token",
                     "scopes": ["calendar.scope.test"]}

    def test_encrypted_atomic_roundtrip_file_mode_and_restart(self):
        self.assertIsNone(self.vault.load())
        self.vault.save(self.item)
        raw = self.file.read_bytes()
        self.assertNotIn(self.item["refresh_token"].encode(), raw)
        self.assertEqual(stat.S_IMODE(self.file.stat().st_mode), 0o600)
        resumed = EncryptedFileVault(self.file, key=self.key)
        self.assertEqual(resumed.load(), self.item)
        updated = {"refresh_token": "rotated-private-token", "scopes": []}
        resumed.save(updated)
        self.assertEqual(self.vault.load(), updated)
        self.assertNotIn(b"rotated-private-token", self.file.read_bytes())
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()),
                         ["calendar-token.enc"])

    def test_tampered_blob_wrong_key_and_corruption_fail_closed(self):
        self.vault.save(self.item)
        with self.assertRaises(VaultUnavailable):
            EncryptedFileVault(self.file, key=b"\x02" * 32).load()
        original = json.loads(self.file.read_text())
        original["ciphertext"] = original["ciphertext"][:-4] + "AAAA"
        self.file.write_text(json.dumps(original))
        with self.assertRaises(VaultUnavailable):
            self.vault.load()
        self.file.write_text("not valid json")
        with self.assertRaises(VaultUnavailable):
            self.vault.load()

    def test_reject_weak_key_world_readable_file_and_directory(self):
        with self.assertRaises(ValueError):
            EncryptedFileVault(self.file, key=b"short")
        self.vault.save(self.item)
        os.chmod(self.file, 0o644)
        with self.assertRaises(VaultUnavailable):
            self.vault.load()
        with self.assertRaises(VaultUnavailable):
            self.vault.save(self.item)
        os.chmod(self.file, 0o600)
        os.chmod(self.dir, 0o755)
        with self.assertRaises(VaultUnavailable):
            self.vault.load()
        with self.assertRaises(VaultUnavailable):
            self.vault.save(self.item)

    def test_symlink_cannot_be_used_for_vault(self):
        secret = self.dir / "unrelated"
        secret.write_text("unmodified")
        self.file.symlink_to(secret)
        with self.assertRaises(VaultUnavailable):
            self.vault.save(self.item)
        with self.assertRaises(VaultUnavailable):
            self.vault.load()
        self.assertEqual(secret.read_text(), "unmodified")

    def test_oauth_uses_encrypted_vault_without_manual_renewal(self):
        calls = []
        scope = "https://www.googleapis.com/auth/calendar.events.owned"
        def exchange(form):
            calls.append({k: v for k, v in form.items()
                          if k not in {"client_secret", "code_verifier",
                                      "refresh_token", "code"}})
            if form["grant_type"] == "authorization_code":
                return {"refresh_token": "long-lived-private-refresh",
                        "scope": scope}
            return {"access_token": "short-lived-access",
                    "expires_in": 3600}
        clock = [1_000_000]
        def client():
            return OfflineOAuth(
                client_id="synthetic-app", client_secret="synthetic-secret",
                redirect_uri="https://example.invalid/return", scopes=[scope],
                exchange=exchange, vault=self.vault, clock=lambda: clock[0])
        broker = client()
        state = parse_qs(urlsplit(broker.authorization_url()).query)["state"][0]
        broker.complete(state=state, code="fictional-authorization-code")
        self.assertNotIn(b"long-lived-private-refresh", self.file.read_bytes())
        self.assertEqual(broker.access_token(), "short-lived-access")
        self.assertEqual(broker.access_token(), "short-lived-access")
        self.assertEqual(len(calls), 2)
        clock[0] += 3601
        self.assertEqual(client().access_token(), "short-lived-access")
        self.assertEqual(len(calls), 3)


class FakeResponse:
    def __init__(self, data, status=200):
        self.data = data
        self.status = status
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.data[:size]


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.result = {"id": "ag0123456789abcdef", "status": "confirmed",
                       "start": {"dateTime": "2026-10-20T10:00:00+02:00"},
                       "end": {"dateTime": "2026-10-20T10:30:00+02:00"},
                       "extendedProperties": {"private": {"agencyOp": "mock"}}}
        self.error = None
        self.status = 200
        def open_request(req, *, timeout):
            self.requests.append((req, timeout))
            if self.error:
                raise self.error
            return FakeResponse(json.dumps(self.result).encode(), self.status)
        self.client = GoogleHTTPS(open_request=open_request)

    def test_only_exact_id_selected_fields_fixed_google_host(self):
        event_id = "ag0123456789abcdef"
        actual = self.client.read_event(
            calendar_id="private+agency@example.com", event_id=event_id,
            fields=READ_FIELDS, access_token="synthetic-token")
        self.assertEqual(actual["id"], event_id)
        req, timeout = self.requests[-1]
        self.assertEqual(timeout, 10)
        self.assertEqual(req.get_method(), "GET")
        self.assertTrue(req.full_url.startswith(CALENDAR_API))
        self.assertIn("private%2Bagency%40example.com", req.full_url)
        self.assertEqual(parse_qs(urlsplit(req.full_url).query)["fields"],
                         [READ_FIELDS])
        self.assertEqual(req.get_header("Authorization"),
                         "Bearer synthetic-token")
        self.assertNotIn("synthetic-token", req.full_url)

    def test_reject_bad_id_credential_calendar_or_field_expansion(self):
        kwargs = {"calendar_id": "test-calendar", "event_id": "ag0123456789abcdef",
                  "fields": READ_FIELDS, "access_token": "synthetic"}
        for replace in ({"event_id": "test/../../../events"},
                        {"event_id": "abcd*invalid"},
                        {"fields": "id,description,attendees"},
                        {"calendar_id": ""},
                        {"access_token": ""}):
            with self.subTest(replace=replace):
                with self.assertRaises(ValueError):
                    self.client.read_event(**{**kwargs, **replace})
        self.assertEqual(self.requests, [])

    def test_token_exchange_only_approved_endpoint_and_grant(self):
        result = self.client.exchange({"grant_type": "refresh_token",
                                       "client_id": "mock-client",
                                       "refresh_token": "synthetic-refresh"})
        self.assertEqual(result, self.result)
        req, _ = self.requests[0]
        self.assertEqual(req.full_url, TOKEN_URL)
        self.assertEqual(req.get_method(), "POST")
        self.assertIn(b"grant_type=refresh_token", req.data)
        with self.assertRaises(ValueError):
            self.client.exchange({"grant_type": "password", "username": "no"})
        self.assertEqual(len(self.requests), 1)

    def test_network_error_and_malformed_or_oversized_response_fail_closed(self):
        self.error = urllib.error.URLError("sensitive-internal-url")
        with self.assertRaises(ProviderReadUnavailable) as ex:
            self.client.exchange({"grant_type": "refresh_token"})
        self.assertNotIn("sensitive-internal-url", str(ex.exception))
        self.error = None
        self.status = 404
        with self.assertRaises(ProviderReadUnavailable):
            self.client.read_event(
                calendar_id="c", event_id="ag0123456789abcdef",
                fields=READ_FIELDS, access_token="private")
        self.status = 200
        self.result = ["not-a-dict"]
        with self.assertRaises(ProviderReadUnavailable):
            self.client.exchange({"grant_type": "refresh_token"})

    def test_redirect_handler_refuses_any_relocation(self):
        handler = _NoRedirects()
        self.assertIsNone(handler.redirect_request(
            None, None, 302, "Found", {}, "https://untrusted.invalid/"))

if __name__ == "__main__":
    unittest.main()
