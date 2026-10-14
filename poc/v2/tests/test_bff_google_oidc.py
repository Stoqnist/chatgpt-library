"""Fictional Google OIDC login/RS256 JWT contract, fully offline."""
import base64
import hashlib
import json
import unittest
from urllib.parse import parse_qs, urlsplit

from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes

from v2_poc.bff_google_oidc import (
    GOOGLE_AUTHORIZATION_ENDPOINT, begin_google_login,
    verify_google_id_token,
)

NOW = 1_000_000
CLIENT = "synthetic-google-login-client.apps.googleusercontent.com"
CALLBACK = "https://agency.example.invalid/auth/google/callback"


def b64(obj):
    return base64.urlsafe_b64encode(json.dumps(
        obj, sort_keys=True, separators=(",", ":")).encode()).decode().rstrip("=")


class GoogleOIDCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.other_signer = rsa.generate_private_key(
            public_exponent=65537, key_size=2048)

    def setUp(self):
        self.attempt = begin_google_login(client_id=CLIENT, redirect_uri=CALLBACK)

    def signed(self, claims=None, header=None, signer=None):
        defaults = {
            "iss": "https://accounts.google.com", "aud": CLIENT,
            "sub": "fictional-google-oidc-subject", "exp": NOW + 300,
            "iat": NOW, "nonce": self.attempt.nonce,
        }
        defaults.update(claims or {})
        header_data = {"alg": "RS256", "kid": "synthetic-google-key"}
        header_data.update(header or {})
        body = b64(header_data) + "." + b64(defaults)
        signature = (signer or self.signer).sign(
            body.encode(), padding.PKCS1v15(), hashes.SHA256())
        return body + "." + base64.urlsafe_b64encode(
            signature).decode().rstrip("=")

    def verify(self, token, keys=None):
        return verify_google_id_token(
            token=token,
            trusted_public_keys=keys if keys is not None else
            {"synthetic-google-key": self.signer.public_key()},
            client_id=CLIENT, expected_nonce=self.attempt.nonce, now=NOW)

    def test_code_pkce_s256_and_one_time_state_inputs_are_unpredictable(self):
        one = self.attempt
        two = begin_google_login(client_id=CLIENT, redirect_uri=CALLBACK)
        self.assertNotEqual(one.state, two.state)
        self.assertNotEqual(one.nonce, two.nonce)
        self.assertNotEqual(one.code_verifier, two.code_verifier)
        url = urlsplit(one.authorization_url)
        self.assertEqual(url.scheme + "://" + url.netloc + url.path,
                         GOOGLE_AUTHORIZATION_ENDPOINT)
        params = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.assertEqual(params["redirect_uri"], CALLBACK)
        self.assertEqual(params["client_id"], CLIENT)
        self.assertEqual(params["response_type"], "code")
        self.assertEqual(params["scope"], "openid email profile")
        self.assertEqual(params["state"], one.state)
        self.assertEqual(params["nonce"], one.nonce)
        self.assertEqual(params["code_challenge_method"], "S256")
        expected = base64.urlsafe_b64encode(hashlib.sha256(
            one.code_verifier.encode()).digest()).decode().rstrip("=")
        self.assertEqual(params["code_challenge"], expected)
        self.assertNotIn(one.code_verifier, one.authorization_url)

    def test_rejects_unknown_insecure_or_open_redirect_callbacks(self):
        for redirect in (
            "http://agency.example.invalid/auth/google/callback",
            "https://evil.invalid/not-callback",
            "https://agency.example.invalid/auth/google/callback?next=https://bad.invalid",
            "https://agency.example.invalid/auth/google/callback#frag",
            "https://agency.example.invalid:8443/auth/google/callback",
            "https://localhost/auth/google/callback",
            "https://a:b@agency.example.invalid/auth/google/callback",
        ):
            with self.subTest(redirect=redirect), self.assertRaises(ValueError):
                begin_google_login(client_id=CLIENT, redirect_uri=redirect)

    def test_trusted_google_rsa_signature_and_nonce_pass(self):
        v = self.verify(self.signed())
        self.assertEqual(v.subject, "fictional-google-oidc-subject")
        self.assertEqual(v.audience, CLIENT)
        self.assertEqual(v.expires_at, NOW + 300)

    def test_wrong_issuer_audience_nonce_claims_or_time_denied(self):
        cases = (
            {"iss": "https://evil.invalid"},
            {"aud": "other-google-client"},
            {"aud": [CLIENT, "other"]},
            {"azp": "different-client"},
            {"nonce": "unexpected-nonce-12345678"},
            {"sub": ""},
            {"exp": NOW},
            {"exp": NOW + 10000},
            {"iat": NOW + 61},
            {"iat": NOW - 601},
            {"exp": True},
        )
        for change in cases:
            with self.subTest(change=change), self.assertRaises(PermissionError):
                self.verify(self.signed(claims=change))

    def test_signer_kid_algorithm_and_payload_tampering_denied(self):
        cases = (
            (self.signed(header={"kid": "unknown"}), None),
            (self.signed(header={"alg": "HS256"}), None),
            (self.signed(signer=self.other_signer), None),
            (self.signed(), {"synthetic-google-key": self.other_signer.public_key()}),
        )
        for token, keys in cases:
            with self.subTest(token=token[:15]), self.assertRaises(PermissionError):
                self.verify(token, keys)
        token = self.signed()
        a, b, c = token.split(".")
        wrong = b64({"iss": "https://accounts.google.com",
                     "aud": CLIENT, "iat": NOW,
                     "exp": NOW + 300, "nonce": self.attempt.nonce,
                     "sub": "forged"})
        with self.assertRaises(PermissionError):
            self.verify(a + "." + wrong + "." + c)
        for token in ("", "abc.def", "abc.def.ghi.jkl", "x" * 10000):
            with self.subTest(token=token), self.assertRaises(PermissionError):
                self.verify(token)

    def test_no_live_discovery_or_real_key_trust_is_claimed(self):
        with self.assertRaises(PermissionError):
            self.verify(self.signed(), {})
        with self.assertRaises(PermissionError):
            self.verify(self.signed(), {"synthetic-google-key": "not-a-public-key"})


if __name__ == "__main__":
    unittest.main()
