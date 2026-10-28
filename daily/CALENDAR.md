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

## Sign-in is not Calendar authorization

Stoq Daily's planned low-friction sign-in uses **Google as a Cloudflare
Access identity provider** and, when Google offers it, a device passkey
unlocked with Face ID. Existing Cloudflare one-time PIN and the Daily
owner access code remain working fallbacks until separately verified.
Do not attempt to implement Face ID directly in the Daily model pipeline.
Cloudflare Access authentication alone must not be trusted by the origin
without a verified JWT/session boundary.

The **Cloudflare Google sign-in OAuth client** requests authentication
identity only. The **Stoq Calendar OAuth client** is a separate authorization
and credential lifecycle for a separately consented read-only calendar grant.
These clients must not share secrets, tokens or extra Calendar scopes.
A passkey authenticates the Google user; it does not authorize Stoq to
inspect their Google Calendar or keep a refresh token. Connection may be
re-prompted after expiry/revocation, which is preferable to hidden overreach.

Deployment order: (1) personal Google passkey setup; (2) configure/test
Google as additional Cloudflare IdP with exact owner email allow rule,
retaining one-time PIN; (3) separately implement Calendar PKCE OAuth as
specified below. Do not remove the second Daily access-code gate until
backend validation of trusted Cloudflare identity is implemented and
tested, including direct-origin bypass resistance.

## Calendar OAuth protocol foundation (not connected)

The calendar_oauth.py module provides a fixed, separate **Google Calendar
authorization-code flow with PKCE S256**, exact callback
https://stoq.page/daily/api/calendar/callback, random state, and a
Google-token exchange restricted to the single calendar.freebusy scope.
The current Daily server does **not** register that callback or a Connect
button, accept tokens, connect calendars or modify model prompts. The code
has only fictional, injected-network regression tests.

Use a **different Web application OAuth client** from the existing
Cloudflare Google sign-in client, even if both clients live inside the
Google Cloud project named Stoq Authentication. Configure:
- Client label: Stoq Daily Calendar (read-only)
- Authorized redirect URI:
  https://stoq.page/daily/api/calendar/callback
- No browser JavaScript origin is required for a server-side token exchange
- OAuth consent screen: External, with an explicitly approved test user during
  Testing and only the calendar.freebusy scope
- Enable Google Calendar API in the same Google Cloud project

These are setup targets, **not proof of a functional login callback**.
Do not click through a real Calendar consent until its runtime session,
CSRF/state, token-security and revocation handlers have been implemented,
reviewed and deployed. Never paste a Client Secret or OAuth authorization
code into chat/GitHub. While the OAuth application remains in Testing,
Google may expire the grant after seven days; durable refresh behavior must
be evaluated before considering Production publication.

### Mandatory before using these helpers in Daily

- Bind state + PKCE verifier to an authenticated owner, single pending flow,
  strict expiration and one-use consumption, with a protected private store.
- Explicitly resolve cross-site Google-to-Stoq redirect cookie behavior:
  the existing Daily app cookie has SameSite=Strict, so it must **not**
  be assumed present on Google's cross-site callback. Use a limited-purpose
  secure, HttpOnly, SameSite=Lax correlation cookie plus server-side
  owner-bound, expiring state (or equivalent reviewed design); do not weaken
  the existing app session cookie.
- Require exactly one expected Google callback state and authorization code;
  never allow a caller-provided redirect URL or scopes. If Google denies
  access, clear pending state without storing credentials.
- Validate the token response scope, bind the selected Google grant to the
  current owner, store refresh tokens with restricted permissions, and
  never return them to the browser. Verify revocation and failed refresh.
- Before calling freeBusy, verify the particular calendar(s) were selected
  and consented. If selection is absent or a call fails, say availability is
  unavailable, not empty. Avoid logging request URLs, callback codes or
  calendar identifiers in any proxy.
- Keep all token scopes for the dedicated Calendar OAuth client separate from
  Cloudflare's identity provider client. The latter authenticates the user
  but does not grant calendar access.

## Explicit read-only Calendar verification (staged; not deployed)

After the owner approved Google's Calendar free/busy-only consent on
2026-10-28, Daily displayed **"Calendar authorization saved. Availability is
not used in plans yet."** This is evidence that the OAuth redirect and
server-side grant save succeeded, not a successful read of Calendar data.
The grant must not be copied to GitHub or pasted into chat.

The next feature adds an **owner-authenticated, CSRF-checked POST**
`/daily/api/calendar/verify` endpoint and a Settings button to invoke it.
This is **on demand only**: no background polling or startup reads. On
request, it:

1. Reads the private mode-0600 OAuth client and refresh credential.
2. Exchanges the refresh token over Google's fixed OAuth token endpoint
   for a short-lived access token, in memory only. Rejects any returned
   incompatible scope, but accepts Google's documented omission of scope
   on refresh (initial consent had been checked for exact freebusy scope).
3. Requests `freeBusy.query` with exactly `primary` for the next 24 hours.
   No event listing, titles, descriptions, attendee reads, event writes or
   extra calendars; bounded network requests and fail-closed provider errors.
4. Returns only `verified: true`, free/busy scope, calendar count and
   window hours to the owner's UI. It **does not return, persist or inject**
   actual free times into check-in history or the model.

A positive read confirms the permission was usable **for one checked
window only**. It does not mean the owner is generally available or that
future reads will work. Failure is explicitly "unavailable", never "free".
Calendar-to-Planning integration and selected-calendar choices beyond
`primary` require a separate reviewed implementation. The login and
Cloudflare controls are unchanged, and the public website stays public.

The existing on-screen check-in description previously said Calendar
"isn't connected yet", which became misleading once consent was saved.
It is corrected to state accurately that availability is **not used in
plans**.

## Owner-only Calendar consent runtime (staged; not deployed)

This iteration adds `daily/calendar_connection.py` and three existing Daily
server endpoints:
- Authenticated, CSRF-protected POST /daily/api/calendar/connect creates one
  short-lived, owner-session-bound, single-use PKCE authorization request.
- GET /daily/api/calendar/callback uses a Secure, HttpOnly, **SameSite=Lax**
  short-lived correlation cookie, verifies server-side state, expiry and the
  original still-live owner session, then consumes the request **before**
  exchanging a code. It does not depend on the SameSite=Strict Daily session
  on the cross-site Google redirect.
- Authenticated POST /daily/api/calendar/disconnect removes local pending
  consent and stored refresh credentials; it does **not** revoke provider-side
  Google consent. Owners can additionally revoke access in Google Account.

This feature is fail-closed until the operator installs the downloaded Google
Web client file as `/opt/agency-daily/private/data/calendar-client.json`, with
owner UID 10001 and mode 0600. The original download stays private, and
nothing is stored in GitHub, environment variables, browser storage or logs
by these application paths. The on-disk refresh grant is mode 0600 in
`/data/calendar-grant.json`; only the refresh credential is persisted.
Google Cloud clients must use the precise redirect URI described above.

**Do not install or deploy with the live client yet.** Before a live consent
trial, the full feature must pass CI, the app must be deployed with backup and
rollback, and the proxy/Cloudflare callback path must be verified not to
record authorization codes. The existing Nginx public demo source has access
logging disabled globally, but this does not prove that all upstream
infrastructure logs omit query parameters.

This consent phase does not call Google Calendar, refresh access tokens, or
send availability to Planning. A successful authorization is only a grant
stored for later verification. Calendar remains unavailable to the model
until the subsequent free/busy read wiring is separately tested. A locally
saved grant is not proof of a valid current refresh token.

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
