"""Offline Google OIDC protocol primitives. No HTTP client or live login.

Google's HTTPS token exchange and JWKS retrieval MUST be implemented by a
separately reviewed, HTTPS-pinned trusted adapter. Never use JWT-provided
jku/x5u/jwk URLs or accept a decoded but unverified ID token.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import urlencode, urlsplit

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

GOOGLE_AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_ISSUERS = frozenset(("https://accounts.google.com", "accounts.google.com"))
_TOKEN_PART = re.compile(r"[A-Za-z0-9_-]{1,1024}\Z")
_ID_TOKEN_MAX = 8192


@dataclass(frozen=True)
class LoginAttempt:
    authorization_url: str
    state: str
    nonce: str
    code_verifier: str


@dataclass(frozen=True)
class VerifiedGoogleIdentity:
    issuer: str
    subject: str
    audience: str
    expires_at: int


def _base64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode(part: str) -> bytes:
    if not isinstance(part, str) or not _TOKEN_PART.fullmatch(part):
        raise ValueError("invalid token encoding")
    raw = base64.b64decode(part + "=" * (-len(part) % 4),
                           altchars=b"-_", validate=True)
    if _base64url(raw) != part:
        raise ValueError("noncanonical token encoding")
    return raw


def begin_google_login(*, client_id: str, redirect_uri: str) -> LoginAttempt:
    """Construct Authorization Code+PKCE S256 request, no network operations.

    State/nonce/verifier MUST remain in server-owned one-shot state bound to an
    unguessable browser cookie, not a query string, log or public repository.
    """
    if (not isinstance(client_id, str) or not 4 <= len(client_id) <= 256
            or not client_id.isascii() or any(c.isspace() for c in client_id)
            or not isinstance(redirect_uri, str)
            or len(redirect_uri) > 1024):
        raise ValueError("approved OIDC client configuration required")
    url = urlsplit(redirect_uri)
    if (url.scheme != "https" or not url.netloc or url.username or url.password
            or url.fragment or url.query
            or url.path != "/auth/google/callback"
            or url.hostname in ("localhost", "127.0.0.1")
            or url.port is not None):
        raise ValueError("exact HTTPS callback route required")
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = _base64url(hashlib.sha256(verifier.encode("ascii")).digest())
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    return LoginAttempt(GOOGLE_AUTHORIZATION_ENDPOINT + "?" +
                        urlencode(params), state, nonce, verifier)


def verify_google_id_token(*, token: str, trusted_public_keys: dict,
                           client_id: str, expected_nonce: str,
                           now: int | None = None) -> VerifiedGoogleIdentity:
    """Verify a Google RSA-signed ID token with previously trusted JWKS keys.

    Does not fetch Google keys, follow token headers, exchange authorization
    codes or validate a live BFF session. Key freshness remains an integration
    gate. Strict single-audience Google web-client profile in first slice.
    """
    if now is None:
        now = int(time.time())
    try:
        if (not isinstance(token, str) or not 0 < len(token) <= _ID_TOKEN_MAX
                or not isinstance(trusted_public_keys, dict)
                or not trusted_public_keys
                or not isinstance(client_id, str) or not client_id
                or not isinstance(expected_nonce, str)
                or len(expected_nonce) < 16
                or type(now) is not int):
            raise ValueError()
        header_b64, payload_b64, sig_b64 = token.split(".")
        header = json.loads(_decode(header_b64))
        claims = json.loads(_decode(payload_b64))
        if not isinstance(header, dict) or not isinstance(claims, dict):
            raise ValueError()
        kid = header.get("kid")
        if (header.get("alg") != "RS256" or
                not isinstance(kid, str) or kid not in trusted_public_keys
                or not isinstance(trusted_public_keys[kid], rsa.RSAPublicKey)):
            raise ValueError()
        trusted_public_keys[kid].verify(
            _decode(sig_b64),
            (header_b64 + "." + payload_b64).encode("ascii"),
            padding.PKCS1v15(), hashes.SHA256())
        subject = claims.get("sub")
        expires = claims.get("exp")
        issued = claims.get("iat")
        if (claims.get("iss") not in GOOGLE_ISSUERS
                or claims.get("aud") != client_id
                or ("azp" in claims and claims["azp"] != client_id)
                or not isinstance(subject, str) or not 1 <= len(subject) <= 255
                or not subject.strip()
                or type(expires) is not int or type(issued) is not int
                or issued > now + 60 or issued < now - 600
                or expires <= now or expires > now + 7200
                or not isinstance(claims.get("nonce"), str)
                or not hmac.compare_digest(claims["nonce"], expected_nonce)):
            raise ValueError()
        return VerifiedGoogleIdentity(claims["iss"], subject, client_id, expires)
    except (ValueError, TypeError, KeyError, UnicodeError,
            OverflowError, InvalidSignature):
        raise PermissionError("Google identity verification unavailable") from None
