"""Privacy-minimal read-only free/busy context for the Planning specialist only.

No event listing, writes, persistence, or calls unless owner separately opted in.
Time zone is explicitly configured for this single-owner pilot. A free interval
is NOT a promise that the user is awake, available for work or has consented
to scheduling an action.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from calendar_connection import _read_client, CalendarConnectionError
from calendar_verify import _read_refresh, refresh_access, CalendarVerifyError
from calendar_readonly import read_freebusy, CalendarUnavailable

MAX_WINDOWS = 6
MAX_SAMPLE_HOURS = 3


def planning_freebusy(data_dir, now, *, timezone_name="Europe/Amsterdam",
                      token_opener=None, calendar_opener=None):
    """Return at most six derived, local-time free windows; no event details.

    Every call is owner-initiated via an opted-in check-in and targets only
    the primary Calendar over the next 24h. The returned windows are samples
    of the read-only result, not proof of full user availability.
    """
    data = Path(data_dir)
    try:
        zone = ZoneInfo(timezone_name)
        client, secret = _read_client(data / "calendar-client.json")
        refresh = _read_refresh(data / "calendar-grant.json")
        access = refresh_access(client, secret, refresh, opener=token_opener)
        start = datetime.fromtimestamp(now, tz=timezone.utc)
        end = start + timedelta(hours=24)
        response = read_freebusy(
            access, ["primary"], start, end, minimum_minutes=30,
            opener=calendar_opener)
        windows = response["free"]
        if not isinstance(windows, list):
            raise ValueError()
        samples = []
        for entry in windows[:MAX_WINDOWS]:
            begin = datetime.fromisoformat(entry["start"].replace("Z", "+00:00"))
            finish = datetime.fromisoformat(entry["end"].replace("Z", "+00:00"))
            if begin.utcoffset() is None or finish.utcoffset() is None or not begin < finish:
                raise ValueError()
            # Never imply that a huge 24-hour block is a suitable task time.
            # These are small samples of *unblocked* windows, not commitments.
            finish = min(finish, begin + timedelta(hours=MAX_SAMPLE_HOURS))
            samples.append({
                "start": begin.astimezone(zone).isoformat(timespec="minutes"),
                "end": finish.astimezone(zone).isoformat(timespec="minutes"),
            })
        return {
            "status": "verified",
            "calendar": "primary",
            "timezone": timezone_name,
            "sample_free_windows": samples,
            "window_hours": 24,
            "interpretation": (
                "These are read-only, potentially free calendar intervals, not "
                "confirmed personal availability. Only suggest a time if it "
                "fits the owner's stated preferences. Never claim an event "
                "was read, created, moved or scheduled."
            ),
        }
    except (CalendarConnectionError, CalendarVerifyError, CalendarUnavailable,
            ValueError, KeyError, TypeError, OverflowError, OSError,
            ZoneInfoNotFoundError):
        raise CalendarVerifyError(
            "Calendar free/busy context is unavailable.") from None
