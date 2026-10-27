"""Contract tests for the read-only Calendar availability adapter; no Google calls."""
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import sys
import unittest
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from calendar_readonly import (
    CalendarUnavailable, FREEBUSY_SCOPE, FREEBUSY_URL, read_freebusy,
)

START = datetime(2026, 11, 1, 9, tzinfo=timezone.utc)
END = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)
TOKEN = "fictional-test-token-no-real-authorization"
CALS = ("primary", "approved-secondary")


def fake_body(a=None, b=None):
    return {"calendars": {
        "primary": {"busy": a if a is not None else [
            {"start": "2026-11-01T09:30:00Z", "end": "2026-11-01T10:30:00Z"}]},
        "approved-secondary": {"busy": b if b is not None else [
            {"start": "2026-11-01T10:00:00Z", "end": "2026-11-01T11:00:00Z"}]},
    }}


class Response:
    def __init__(self, value):
        self.stream = io.BytesIO(value)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, amount):
        return self.stream.read(amount)


class CapturingTransport:
    def __init__(self, value=None, error=None):
        self.value = fake_body() if value is None else value
        self.error = error
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        blob = json.dumps(self.value).encode() if not isinstance(self.value, bytes) else self.value
        return Response(blob)


class CalendarReadOnlyTest(unittest.TestCase):
    def query(self, *, transport=None, ids=CALS, start=START, end=END, minimum=15):
        transport = transport or CapturingTransport()
        return read_freebusy(TOKEN, ids, start, end, minimum_minutes=minimum, opener=transport)

    def test_only_freebusy_endpoint_and_scoped_read_request(self):
        self.assertEqual(FREEBUSY_SCOPE, "https://www.googleapis.com/auth/calendar.freebusy")
        transport = CapturingTransport()
        result = self.query(transport=transport)
        self.assertEqual(len(transport.calls), 1)
        req, timeout = transport.calls[0]
        self.assertEqual(req.full_url, FREEBUSY_URL)
        self.assertEqual(req.get_method(), "POST")  # Google freeBusy query is a read operation.
        self.assertEqual(timeout, 10)
        self.assertEqual(req.headers["Authorization"], "Bearer " + TOKEN)
        body = json.loads(req.data)
        self.assertEqual(body["items"], [{"id": "primary"}, {"id": "approved-secondary"}])
        self.assertEqual(body["timeMin"], "2026-11-01T09:00:00Z")
        self.assertEqual(body["timeMax"], "2026-11-01T12:00:00Z")
        self.assertEqual(body["groupExpansionMax"], 0)
        self.assertEqual(result["source"], "google_calendar_freebusy")

    def test_overlap_merges_and_only_aggregated_free_slots_escape(self):
        tr = CapturingTransport({
            **fake_body(),
            "event": {"summary": "PRIVATE", "description": "secret"},
            "calendars": {
                "primary": {"busy": [
                    {"start": "2026-11-01T09:30:00Z", "end": "2026-11-01T10:30:00Z", "summary": "PRIVATE"}]},
                "approved-secondary": {"busy": [
                    {"start": "2026-11-01T10:00:00Z", "end": "2026-11-01T11:00:00Z"}]},
            },
        })
        result = self.query(transport=tr)
        self.assertEqual(result["busy_block_count"], 1)
        self.assertEqual(result["free"], [
            {"start": "2026-11-01T09:00:00Z", "end": "2026-11-01T09:30:00Z"},
            {"start": "2026-11-01T11:00:00Z", "end": "2026-11-01T12:00:00Z"},
        ])
        self.assertNotIn("PRIVATE", str(result))
        self.assertNotIn("primary", str(result))
        self.assertNotIn("approved-secondary", str(result))
        self.assertNotIn(TOKEN, str(result))

    def test_clamps_busy_outside_interval_and_filters_short_gaps(self):
        tr = CapturingTransport(fake_body([
            {"start": "2026-11-01T08:00:00Z", "end": "2026-11-01T09:20:00Z"},
            {"start": "2026-11-01T09:30:00Z", "end": "2026-11-01T12:30:00Z"},
        ], []))
        result = self.query(transport=tr, minimum=15)
        self.assertEqual(result["free"], [])
        self.assertEqual(result["busy_block_count"], 2)

    def test_adjacent_busy_blocks_are_merged(self):
        tr = CapturingTransport(fake_body([
            {"start": "2026-11-01T09:00:00Z", "end": "2026-11-01T10:00:00Z"},
            {"start": "2026-11-01T10:00:00Z", "end": "2026-11-01T11:00:00Z"},
        ], []))
        result = self.query(transport=tr)
        self.assertEqual(result["busy_block_count"], 1)

    def test_timezones_are_normalized_without_local_dst_guessing(self):
        tr = CapturingTransport(fake_body([
            {"start": "2026-11-01T10:30:00+01:00", "end": "2026-11-01T11:30:00+01:00"}
        ], []))
        result = self.query(transport=tr)
        self.assertEqual(result["free"][0]["end"], "2026-11-01T09:30:00Z")

    def test_bad_windows_calendar_ids_and_tokens_never_hit_transport(self):
        tr = CapturingTransport()
        invalid = [
            (CALS, START.replace(tzinfo=None), END),
            (CALS, END, START),
            (CALS, START, START),
            (CALS, START, START.replace(day=5)),
            ((), START, END),
            (("primary",)*2, START, END),
            (tuple(str(x) for x in range(6)), START, END),
            (("bad\nidentifier",), START, END),
        ]
        for ids, start, end in invalid:
            with self.subTest(ids=ids, start=start, end=end):
                with self.assertRaises(ValueError):
                    self.query(transport=tr, ids=ids, start=start, end=end)
        for token in ("", "token with spaces", "\rmalformed", "short"):
            with self.assertRaises(ValueError):
                read_freebusy(token, CALS, START, END, opener=tr)
        for minimum in (0, -1, 181, 1.5, True):
            with self.assertRaises(ValueError):
                self.query(transport=tr, minimum=minimum)
        self.assertEqual(tr.calls, [])

    def test_missing_calendars_or_errors_fail_closed_instead_of_free(self):
        samples = [
            {"calendars": {"primary": {"busy": []}}},
            {"calendars": {"primary": {"busy": []}, "approved-secondary": {"errors": [{"reason": "notFound"}], "busy": []}}},
            {"calendars": {"primary": {"busy": []}, "approved-secondary": {}}},
            {"calendars": {"primary": {"busy": []}, "approved-secondary": {"busy": []}}, "groups": {"group": {"calendars": ["someone"]}}},
            [],
            {"calendars": None},
            {"calendars": {"primary": {"busy": []}, "approved-secondary": {"busy": []}, "unapproved": {"busy": []}}},
        ]
        for body in samples:
            with self.subTest(body=body), self.assertRaises(CalendarUnavailable):
                self.query(transport=CapturingTransport(body))

    def test_malformed_busy_ranges_fail_closed(self):
        bad = [
            {"start": "2026-11-01T11:00:00Z", "end": "2026-11-01T10:00:00Z"},
            {"start": "not-a-date", "end": "2026-11-01T10:00:00Z"},
            {"start": "2026-11-01T10:00:00", "end": "2026-11-01T11:00:00Z"},
            {"start": "2026-11-01T10:00:00Z"},
        ]
        for item in bad:
            with self.subTest(item=item), self.assertRaises(CalendarUnavailable):
                self.query(transport=CapturingTransport(fake_body([item], [])))

    def test_transport_failures_do_not_leak_provider_or_token(self):
        for error in (
            urllib.error.URLError("fictional-token-secret"),
            urllib.error.HTTPError(FREEBUSY_URL, 403, "fictional-token-secret", {}, None),
            TimeoutError("fictional-token-secret"),
        ):
            with self.subTest(error=type(error)), self.assertRaises(CalendarUnavailable) as caught:
                self.query(transport=CapturingTransport(error=error))
            self.assertNotIn("fictional-token-secret", str(caught.exception))
            self.assertNotIn(TOKEN, str(caught.exception))

    def test_rejects_oversized_or_malformed_response(self):
        for content in (b"not json", b"{" + b"x" * 65537, b"[]"):
            with self.subTest(kind=len(content)), self.assertRaises(CalendarUnavailable):
                self.query(transport=CapturingTransport(content))

    def test_no_busy_means_free_window_not_missing_calendar(self):
        result = self.query(transport=CapturingTransport(fake_body([], [])))
        self.assertEqual(result["busy_block_count"], 0)
        self.assertEqual(result["free"], [
            {"start": "2026-11-01T09:00:00Z", "end": "2026-11-01T12:00:00Z"}
        ])


if __name__ == "__main__":
    unittest.main()
