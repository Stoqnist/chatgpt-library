"""Offline-only Google OIDC + Calendar authority *evidence* policy.

This evaluates synthetic, already-verified BFF/Google adapter evidence. It does
NOT validate JWT signatures, fetch JWKS, exchange OAuth tokens, call Google,
authenticate a person, or authorize external Calendar writes. The caller MUST
obtain each field from a trusted, separate verifier; client-supplied JSON is
never acceptable as proof. This module is NOT a production execution gate.
"""
from __future__ import annotations

from collections.abc import Mapping
import math
import time


GOOGLE_ISSUERS = frozenset({"https://accounts.google.com", "accounts.google.com"})
OWNED_EVENT_SCOPE = "https://www.googleapis.com/auth/calendar.events.owned"
CALENDAR_LIST_READ_SCOPE = "https://www.googleapis.com/auth/calendar.calendarlist.readonly"

# A production deployment must select the allowed maximum after testing real
# provider latency, revocation and effective scope introspection.
MAX_SESSION_EVIDENCE_AGE_SECONDS = 30
MAX_CALENDAR_ROLE_AGE_SECONDS = 30
MAX_GRANT_EVIDENCE_AGE_SECONDS = 30
MAX_EXPLICIT_CONSENT_AGE_SECONDS = 120


def _fresh(ts, *, now, seconds):
    return (type(ts) in (int, float) and math.isfinite(ts)
            and 0 <= now - ts <= seconds)


def evaluate_google_owned_calendar_preflight(
    *, session: Mapping, grant: Mapping, expected_oidc_client_id: str,
    expected_calendar_oauth_client_id: str, expected_subject: str,
    expected_calendar_id: str, now: float | None = None,
) -> dict:
    """Evaluate independently verified metadata; no token/external action.

    All evidence is synthetic here. A passing result is a *local contract
    match*, not verification of live login, grant, event insertion or a
    distributed atomic check of Google authority.
    """
    if now is None:
        now = time.time()
    if (type(now) not in (int, float) or not math.isfinite(now)
            or not isinstance(session, Mapping) or not isinstance(grant, Mapping)
            or not all(isinstance(x, str) and x for x in (
                expected_oidc_client_id, expected_calendar_oauth_client_id,
                expected_subject, expected_calendar_id))):
        return {"status": "denied", "reason": "invalid_trusted_inputs"}

    # Google OIDC is verified by a separately configured OIDC verifier that
    # follows Google discovery/JWKS. A session is managed by the private BFF.
    # Do not infer current Google global-login state from an old ID token.
    session_checks = (
        session.get("verified_google_id_token") is True,
        isinstance(session.get("issuer"), str)
        and session.get("issuer") in GOOGLE_ISSUERS,
        session.get("audience") == expected_oidc_client_id,
        session.get("subject") == expected_subject,
        session.get("local_bff_session_active") is True,
        session.get("local_bff_session_revoked") is False,
        _fresh(session.get("session_checked_at"), now=now,
               seconds=MAX_SESSION_EVIDENCE_AGE_SECONDS),
        _fresh(session.get("explicit_consent_at"), now=now,
               seconds=MAX_EXPLICIT_CONSENT_AGE_SECONDS),
        type(session.get("session_expires_at")) in (int, float)
        and math.isfinite(session.get("session_expires_at"))
        and session.get("session_expires_at") > now,
    )
    if not all(session_checks):
        return {"status": "denied", "reason": "google_session_unverified_or_stale"}

    # The Agency OAuth client and current Google account/grant are *different*
    # from the connected ChatGPT Calendar connector. Exact user, OAuth client,
    # calendar ID, scope, role, token expiry and freshness must all match.
    scopes = grant.get("verified_scopes")
    scopes_valid = (
        isinstance(scopes, (tuple, list, frozenset, set))
        and all(isinstance(x, str) for x in scopes)
        and OWNED_EVENT_SCOPE in scopes
        and CALENDAR_LIST_READ_SCOPE in scopes
    )
    grant_checks = (
        grant.get("source_verified_google_calendar") is True,
        grant.get("subject") == expected_subject,
        grant.get("oauth_client_id") == expected_calendar_oauth_client_id,
        grant.get("calendar_id") == expected_calendar_id,
        grant.get("effective_access_role") == "owner",
        grant.get("oauth_grant_active") is True,
        scopes_valid,
        _fresh(grant.get("grant_checked_at"), now=now,
               seconds=MAX_GRANT_EVIDENCE_AGE_SECONDS),
        _fresh(grant.get("calendar_role_checked_at"), now=now,
               seconds=MAX_CALENDAR_ROLE_AGE_SECONDS),
        type(grant.get("token_expires_at")) in (int, float)
        and math.isfinite(grant.get("token_expires_at"))
        and grant.get("token_expires_at") > now,
    )
    if not all(grant_checks):
        return {"status": "denied", "reason": "calendar_grant_unverified_or_stale"}
    return {
        "status": "synthetic_preconditions_satisfied",
        "external_actions": 0,
        "live_write_authorized": False,
    }
