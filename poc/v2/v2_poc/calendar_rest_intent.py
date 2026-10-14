"""I1 offline Google Calendar REST intent contract. NO network or provider writes.

Not an OAuth adapter, durable attempt ledger, or exactly-once guarantee.
"""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


_OPERATION_ID = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")
EVENT_ID = re.compile(r"[0-9a-v]{5,1024}\Z")
TITLE = "Personal follow-up"
READ_FIELDS = (
    "id,status,summary,start(dateTime,timeZone),end(dateTime,timeZone),"
    "visibility,transparency,reminders(useDefault,overrides),"
    "attendees(email),conferenceData,hangoutLink"
)


def _time(value: str, zone: ZoneInfo) -> datetime:
    if not isinstance(value, str):
        raise ValueError("a full RFC3339 timestamp with offset is required")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("invalid RFC3339 timestamp") from error
    if moment.utcoffset() is None or moment.utcoffset() != moment.astimezone(zone).utcoffset():
        raise ValueError("timestamp must have an offset valid for the explicit timezone")
    return moment


def plan_insert(*, secret: bytes, calendar_id: str, request_id: str,
                operation_id: str, start: str, end: str,
                timezone_name: str) -> dict:
    """Prepare a non-sensitive event with stable secret-derived Google event ID.

    The caller MUST durably register/approve the exact intent BEFORE an insert.
    Identical inputs with the same private secret produce the same event ID.
    """
    if not isinstance(secret, bytes) or len(secret) < 32:
        raise ValueError("requires a durable private HMAC key (at least 32 bytes)")
    if not isinstance(calendar_id, str) or not calendar_id.strip() or len(calendar_id) > 512:
        raise ValueError("calendar identity is required")
    if any(not isinstance(v, str) or _OPERATION_ID.fullmatch(v) is None
           for v in (request_id, operation_id)):
        raise ValueError("stable request and operation IDs are required")
    try:
        zone = ZoneInfo(timezone_name)
    except (TypeError, ValueError, ZoneInfoNotFoundError) as error:
        raise ValueError("explicit IANA timezone is required") from error
    first, last = _time(start, zone), _time(end, zone)
    length = (last.astimezone(timezone.utc) - first.astimezone(timezone.utc)).total_seconds()
    if not 0 < length <= 3600:
        raise ValueError("follow-up duration must be between 1 second and 1 hour")

    body = {
        "summary": TITLE,
        "start": {"dateTime": first.isoformat(), "timeZone": timezone_name},
        "end": {"dateTime": last.isoformat(), "timeZone": timezone_name},
        "visibility": "private",
        "transparency": "transparent",
        "reminders": {"useDefault": False, "overrides": []},
    }
    # Length-prefixing is unnecessary with deterministic canonical JSON. The
    # HMAC key and raw identity/intent remain private; event ID is opaque.
    fingerprint = json.dumps(
        ["agency-v2-calendar-1", calendar_id, request_id, operation_id, body],
        sort_keys=True, separators=(",", ":"), ensure_ascii=True,
    ).encode("utf-8")
    identifier = base64.b32hexencode(
        hmac.new(secret, fingerprint, hashlib.sha256).digest()[:20]
    ).decode("ascii").rstrip("=").lower()
    assert EVENT_ID.fullmatch(identifier)
    body["id"] = identifier
    return {
        "calendar_id": calendar_id,
        "body": body,
        "insert_params": {"sendUpdates": "none", "conferenceDataVersion": 0},
        "read_params": {"fields": READ_FIELDS},
        "requires_preinsert_durable_attempt": True,
        "live_execution_authorized": False,
    }


def verify_exact_readback(plan: dict, *, read_calendar_id: str,
                          event: dict | None) -> dict:
    """Verify exact, successful event readback or return unknown, never retry.

    The API caller must authenticate and authorize the exact calendar itself.
    A missing event, inaccessible read, or partial response is inconclusive.
    """
    expected = plan["body"]
    if read_calendar_id != plan["calendar_id"] or not isinstance(event, dict):
        return {"status": "unknown"}
    for key, value in (("id", expected["id"]), ("status", "confirmed"),
                       ("summary", TITLE), ("visibility", "private"),
                       ("transparency", "transparent")):
        if event.get(key) != value:
            return {"status": "unknown"}
    try:
        for key in ("start", "end"):
            item = event[key]
            if not isinstance(item, dict) or item.get("timeZone") != expected[key]["timeZone"]:
                return {"status": "unknown"}
            if datetime.fromisoformat(item["dateTime"].replace("Z", "+00:00")) != \
                    datetime.fromisoformat(expected[key]["dateTime"]):
                return {"status": "unknown"}
    except (KeyError, TypeError, ValueError):
        return {"status": "unknown"}
    reminder = event.get("reminders")
    if (not isinstance(reminder, dict) or reminder.get("useDefault") is not False
            or reminder.get("overrides", []) != []
            or event.get("attendees", []) != []
            or event.get("hangoutLink")
            or event.get("conferenceData")):
        return {"status": "unknown"}
    return {"status": "verified"}
