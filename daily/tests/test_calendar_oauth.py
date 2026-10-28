"""Fictional authorization-code/PKCE tests; Google is never contacted."""
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_oauth import (
    AUTH_URL, TOKEN_URL, CALLBACK_URL, FREEBUSY_SCOPE,
    CalendarOAuthError, begin_calendar_auth, parse_calendar_callback,
    exchange_calendar_code,
)

CLIENT = "1234-test.apps.googleusercontent.com"
SECRET = "GOCSPX-not-a-real-secret-for-tests"
CODE = "fictional-single-use-code"
VERIFIER = "x" * 64
STATE = "fictional-random-session-state"
RESPONSE = {
    "scope": FREEBUSY_SCOPE, "token_type": "Bearer", "expires_in": 3599,
    "access_token": "fictional-access-token-value",
    "refresh_token": "fictional-refresh-token-value",
}


class Response:
    def __init__(self, data):
        self.data = io.BytesIO(data)

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        return False

    def read(self, limit):
        return self.data.read(limit)


class Transport:
    def __init__(self, payload=None, error=None):
        self.payload = RESPONSE if payload is None else payload
        self.error = error
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append((request, timeout))
        if self.error:
            raise self.error
        raw = (self.payload if isinstance(self.payload, bytes)
               else json.dumps(self.payload).encode())
        return Response(raw)


class CalendarOAuthTest(unittest.TestCase):
    def test_authorization_is_single_scope_pkce_and_exact_callback(self):
        url, state, verifier = begin_calendar_auth(CLIENT)
        parsed = urllib.parse.urlparse(url)
        self.assertEqual(parsed.scheme + "://" + parsed.netloc + parsed.path, AUTH_URL)
        q = urllib.parse.parse_qs(parsed.query)
        self.assertEqual(q["client_id"], [CLIENT])
        self.assertEqual(q["redirect_uri"], [CALLBACK_URL])
        self.assertEqual(q["scope"], [FREEBUSY_SCOPE])
        self.assertEqual(q["response_type"], ["code"])
        self.assertEqual(q["access_type"], ["offline"])
        self.assertEqual(q["prompt"], ["consent"])
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertNotIn("client_secret", q)
        self.assertNotIn("refresh_token", q)
        self.assertNotIn(verifier, url)
        expected = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(q["code_challenge"], [expected])
        self.assertEqual(q["state"], [state])
        self.assertGreaterEqual(len(state), 32)

    def test_new_authorizations_use_independent_state_and_verifier(self):
        first = begin_calendar_auth(CLIENT)
        second = begin_calendar_auth(CLIENT)
        self.assertNotEqual(first[1], second[1])
        self.assertNotEqual(first[2], second[2])

    def test_callback_requires_exact_one_state(self):
        q = urllib.parse.urlencode({"state": STATE, "code": CODE})
        self.assertEqual(parse_calendar_callback(q, STATE), CODE)
        for bad in (
            "", "code=ok", "state=wrong&code=ok",
            f"state={STATE}&state={STATE}&code=ok",
            f"state={STATE}&code=one&code=two",
            f"state={STATE}&error=access_denied",
            f"state={STATE}&error=access_denied&code=ok",
            f"state={STATE}&code=",
        ):
            with self.subTest(bad=bad), self.assertRaises(CalendarOAuthError):
                parse_calendar_callback(bad, STATE)

    def test_exchange_is_single_fixed_endpoint_without_excess_scopes(self):
        transport = Transport()
        output = exchange_calendar_code(
            CLIENT, SECRET, CODE, VERIFIER, opener=transport)
        self.assertEqual(output["scope"], FREEBUSY_SCOPE)
        self.assertEqual(output["refresh_token"], RESPONSE["refresh_token"])
        self.assertEqual(len(transport.requests), 1)
        req, timeout = transport.requests[0]
        self.assertEqual(req.full_url, TOKEN_URL)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(timeout, 10)
        self.assertEqual(req.headers["Content-type"], "application/x-www-form-urlencoded")
        body = urllib.parse.parse_qs(req.data.decode())
        self.assertEqual(body["client_id"], [CLIENT])
        self.assertEqual(body["client_secret"], [SECRET])
        self.assertEqual(body["code"], [CODE])
        self.assertEqual(body["redirect_uri"], [CALLBACK_URL])
        self.assertEqual(body["grant_type"], ["authorization_code"])
        self.assertEqual(body["code_verifier"], [VERIFIER])

    def test_token_scope_missing_or_broader_fails_closed(self):
        altered = [
            {**RESPONSE, "scope": "https://www.googleapis.com/auth/calendar"},
            {**RESPONSE, "scope": FREEBUSY_SCOPE + " openid"},
            {**RESPONSE, "scope": ""},
            {**RESPONSE, "scope": None},
            {**RESPONSE, "token_type": "Bearerx"},
            {**RESPONSE, "token_type": ""},
            {**RESPONSE, "refresh_token": ""},
            {**RESPONSE, "expires_in": 0},
            {**RESPONSE, "expires_in": True},
            {**RESPONSE, "expires_in": "3600"},
        ]
        for response in altered:
            with self.subTest(value=response), self.assertRaises(CalendarOAuthError):
                exchange_calendar_code(CLIENT, SECRET, CODE, VERIFIER,
                                       opener=Transport(response))

    def test_exchange_network_error_never_leaks_code_or_secret(self):
        tr = Transport(error=urllib.error.URLError("secret " + SECRET))
        with self.assertRaises(CalendarOAuthError) as caught:
            exchange_calendar_code(CLIENT, SECRET, CODE, VERIFIER, opener=tr)
        self.assertNotIn(SECRET, str(caught.exception))
        self.assertNotIn(CODE, str(caught.exception))

    def test_malformed_and_oversized_token_responses_fail(self):
        for raw in (b"[]", b"not-json", b"{" + b"x" * 16384):
            with self.subTest(length=len(raw)), self.assertRaises(CalendarOAuthError):
                exchange_calendar_code(CLIENT, SECRET, CODE, VERIFIER,
                                       opener=Transport(raw))

    def test_invalid_client_or_secret_does_not_touch_network(self):
        tr = Transport()
        for client, secret, verifier in (
            ("evil.example", SECRET, VERIFIER),
            (CLIENT, "bad\nsecret", VERIFIER),
            (CLIENT, SECRET, "short"),
        ):
            with self.subTest(client=client, secret=secret), self.assertRaises(ValueError):
                exchange_calendar_code(client, secret, CODE, verifier, opener=tr)
        self.assertEqual(tr.requests, [])

    def test_callbacks_reject_invalid_values(self):
        for query in (f"state={STATE}&code=%0A", "?" * 9000,
                      f"state={STATE}&code=%20"):
            with self.subTest(query=query[:80]), self.assertRaises(CalendarOAuthError):
                parse_calendar_callback(query, STATE)


if __name__ == "__main__":
    unittest.main()
