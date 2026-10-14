"""Offline-only exact-intent approval proof verification.

A separate trusted consent/identity service would have to authenticate the
actual user and issue these approvals. This module cannot obtain consent or
sign a proof, and MUST NOT be treated as deployed user authorization.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time

APPROVAL_DENIED = "calendar approval unavailable"
APPROVAL_ACTION = "calendar.event.create"
_APPROVAL_AUDIENCE = "agency-calendar-approval"


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def plan_digest(plan: dict) -> str:
    """Bind approval to the entire canonical Calendar planner result."""
    return hashlib.sha256(_canonical(plan)).hexdigest()


class OfflineApprovalVerifier:
    """Verify independent signed consent evidence for one exact prepared plan.

    Signing is deliberately NOT implemented. Only a separately trusted issuer
    possessing an independent key may sign. A valid signature proves key
    possession, not that a real human approved the operation.
    """

    def __init__(self, *, verification_key: bytes,
                 issuer="agency-calendar-consent", clock=time.time):
        if not isinstance(verification_key, bytes) or len(verification_key) < 32:
            raise ValueError("approval verification key must be >=32 bytes")
        if not isinstance(issuer, str) or not issuer:
            raise ValueError("approval issuer is required")
        self._key = verification_key
        self._issuer = issuer
        self._clock = clock

    def verify(self, proof: str, *, expected_row: dict) -> str:
        """Return a one-use opaque approval ID, or uniformly deny."""
        try:
            if not isinstance(proof, str) or len(proof) > 4096:
                raise ValueError()
            body, signature = proof.split(".")
            expected = hmac.new(self._key, body.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(_decode(signature), expected):
                raise ValueError()
            claims = json.loads(_decode(body))
            if not isinstance(claims, dict):
                raise ValueError()
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
            return approval_id
        except (ValueError, TypeError, KeyError, UnicodeError, binascii.Error,
                UnicodeEncodeError, OverflowError):
            raise PermissionError(APPROVAL_DENIED) from None
