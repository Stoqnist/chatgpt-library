"""Verification-only offline trust contract for external identity and consent.

The public-key allowlists are local trusted inputs. No account login, OIDC
discovery, browser UI, external network, signing keys or issuance endpoints.
Tests use fictional issuers; a signature is NOT proof of an actual user action.
"""
from __future__ import annotations

import json
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .calendar_approval import APPROVAL_DENIED, _decode

_KID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_SESSION_TYPE = "agency-session-attestation-v1"
_UI_TYPE = "agency-consent-display-attestation-v1"


class PinnedAssertionVerifier:
    """Public-key-only verifier for a precisely scoped external trust root."""

    def __init__(self, *, public_keys: dict, issuer: str, audience: str,
                 assertion_type: str, max_ttl: int, clock=time.time):
        if (not isinstance(public_keys, dict) or not public_keys
                or not isinstance(issuer, str) or not issuer
                or not isinstance(audience, str) or not audience
                or assertion_type not in (_SESSION_TYPE, _UI_TYPE)
                or type(max_ttl) is not int or not 0 < max_ttl <= 3600):
            raise ValueError("pinned trust root and bounded assertion policy required")
        for kid, key in public_keys.items():
            if (not isinstance(kid, str) or not _KID.fullmatch(kid)
                    or not isinstance(key, Ed25519PublicKey)):
                raise ValueError("public-only pinned Ed25519 keys required")
        self._keys = dict(public_keys)
        self._issuer, self._audience = issuer, audience
        self._type, self._max_ttl, self._clock = assertion_type, max_ttl, clock

    def verify(self, token: str) -> dict:
        try:
            if not isinstance(token, str) or len(token) > 4096:
                raise ValueError()
            body, signature = token.split(".")
            claims = json.loads(_decode(body))
            if not isinstance(claims, dict):
                raise ValueError()
            kid = claims.get("kid")
            if kid not in self._keys:
                raise ValueError()
            self._keys[kid].verify(_decode(signature), body.encode("ascii"))
            now = self._clock()
            issued, expires = claims.get("iat"), claims.get("exp")
            if (claims.get("alg") != "EdDSA" or claims.get("typ") != self._type
                    or claims.get("iss") != self._issuer
                    or claims.get("aud") != self._audience
                    or type(issued) not in (int, float)
                    or type(expires) not in (int, float)
                    or not issued <= now < expires
                    or not 0 < expires - issued <= self._max_ttl
                    or not isinstance(claims.get("sub"), str)
                    or not 1 <= len(claims["sub"]) <= 128
                    or not claims["sub"].strip()
                    or not isinstance(claims.get("sid"), str)
                    or not 16 <= len(claims["sid"]) <= 128
                    or not re.fullmatch(r"[A-Za-z0-9_-]+", claims["sid"])):
                raise ValueError()
            return claims
        except (ValueError, TypeError, KeyError, UnicodeError, InvalidSignature):
            raise PermissionError(APPROVAL_DENIED) from None


def session_verifier(*, public_keys, clock=time.time):
    return PinnedAssertionVerifier(
        public_keys=public_keys, issuer="agency-idp-fixture",
        audience="agency-calendar-consent-session",
        assertion_type=_SESSION_TYPE, max_ttl=900, clock=clock)


def consent_display_verifier(*, public_keys, clock=time.time):
    return PinnedAssertionVerifier(
        public_keys=public_keys, issuer="agency-ui-fixture",
        audience="agency-calendar-consent-confirmation",
        assertion_type=_UI_TYPE, max_ttl=90, clock=clock)
