# Private daily MVP

A separate, single-owner phone web app at `/daily/`. One submitted check-in is routed to up to three separate model calls (wellbeing, home, planning), with minimal exact excerpts and one consolidated UI. This is a real API integration, not a synthetic-fixture demo. Its live readiness still requires an owner API key and a successful canary.

## Deliberate scope

- User-submitted context only. **No Calendar, Gmail, inventory, bank or Library connector access.** Do not present this as the full existing daily routine or a clinical system.
- No external writes or executed actions. Model advice stays explicitly unverified. The pilot does not reuse or impersonate existing custom GPTs.
- Conservative urgent-input interruption is model-based, not a validated clinical triage service. No diagnosis or treatment. A provider failure blocks output or gives a clearly partial result.
- Maximum one active run, three specialists, four bounded calls per check-in, 20 submissions per rolling 24 hours, no automatic provider retry. Counts are not a dollar budget; configure provider project limits.
- Request IDs deduplicate transport retries. Runs interrupted by restart are marked interrupted and never replayed. Clearing history does not reset usage limits.

## Privacy and access

The public shell contains no personal information. All state, settings and model execution require the owner access code. Random, server-side hashed sessions use Secure/HttpOnly/SameSite=Strict cookies, seven-day absolute expiry, exact-Origin and CSRF validation for mutations. Login attempts are limited. No request/prompt/key logging, localStorage, analytics or service worker.

API keys remain in a mode-0600 file on the private server, never sent back to the browser. The directory is mode 0700, owned by service UID 10001. This is filesystem protection, **not encryption at rest**. The server operator can read it. Check-in text/results reside in a mode-0600 SQLite database and are application-deleted after seven days or by Clear history. SQLite/file-system remnants and external backups are outside this deletion guarantee. No canonical personal records are modified. API requests use `store:false`; this does not override provider abuse-monitoring/data-retention policy.

## Deployment

Keep this project isolated from the public demo and MCP services. A private env file supplies `AGENCY_ORIGIN=https://stoq.page`, `AGENCY_LOGIN_HASH` (generated with `password_hash`), and optional `AGENCY_MODEL` (default gpt-4.1-mini). Never commit private files or an actual access code. Mount `/opt/agency-daily/private/data` to `/data`; permissions must be 0700/UID 10001. Run one Gunicorn worker; in-process submission serialization and executor are deliberately single-process. Startup marks interrupted runs before serving requests.

The existing demo proxy forwards only `/daily/` to `agency-daily:8000`. Runtime DNS lookup allows the public demo to work if the private service is absent. Health is loopback-only and isn't publicly routed. Both services retain independent images/rollback.

Check: `python3 -m unittest discover -s daily/tests -v` and `node --check daily/static/app.js`, plus existing generated demo/HTTP checks. Build/release and live model canary must be recorded separately. Synthetic tests inject the provider; production has no mock mode.

Source API contract: https://developers.openai.com/api/docs/guides/structured-outputs and https://developers.openai.com/api/reference/resources/responses/methods/create.
