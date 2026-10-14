"""Synthetic provider-specific evidence tests, no credentials or network."""
import copy
import math
import unittest

from v2_poc.calendar_google_authority import (
    CALENDAR_LIST_READ_SCOPE, OWNED_EVENT_SCOPE,
    evaluate_google_owned_calendar_preflight as check,
)

NOW = 1_000_000
OIDC_CLIENT = "fictional-agency-login-client"
CALENDAR_CLIENT = "fictional-agency-calendar-client"
SUBJECT = "fictional-google-subject"
CALENDAR = "fictional-owned-calendar"


def evidence():
    session = {
        "verified_google_id_token": True,
        "issuer": "https://accounts.google.com",
        "audience": OIDC_CLIENT,
        "subject": SUBJECT,
        "local_bff_session_active": True,
        "local_bff_session_revoked": False,
        "session_checked_at": NOW,
        "explicit_consent_at": NOW,
        "session_expires_at": NOW + 300,
    }
    grant = {
        "source_verified_google_calendar": True,
        "subject": SUBJECT,
        "oauth_client_id": CALENDAR_CLIENT,
        "calendar_id": CALENDAR,
        "effective_access_role": "owner",
        "oauth_grant_active": True,
        "verified_scopes": [CALENDAR_LIST_READ_SCOPE, OWNED_EVENT_SCOPE],
        "grant_checked_at": NOW,
        "calendar_role_checked_at": NOW,
        "token_expires_at": NOW + 300,
    }
    return session, grant


def evaluate(session, grant, **overrides):
    args = {
        "session": session, "grant": grant,
        "expected_oidc_client_id": OIDC_CLIENT,
        "expected_calendar_oauth_client_id": CALENDAR_CLIENT,
        "expected_subject": SUBJECT,
        "expected_calendar_id": CALENDAR,
        "now": NOW,
    }
    return check(**{**args, **overrides})


class GoogleAuthorityPolicyTests(unittest.TestCase):
    def test_owned_role_with_exact_separate_scopes_is_only_synthetic_evidence(self):
        session, grant = evidence()
        self.assertEqual(evaluate(session, grant), {
            "status": "synthetic_preconditions_satisfied",
            "external_actions": 0, "live_write_authorized": False,
        })

    def test_no_app_login_or_wrong_oidc_identity_denies(self):
        for field, value in (
            ("verified_google_id_token", False),
            ("issuer", "https://malicious-issuer.invalid"),
            ("issuer", []),
            ("audience", "not-the-agency-login-client"),
            ("subject", "other-google-account"),
            ("local_bff_session_active", False),
            ("local_bff_session_revoked", True),
            ("session_expires_at", NOW - 1),
            ("session_checked_at", NOW - 31),
            ("session_checked_at", NOW + 1),
            ("explicit_consent_at", NOW - 121),
            ("explicit_consent_at", None),
        ):
            with self.subTest(field=field, value=value):
                session, grant = evidence()
                session[field] = value
                self.assertEqual(evaluate(session, grant)["status"], "denied")

    def test_connector_role_is_not_agency_calendar_grant(self):
        session, grant = evidence()
        # Connected Calendar's owner role is insufficient without the separate
        # Agency OAuth client's verified scopes/principal.
        grant["source_verified_google_calendar"] = False
        self.assertEqual(evaluate(session, grant)["status"], "denied")
        for field, value in (
            ("subject", "different-grant-subject"),
            ("oauth_client_id", "chatgpt-calendar-connector"),
            ("calendar_id", "different-calendar"),
            ("effective_access_role", "reader"),
            ("effective_access_role", "writer"),
            ("effective_access_role", "writerWithoutPrivateAccess"),
            ("oauth_grant_active", False),
            ("grant_checked_at", NOW - 31),
            ("calendar_role_checked_at", NOW - 31),
            ("token_expires_at", NOW - 1),
        ):
            with self.subTest(field=field, value=value):
                s, g = evidence()
                g[field] = value
                self.assertEqual(evaluate(s, g)["status"], "denied")

    def test_readonly_scope_or_broad_unrequested_scope_does_not_suffice(self):
        for scopes in (
            [CALENDAR_LIST_READ_SCOPE],
            [OWNED_EVENT_SCOPE],
            ["https://www.googleapis.com/auth/calendar.readonly"],
            ["https://www.googleapis.com/auth/calendar.events",
             CALENDAR_LIST_READ_SCOPE],
            [],
            None,
            "https://www.googleapis.com/auth/calendar.events.owned",
        ):
            with self.subTest(scopes=scopes):
                session, grant = evidence()
                grant["verified_scopes"] = scopes
                self.assertEqual(evaluate(session, grant)["status"], "denied")

    def test_stale_unknown_malformed_or_future_evidence_fails_closed(self):
        session, grant = evidence()
        for kwargs in (
            {"now": float("nan")},
            {"expected_subject": ""},
            {"session": None},
            {"grant": None},
            {"expected_calendar_id": None},
        ):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(evaluate(session, grant, **kwargs)["status"],
                                 "denied")
        for which, field, value in (
            ("session", "session_checked_at", float("nan")),
            ("session", "session_expires_at", float("inf")),
            ("grant", "grant_checked_at", NOW + 10),
            ("grant", "calendar_role_checked_at", None),
            ("grant", "token_expires_at", float("inf")),
        ):
            with self.subTest(field=field):
                s, g = evidence()
                (s if which == "session" else g)[field] = value
                self.assertEqual(evaluate(s, g)["status"], "denied")

    def test_does_not_create_events_or_infer_user_approval(self):
        session, grant = evidence()
        # A synthetic preflight is not authorization to invoke provider REST.
        result = evaluate(session, grant)
        self.assertIs(result["live_write_authorized"], False)
        self.assertEqual(result["external_actions"], 0)


if __name__ == "__main__":
    unittest.main()
