"""HTTP flow using real RSA signatures and a fictional Google transport."""
import base64
import hashlib
import io
import json
import re
import tempfile
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit
from unittest.mock import patch
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from v2_poc.bff_browser_consent import OfflineBrowserConsent
from v2_poc.bff_google_login_state import OfflineLoginState
from v2_poc.bff_google_oidc import GOOGLE_AUTHORIZATION_ENDPOINT
from v2_poc.bff_google_provider import GoogleProvider, DISCOVERY, JWKS, TOKEN, request_json
from v2_poc.bff_http import GoogleLoginApplication, configured_application

ORIGIN = 'https://agency.example.invalid'
CLIENT = 'fictional-client.apps.googleusercontent.com'
NOW = 1000000


def b64(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip('=')


class HTTPLoginTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = self.temp.name + '/sessions.sqlite'
        self.now, self.calls, self.changes = NOW, [], {}
        self.kid, self.fail = 'fixture-key', None
        self.store = OfflineBrowserConsent(self.path, oidc_client_id=CLIENT, trusted_origin=ORIGIN, clock=lambda: self.now)
        self.login = OfflineLoginState(self.path, client_id=CLIENT, redirect_uri=ORIGIN + '/auth/google/callback', clock=lambda: self.now)
        self.provider = GoogleProvider(client_id=CLIENT, client_secret='fixture-secret', redirect_uri=self.login.redirect_uri, transport=self.transport, clock=lambda: self.now)
        self.app = GoogleLoginApplication(store=self.store, login=self.login, provider=self.provider, origin=ORIGIN, allowed_subject='fictional-subject')

    def transport(self, url, data=None):
        self.calls.append(url)
        if url == self.fail:
            raise TimeoutError('private provider response')
        if url == DISCOVERY:
            return dict(issuer='https://accounts.google.com', token_endpoint=TOKEN, jwks_uri=JWKS, authorization_endpoint=GOOGLE_AUTHORIZATION_ENDPOINT)
        if url == JWKS:
            n = self.key.public_key().public_numbers().n
            return {'keys': [{'kid': self.kid, 'kty': 'RSA', 'use': 'sig', 'alg': 'RS256', 'n': b64(n.to_bytes(256, 'big')), 'e': 'AQAB'}]}
        self.assertEqual(url, TOKEN)
        params = parse_qs(data.decode())
        for k, v in {'client_secret': 'fixture-secret', 'grant_type': 'authorization_code', 'redirect_uri': self.login.redirect_uri, 'client_id': CLIENT, 'code': 'fictional-code'}.items():
            self.assertEqual(params[k], [v])
        self.assertEqual(b64(hashlib.sha256(params['code_verifier'][0].encode()).digest()), self.authorization['code_challenge'][0])
        claims = dict(iss='https://accounts.google.com', aud=CLIENT, sub='fictional-subject', nonce=self.authorization['nonce'][0], iat=self.now, exp=self.now + 300)
        claims.update(self.changes)
        payload = b64(json.dumps({'alg': 'RS256', 'kid': self.kid}).encode()) + '.' + b64(json.dumps(claims).encode())
        signature = self.key.sign(payload.encode(), padding.PKCS1v15(), hashes.SHA256())
        return {'id_token': payload + '.' + b64(signature), 'access_token': 'never-expose-this'}

    def call(self, path, *, method='GET', cookies='', data='', **extra):
        parsed = urlsplit(path)
        env = {'PATH_INFO': parsed.path, 'QUERY_STRING': parsed.query, 'REQUEST_METHOD': method, 'HTTP_HOST': urlsplit(ORIGIN).netloc, 'wsgi.url_scheme': 'https', 'HTTP_COOKIE': cookies, 'CONTENT_TYPE': 'application/x-www-form-urlencoded', 'CONTENT_LENGTH': str(len(data)), 'wsgi.input': io.BytesIO(data.encode()), 'HTTP_ORIGIN': ORIGIN}
        env.update(extra)
        result = {}
        def start(status, headers):
            result.update(status=status, headers=headers)
        result['body'] = b''.join(self.app(env, start)).decode()
        return result

    def start(self):
        result = self.call('/auth/google/login')
        self.assertEqual(result['status'], '303 See Other')
        headers = dict(result['headers'])
        self.authorization = parse_qs(urlsplit(headers['Location']).query)
        self.binder = headers['Set-Cookie'].split(';')[0]
        self.callback = '/auth/google/callback?' + urlencode({'state': self.authorization['state'][0], 'code': 'fictional-code'})

    def sign_in(self):
        self.start()
        result = self.call(self.callback, cookies=self.binder)
        self.assertEqual(result['status'], '303 See Other')
        value = next(v for k, v in result['headers'] if k == 'Set-Cookie' and v.startswith('__Host-agency_session='))
        for flag in ('Secure', 'HttpOnly', 'SameSite=Lax', 'Path=/'):
            self.assertIn(flag, value)
        self.assertNotIn('Domain=', value)
        return value.split(';')[0]

    def test_complete_login_logout_replay_and_pending_consent_revocation(self):
        self.assertEqual(self.call('/')['status'], '403 Forbidden')
        session = self.sign_in()
        self.assertEqual(self.calls, [DISCOVERY, JWKS, TOKEN])
        page = self.call('/', cookies=session)
        self.assertEqual(page['status'], '200 OK')
        self.assertNotIn('fictional-subject', page['body'])
        csrf = re.search('name="csrf" value="([a-f0-9]+)"', page['body'])[1]
        challenge = self.store.begin_consent(session_token=session.split('=', 1)[1], preview={'summary': 'Fictional'}, plan_sha256='a' * 64)
        out = self.call('/auth/logout', method='POST', cookies=session, data=urlencode({'csrf': csrf}))
        self.assertEqual(out['status'], '200 OK')
        self.assertIn('Max-Age=0', str(out['headers']))
        self.assertEqual(self.call('/', cookies=session)['status'], '403 Forbidden')
        self.assertEqual(self.call(self.callback, cookies=self.binder)['status'], '403 Forbidden')
        self.assertEqual(self.calls.count(TOKEN), 1)
        with self.store._db() as db:
            self.assertEqual(db.execute('SELECT state FROM bff_consent_challenges WHERE challenge_id=?', (challenge['challenge_id'],)).fetchone()[0], 'revoked')

    def test_wrong_browser_duplicate_state_never_exchange(self):
        self.start()
        self.assertEqual(self.call(self.callback)['status'], '403 Forbidden')
        self.assertEqual(self.call(self.callback + '&state=x', cookies=self.binder)['status'], '403 Forbidden')
        self.assertEqual(self.calls, [])

    def test_provider_timeout_consumes_state_no_leak_or_retry(self):
        self.start()
        self.fail = TOKEN
        result = self.call(self.callback, cookies=self.binder)
        self.assertEqual(result['status'], '403 Forbidden')
        self.assertNotIn('private', result['body'])
        self.assertEqual(self.call(self.callback, cookies=self.binder)['status'], '403 Forbidden')
        self.assertEqual(self.calls.count(TOKEN), 1)

    def test_signed_wrong_claims_and_other_account_denied(self):
        for changes in ({'sub': 'other'}, {'aud': 'other'}, {'nonce': 'wrong'}, {'exp': NOW - 1}, {'iss': 'evil'}):
            with self.subTest(changes=changes):
                self.changes = changes
                self.start()
                result = self.call(self.callback, cookies=self.binder)
                self.assertEqual(result['status'], '403 Forbidden')
                self.assertNotIn('__Host-agency_session=', str(result['headers']))

    def test_rotation_refetches_keys(self):
        self.sign_in()
        self.kid = 'rotated-key'
        self.sign_in()
        self.assertEqual(self.calls.count(JWKS), 2)

    def test_logout_requires_origin_csrf_post(self):
        session = self.sign_in()
        for options in ({'method': 'GET'}, {'method': 'POST', 'data': 'csrf=wrong'}, {'method': 'POST', 'HTTP_ORIGIN': 'https://evil.invalid'}):
            self.assertNotEqual(self.call('/auth/logout', cookies=session, **options)['status'], '200 OK')
            self.assertEqual(self.call('/', cookies=session)['status'], '200 OK')

    def test_restart_expiry_headers_host_https_and_duplicates(self):
        session = self.sign_in()
        self.app.store = OfflineBrowserConsent(self.path, oidc_client_id=CLIENT, trusted_origin=ORIGIN, clock=lambda: self.now)
        self.assertEqual(self.call('/', cookies=session)['status'], '200 OK')
        for extra in ({'HTTP_HOST': 'evil.invalid'}, {'wsgi.url_scheme': 'http', 'HTTP_X_FORWARDED_PROTO': 'https'}):
            self.assertEqual(self.call('/', cookies=session, **extra)['status'], '403 Forbidden')
        self.assertEqual(self.call('/', cookies=session + '; ' + session)['status'], '403 Forbidden')
        self.assertEqual(self.call('/calendar/execute', cookies=session)['status'], '503 Service Unavailable')
        self.now += 301
        self.assertEqual(self.call('/', cookies=session)['status'], '403 Forbidden')
        self.assertEqual(self.call('/', HTTP_AUTHORIZATION='Bearer forged', HTTP_CF_ACCESS_AUTHENTICATED_USER_EMAIL='owner@example.invalid')['status'], '403 Forbidden')

    def test_unconfigured_inert_and_untrusted_transport_urls(self):
        with patch.dict('os.environ', {}, clear=True):
            self.assertEqual(configured_application().__module__, 'v2_poc.bff_offline')
        for url in ('http://accounts.google.com', 'https://evil.invalid', TOKEN + '?code=x'):
            with self.assertRaises(PermissionError):
                request_json(url)

    def test_discovery_substitution_and_invalid_keys_before_exchange(self):
        original = self.provider._request
        for replacement in ({'jwks_uri': 'https://evil.invalid/keys'}, {'keys': []}):
            def substituted(url, data=None):
                result = original(url, data)
                if (url == DISCOVERY and 'jwks_uri' in replacement) or (url == JWKS and 'keys' in replacement):
                    result.update(replacement)
                return result
            self.provider._request = substituted
            self.start()
            self.assertEqual(self.call(self.callback, cookies=self.binder)['status'], '403 Forbidden')
            self.assertNotIn(TOKEN, self.calls)

    def test_socket_http_login_logout_with_explicit_trusted_tls_proxy(self):
        import threading
        import urllib.request
        import urllib.error
        from wsgiref.simple_server import make_server
        from v2_poc.bff_offline import _NoAccessLog
        self.app.proxy = '127.0.0.1'
        server = make_server('127.0.0.1', 0, self.app, handler_class=_NoAccessLog)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args):
                return None
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        def request(path, cookie='', data=None):
            req = urllib.request.Request('http://127.0.0.1:' + str(server.server_port) + path,
                data=data, headers={'Host': urlsplit(ORIGIN).netloc,
                'X-Forwarded-Proto': 'https', 'Cookie': cookie, 'Origin': ORIGIN,
                'Content-Type': 'application/x-www-form-urlencoded'})
            try:
                response = opener.open(req, timeout=3)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                return response.status, response.headers, response.read().decode()
        try:
            self.assertEqual(request('/')[0], 403)
            status, headers, _ = request('/auth/google/login')
            self.assertEqual(status, 303)
            self.authorization = parse_qs(urlsplit(headers['Location']).query)
            binder = headers['Set-Cookie'].split(';')[0]
            callback = '/auth/google/callback?' + urlencode({'state': self.authorization['state'][0], 'code': 'fictional-code'})
            status, headers, _ = request(callback, binder)
            self.assertEqual(status, 303)
            session = next(v.split(';')[0] for v in headers.get_all('Set-Cookie') if v.startswith('__Host-agency_session='))
            status, _, body = request('/', session)
            self.assertEqual(status, 200)
            csrf = re.search('name="csrf" value="([a-f0-9]+)"', body)[1]
            self.assertEqual(request('/auth/logout', session, urlencode({'csrf': csrf}).encode())[0], 200)
            self.assertEqual(request('/', session)[0], 403)
        finally:
            server.shutdown()
            worker.join(timeout=3)
            server.server_close()
