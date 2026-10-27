# Calendar availability in private Daily — first read-only slice

**Status:** tested adapter source, **not connected to a Google account or the running app**.
The existing Daily UI, API key, model pipeline and public website remain unchanged.
This file is a development contract, not user OAuth consent.

## Narrowest useful operation

Use Google's Calendar freeBusy.query endpoint only:
POST https://www.googleapis.com/calendar/v3/freeBusy.
The method uses POST but its **effect is a read**, not event creation.
Request only scope https://www.googleapis.com/auth/calendar.freebusy.
Do not use events.list or any event-write scope. Google also documents
calendar.events.freebusy; select one supported scope after testing the
owner's actual grant. Never assume a ChatGPT Calendar connector authorizes
the separate Hetzner web service.

The calendar_readonly.py module implements this fixed endpoint with:

- One explicitly approved calendar-ID set (1–5 IDs, never inferred from
  contacts or unrelated accounts). Future UI consent identifies calendars.
- A positive, timezone-aware window up to 72 hours; normalize to UTC.
- 10-second HTTP timeout, 64-KiB response ceiling, maximum 200 busy
  intervals per calendar; reject inconsistent/partial data, missing
  calendars, invalid dates, provider errors and group expansions.
- Merge overlapping busy intervals; expose only bounded aggregate **free**
  intervals and an aggregate busy-block count. No event title, attendee,
  description, email, calendar ID, credential or raw response in output.
- No retries, side effects, caching, persistent token storage or event writes.

**Semantics:** availability covers *only selected calendars* and the requested
window. An empty busy set in a successful response does not prove the user is
generally available. Calendar state is a bounded observation, never a promise
that an appointment was created. Provider failures mean **missing context**
and must not be interpreted as "free all day".

## Auth and rollout blockers

The adapter expects a separately supplied short-lived OAuth access token.
No app credential is committed, and no OAuth endpoints are enabled. Before
wiring it into the current Daily application:

1. Verify owner identity and exact consented calendars. Decide whether only
   the primary calendar is sufficient; do not claim coverage of others.
2. Implement browser OAuth authorization code with PKCE/state, a fixed exact
   HTTPS callback, owner session linkage, minimal calendar.freebusy scope,
   and CSRF protections. Validate the real provider grant and refresh flow.
3. Store any refresh credential only in protected private server storage,
   separate from public GitHub and check-in history; support revocation.
   Never place tokens in browser localStorage or URL fragments.
4. Verify effective scopes and exact Google principal. ChatGPT's connected
   Calendar plugin is **not** authorization for the Hetzner web service.
5. Inject only sanitized availability into Planning, not router, Wellbeing,
   Home or the public UI by default. Missing Calendar must remain explicit;
   existing check-in functionality must continue without it.
6. Test fake provider responses, then an authorized read-only canary on a
   disposable calendar or explicitly approved low-sensitivity slot window.
   Confirm true read-only scope, timezones, expiry/revocation and zero writes.
   A real personal calendar read requires consent beyond code deployment.
7. Deploy a pinned candidate with isolated smoke test, preserved backups,
   Compose override, health/login checks and rollback; keep public landing
   site and unrelated services unchanged.

Do not commit Google OAuth client secrets, refresh tokens, calendar IDs,
personal events or account emails. Event details and event creation are out
of scope.

## Offline checks

Run: python3 -m unittest discover -s daily/tests -v

test_calendar_readonly.py injects a fake network opener and exercises the
fixed read-only endpoint, bounded windows, aggregation, timezones, errors,
partial response handling and token privacy without contacting Google.
Passing CI does not establish live read permission.

References:
- https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- https://developers.google.com/workspace/calendar/api/auth
