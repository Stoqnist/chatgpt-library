"""Fully offline, fictional tests: no OAuth, network, events or personal data."""
from copy import deepcopy
import unittest

from v2_poc.calendar_rest_intent import plan_insert, verify_exact_readback


def plan(**changes):
    params = dict(secret=b"synthetic-test-key-32-bytes-only--", calendar_id="fictional-calendar",
                  request_id="fictional-request", operation_id="fictional-operation",
                  start="2030-01-15T09:00:00+01:00", end="2030-01-15T09:05:00+01:00",
                  timezone_name="Europe/Amsterdam")
    params.update(changes)
    return plan_insert(**params)


def observed(p):
    return {**deepcopy(p["body"]), "status": "confirmed"}


class CalendarRestIntentTests(unittest.TestCase):
    def test_google_id_is_stable_base32hex_and_intent_bound(self):
        p = plan()
        i = p["body"]["id"]
        self.assertRegex(i, r"\A[0-9a-v]{32}\Z")
        self.assertEqual(i, plan()["body"]["id"])
        for delta in (dict(calendar_id="another-calendar"),
                      dict(request_id="another-request"),
                      dict(operation_id="another-operation"),
                      dict(start="2030-01-15T09:01:00+01:00"),
                      dict(secret=b"different-private-key-32-bytes-!!")):
            with self.subTest(delta=delta):
                self.assertNotEqual(i, plan(**delta)["body"]["id"])

    def test_minimal_safe_rest_plan_and_no_implicit_execution(self):
        p = plan()
        self.assertEqual(p["insert_params"], {"sendUpdates": "none", "conferenceDataVersion": 0})
        self.assertEqual(p["body"]["summary"], "Personal follow-up")
        self.assertEqual(p["body"]["visibility"], "private")
        self.assertEqual(p["body"]["transparency"], "transparent")
        self.assertEqual(p["body"]["reminders"], {"useDefault": False, "overrides": []})
        self.assertFalse(set(p["body"]) & {"attendees", "conferenceData", "description", "location", "iCalUID"})
        self.assertIn("fields", p["read_params"])
        self.assertTrue(p["requires_preinsert_durable_attempt"])
        self.assertFalse(p["live_execution_authorized"])

    def test_invalid_secret_identifier_time_or_zone_rejected(self):
        for delta in (dict(secret=b"short"), dict(secret="not-bytes"),
                      dict(request_id="request with spaces"),
                      dict(operation_id=""), dict(calendar_id=""),
                      dict(start="2030-01-15T09:00:00"),
                      dict(timezone_name="Mars/Phobos"),
                      dict(start="2030-01-15T09:00:00+00:00"),
                      dict(end="2030-01-15T09:00:00+01:00"),
                      dict(end="2030-01-15T11:00:00+01:00")):
            with self.subTest(delta=delta):
                with self.assertRaises(ValueError):
                    plan(**delta)

    def test_exact_readback_verified_only_when_all_checks_match(self):
        p = plan()
        self.assertEqual(verify_exact_readback(p, read_calendar_id=p["calendar_id"],
                                               event=observed(p)), {"status": "verified"})
        self.assertEqual(verify_exact_readback(p, read_calendar_id="wrong-calendar",
                                               event=observed(p)), {"status": "unknown"})
        for key, bad in (("id", "other-id"), ("summary", "Medical follow-up"),
                         ("status", "cancelled"), ("visibility", "public"),
                         ("transparency", "opaque"), ("reminders", {"useDefault": True}),
                         ("attendees", [{"email": "fictional@example.invalid"}]),
                         ("hangoutLink", "https://example.invalid/meeting"),
                         ("conferenceData", {"entryPoints": [{"entryPointType": "video"}]}),
                         ("start", {"dateTime": "2030-01-15T09:30:00+01:00", "timeZone": "Europe/Amsterdam"})):
            candidate = observed(p)
            candidate[key] = bad
            with self.subTest(key=key):
                self.assertEqual(verify_exact_readback(p, read_calendar_id=p["calendar_id"],
                                                       event=candidate), {"status": "unknown"})
        self.assertEqual(verify_exact_readback(p, read_calendar_id=p["calendar_id"],
                                               event=None), {"status": "unknown"})
        self.assertEqual(verify_exact_readback(p, read_calendar_id=p["calendar_id"],
                                               event={"id": p["body"]["id"]}), {"status": "unknown"})


if __name__ == "__main__":
    unittest.main()
