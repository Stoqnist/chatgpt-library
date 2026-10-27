"""Bounded Google Calendar free/busy reader; never reads event details or writes events.

Not wired to Daily yet. An owner-approved, short-lived OAuth token with only
calendar.freebusy scope must be supplied by a future auth boundary.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import urllib.error
import urllib.request

FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
FREEBUSY_SCOPE = "https://www.googleapis.com/auth/calendar.freebusy"
MAX_CALENDARS = 5
MAX_WINDOW = timedelta(hours=72)
MAX_BUSY_INTERVALS = 200
MAX_RESPONSE_BYTES = 65536


class CalendarUnavailable(Exception):
    """Read failed: never include tokens, IDs, response bodies, or event facts."""


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Calendar window must have timezone-aware datetimes.")
    return value.astimezone(timezone.utc)


def _stamp(value):
    return value.isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_stamp(value):
    if not isinstance(value, str) or len(value) > 50:
        raise CalendarUnavailable("Calendar availability response is invalid.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return _utc(parsed)
    except (ValueError, TypeError):
        raise CalendarUnavailable("Calendar availability response is invalid.") from None


def _window(start, end):
    start, end = _utc(start), _utc(end)
    if not start < end or end - start > MAX_WINDOW:
        raise ValueError("Calendar window must be positive and at most 72 hours.")
    return start, end


def _calendars(ids):
    if not isinstance(ids, (list, tuple)) or not 1 <= len(ids) <= MAX_CALENDARS:
        raise ValueError("Choose between one and five approved calendars.")
    if any(not isinstance(i, str) or not i or i.strip() != i or
           len(i) > 254 or any(ord(c) < 33 for c in i) for i in ids):
        raise ValueError("Invalid calendar identifier.")
    if len(set(ids)) != len(ids):
        raise ValueError("Calendar identifiers must be unique.")
    return tuple(ids)


def read_freebusy(access_token, calendar_ids, start, end, *,
                  minimum_minutes=15, opener=None):
    """Return non-identifying free windows from Google's freeBusy read API.

    The only HTTP request is POST /calendar/v3/freeBusy, whose *semantics* are
    read-only. Token validity and granted scope are enforced by Google, not
    inferred by this function. No token or raw provider response is persisted.
    Fail closed if any selected calendar has missing/ambiguous data.
    """
    start, end = _window(start, end)
    ids = _calendars(calendar_ids)
    if not isinstance(access_token, str) or not 20 <= len(access_token) <= 8192 or any(
            ord(c) < 33 or ord(c) > 126 for c in access_token):
        raise ValueError("A valid in-memory OAuth access token is required.")
    if type(minimum_minutes) is not int or not 1 <= minimum_minutes <= 180:
        raise ValueError("Minimum free interval must be between 1 and 180 minutes.")

    payload = json.dumps({
        "timeMin": _stamp(start), "timeMax": _stamp(end),
        "timeZone": "UTC", "calendarExpansionMax": len(ids),
        "groupExpansionMax": 0,
        "items": [{"id": value} for value in ids],
    }, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(
        FREEBUSY_URL, data=payload, method="POST",
        headers={"Authorization": "Bearer " + access_token,
                 "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with (opener or urllib.request.urlopen)(request, timeout=10) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise CalendarUnavailable("Calendar availability response is too large.")
        body = json.loads(raw)
    except CalendarUnavailable:
        raise
    except (urllib.error.HTTPError, urllib.error.URLError, OSError,
            TimeoutError, ValueError, UnicodeError):
        raise CalendarUnavailable("Calendar availability could not be verified.") from None

    if not isinstance(body, dict) or not isinstance(body.get("calendars"), dict):
        raise CalendarUnavailable("Calendar availability response is invalid.")
    if body.get("groups"):
        raise CalendarUnavailable("Calendar availability response included group data.")

    calendars = body["calendars"]
    if set(calendars) != set(ids):
        raise CalendarUnavailable("Calendar availability is incomplete.")

    busy = []
    for calendar_id in ids:
        entry = calendars[calendar_id]
        if not isinstance(entry, dict) or entry.get("errors") or not isinstance(entry.get("busy"), list):
            raise CalendarUnavailable("Calendar availability is incomplete.")
        if len(entry["busy"]) > MAX_BUSY_INTERVALS:
            raise CalendarUnavailable("Calendar availability is too complex.")
        for interval in entry["busy"]:
            if not isinstance(interval, dict):
                raise CalendarUnavailable("Calendar availability response is invalid.")
            left = _parse_stamp(interval.get("start"))
            right = _parse_stamp(interval.get("end"))
            if left >= right:
                raise CalendarUnavailable("Calendar availability response is invalid.")
            if right <= start or left >= end:
                continue
            busy.append((max(left, start), min(right, end)))

    busy.sort()
    merged = []
    for left, right in busy:
        if merged and left <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], right))
        else:
            merged.append((left, right))

    cursor, free = start, []
    for left, right in merged:
        if left - cursor >= timedelta(minutes=minimum_minutes):
            free.append({"start": _stamp(cursor), "end": _stamp(left)})
        cursor = max(cursor, right)
    if end - cursor >= timedelta(minutes=minimum_minutes):
        free.append({"start": _stamp(cursor), "end": _stamp(end)})

    # Whitelist output: no calendar IDs, event names, descriptions or attendees.
    return {
        "source": "google_calendar_freebusy",
        "window_start": _stamp(start),
        "window_end": _stamp(end),
        "free": free,
        "busy_block_count": len(merged),
    }
