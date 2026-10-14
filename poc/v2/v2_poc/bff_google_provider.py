"""Confidential Google OIDC adapter. Fixed HTTPS trust roots; no token logging.

Fresh discovery and JWKS per exchange deliberately avoid stale-key cache and
rotation ambiguity in this low-volume single-user slice. Never retry a code.
"""
import json
import ssl
import time
from urllib.parse import urlencode
from urllib.request import (Request, build_opener, HTTPSHandler,
                            HTTPRedirectHandler, ProxyHandler)

from cryptography.hazmat.primitives.asymmetric import rsa

from .bff_google_oidc import (_decode, verify_google_id_token,
                              GOOGLE_AUTHORIZATION_ENDPOINT)

DISCOVERY = 'https://accounts.google.com/.well-known/openid-configuration'
TOKEN = 'https://oauth2.googleapis.com/token'
JWKS = 'https://www.googleapis.com/oauth2/v3/certs'


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise PermissionError('Google identity provider unavailable')


def request_json(url, data=None):
    """TLS certificate/hostname verification, bounded body/time, no redirects."""
    if url not in (DISCOVERY, TOKEN, JWKS) or (data is not None) != (url == TOKEN):
        raise PermissionError('Google identity provider unavailable')
    opener = build_opener(ProxyHandler({}), _NoRedirect(),
                          HTTPSHandler(context=ssl.create_default_context()))
    request = Request(url, data=data, headers={'Accept': 'application/json'})
    if data is not None:
        request.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with opener.open(request, timeout=10) as response:
            if response.status != 200 or response.headers.get_content_type() != 'application/json':
                raise ValueError()
            raw = response.read(65537)
            if len(raw) > 65536:
                raise ValueError()
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
    except Exception:
        # Provider errors may contain authorization codes or credentials.
        raise PermissionError('Google identity provider unavailable') from None


class GoogleProvider:
    def __init__(self, *, client_id, client_secret, redirect_uri,
                 transport=request_json, clock=time.time):
        if not isinstance(client_secret, str) or not 1 <= len(client_secret) <= 4096:
            raise ValueError('Google client secret required')
        self.client_id = client_id
        self._secret = client_secret
        self.redirect_uri = redirect_uri
        self._request = transport
        self._clock = clock

    def exchange(self, *, code, transaction):
        try:
            if (not isinstance(code, str) or not 1 <= len(code) <= 4096
                    or not code.isascii() or any(ord(c) < 33 for c in code)
                    or transaction['client_id'] != self.client_id
                    or transaction['redirect_uri'] != self.redirect_uri):
                raise ValueError()
            discovery = self._request(DISCOVERY)
            for name, expected in (
                ('issuer', 'https://accounts.google.com'),
                ('authorization_endpoint', GOOGLE_AUTHORIZATION_ENDPOINT),
                ('token_endpoint', TOKEN), ('jwks_uri', JWKS),
            ):
                if discovery.get(name) != expected:
                    raise ValueError()
            # Validate the full key set before transmitting the one-use code.
            document = self._request(JWKS)
            entries = document['keys']
            if not isinstance(entries, list) or not 1 <= len(entries) <= 20:
                raise ValueError()
            keys = {}
            for entry in entries:
                kid = entry['kid']
                if (entry.get('kty') != 'RSA' or entry.get('alg') != 'RS256'
                        or entry.get('use') != 'sig' or not isinstance(kid, str)
                        or not 1 <= len(kid) <= 256 or kid in keys
                        or any(k in entry for k in ('d', 'p', 'q'))):
                    raise ValueError()
                n = int.from_bytes(_decode(entry['n']), 'big')
                e = int.from_bytes(_decode(entry['e']), 'big')
                if not 2048 <= n.bit_length() <= 4096 or e != 65537:
                    raise ValueError()
                keys[kid] = rsa.RSAPublicNumbers(e, n).public_key()
            response = self._request(TOKEN, urlencode({
                'code': code, 'client_id': self.client_id,
                'client_secret': self._secret, 'redirect_uri': self.redirect_uri,
                'grant_type': 'authorization_code',
                'code_verifier': transaction['code_verifier'],
            }).encode('ascii'))
            # Discard access/refresh tokens: this adapter grants login only.
            return verify_google_id_token(
                token=response['id_token'], trusted_public_keys=keys,
                client_id=self.client_id, expected_nonce=transaction['nonce'],
                now=int(self._clock()))
        except Exception:
            raise PermissionError('Google login unavailable') from None
