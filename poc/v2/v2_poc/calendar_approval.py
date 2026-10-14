"""Offline-only Ed25519 verification of exact Calendar approval proofs.

The Gateway receives only a configured public verification-key ring. Real
authenticated user consent and the trust distribution of public keys remain
external deployment requirements. HMAC approval proofs are not accepted.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

APPROVAL_DENIED = "calendar approval unavailable"
APPROVAL_ACTION = "calendar.event.create"
_APPROVAL_AUDIENCE = "agency-calendar-approval"
_APPROVAL_TYPE = "agency-calendar-approval-v1"
_KEY_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(text: str) -> bytes:
    if not isinstance(text, str) or not text or not text.isascii():
        raise ValueError()
    data = base64.b64decode(text + "=" * (-len(text) % 4),
                            altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(data).decode("ascii").rstrip("=") != text:
        raise ValueError()
    return data


def plan_digest(plan: dict) -> str:
    """Bind approval to the entire canonical Calendar planner result."""
    return hashlib.sha256(_canonical(plan)).hexdigest()


class OfflineApprovalVerifier:
    """Public-key-only verifier for one externally authorized Calendar intent.

    Key IDs are explicit and pinned in a trusted local configuration. This
    cannot fetch signing keys from tokens, mint approval signatures, or prove
    a real human approved an event.
    """

    def __init__(self, *, verification_keys: dict,
                 issuer="agency-calendar-consent", clock=time.time):
        if not isinstance(verification_keys, dict) or not verification_keys:
            raise ValueError("nonempty public verification key ring required")
        for kid, public in verification_keys.items():
            if (not isinstance(kid, str) or not _KEY_ID.fullmatch(kid)
                    or not isinstance(public, Ed25519PublicKey)):
                raise ValueError("approval keys must be Ed25519 public keys")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("approval issuer is required")
        self._keys = dict(verification_keys)
        self._issuer = issuer
        self._clock = clock

    def verify(self, proof: str, *, expected_row: dict) -> str:
        """Return (receipt ID, signing key ID) for a valid exact-plan proof."""
        try:
            if not isinstance(proof, str) or len(proof) > 4096:
                raise ValueError()
            body, signature = proof.split(".")
            claims = json.loads(_decode(body))
            if not isinstance(claims, dict):
                raise ValueError()
            kid = claims.get("kid")
            if not isinstance(kid, str) or kid not in self._keys:
                raise ValueError()
            if claims.get("alg") != "EdDSA" or claims.get("typ") != _APPROVAL_TYPE:
                raise ValueError()
            self._keys[kid].verify(_decode(signature), body.encode("ascii"))
            now = self._clock()
            approval_id = claims.get("jti")
            subject = claims.get("sub")
            if (claims.get("iss") != self._issuer
                    or claims.get("aud") != _APPROVAL_AUDIENCE
                    or claims.get("action") != APPROVAL_ACTION
                    or claims.get("decision") != "approved"
                    or claims.get("calendar_id") != expected_row["calendar_id"]
                    or claims.get("operation_id") != expected_row["operation_id"]
                    or claims.get("event_id") != expected_row["event_id"]
                    or claims.get("plan_sha256") != plan_digest(expected_row["plan"])
                    or not isinstance(approval_id, str)
                    or not 16 <= len(approval_id) <= 128
                    or not approval_id.isascii()
                    or not all(c.isalnum() or c in "-_" for c in approval_id)
                    or not isinstance(subject, str) or not subject.strip()
                    or len(subject) > 128
                    or type(claims.get("exp")) not in (int, float)
                    or not now < claims["exp"] <= now + 300):
                raise ValueError()
            return approval_id, kid
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error,
                OverflowError, InvalidSignature):
            raise PermissionError(APPROVAL_DENIED) from None
