# Private daily MVP

## Morning Companion — staged UI source, not yet deployed

The **Start morning check-in** control opens a three-question, optional-answer
guide: sleep/physical comfort; energy/mood/mental clarity; and priorities
including appointments, replies, hygiene, meals, chores and protected focus.
The owner can review and edit the resulting text before pressing **Find my
next steps**. There are no stored incomplete answers, mandatory health
scores, new model calls, automatically submitted requests or provider writes.

The start tap attempts a welcoming spoken prompt. Browser speech synthesis
can also read a question or selected completed plan after explicit activation. Optional browser recognition can enter
a spoken answer only after pressing **Speak answer**, and only on supporting
browsers. **A browser may send microphone audio to its own speech provider**;
Stoq itself does not record audio or upload it through this feature. Brave
speech-recognition support is inconsistent. Device keyboard dictation and
typing remain the supported fallbacks. Never claim guaranteed local-only
transcription or full-duplex voice. Speech is stopped on logout, cancel, backgrounding or
check-in submission. This slice requires owner browser QA, a pinned-image
deployment, backup and rollback before it is operational.

**Email remains a subsequent, separate permissioned milestone:** read-only
metadata/message triage before owner-reviewed drafts, then individual
send approval and provider readback. No Gmail scopes, OAuth or access are
added by the Morning Companion. Private advocate matters remain separate.

A separate, single-owner phone web app at `/daily/`. One submitted check-in is routed to up to three separate model calls (wellbeing, home, planning), with minimal exact excerpts and one consolidated UI. This is a real API integration, not a synthetic-fixture demo. Its live readiness still requires an owner API key and a successful canary.

## Deliberate scope

- User-submitted context only. **No Calendar, Gmail, inventory, bank or Library connector access.** Do not present this as the full existing daily routine or a clinical system.
- No external writes or executed actions. Model advice stays explicitly unverified. The pilot does not reuse or impersonate existing custom GPTs.
- Conservative urgent-input interruption is model-based, not a validated clinical triage service. No diagnosis or treatment. A provider failure blocks output or gives a clearly partial result.
- Maximum one active run, three specialists, five bounded calls per check-in, 20 submissions per rolling 24 hours, one final coordinator selection pass, no automatic provider retry. Counts are not a dollar budget; configure provider project limits.
- Request IDs deduplicate transport retries. Runs interrupted by restart are marked interrupted and never replayed. Clearing history does not reset usage limits.

## Privacy and access

The public shell contains no personal information. All state, settings and model execution require the owner access code. Random, server-side hashed sessions use Secure/HttpOnly/SameSite=Strict cookies, seven-day absolute expiry, exact-Origin and CSRF validation for mutations. Login attempts are limited. No request/prompt/key logging, localStorage, analytics or service worker.

API keys remain in a mode-0600 file on the private server, never sent back to the browser. The directory is mode 0700, owned by service UID 10001. This is filesystem protection, **not encryption at rest**. The server operator can read it. Check-in text/results reside in a mode-0600 SQLite database and are application-deleted after seven days or by Clear history. SQLite/file-system remnants and external backups are outside this deletion guarantee. No canonical personal records are modified. API requests use `store:false`; this does not override provider abuse-monitoring/data-retention policy.

## Additional handoff controls (source patch; deployment separately verified)

The server rejects recognizable pasted API tokens **before** storing or sending
a new check-in. After model routing, it refuses Home/Planning handoffs containing
a narrow set of high-confidence private health, financial or credential terms.
The final plan selection receives the non-sensitive Home/Planning task excerpts
and bounded specialist suggestions, not the complete original check-in.

These are defense-in-depth checks, **not** a comprehensive classification or
data-loss prevention system. The initial router necessarily receives the
submitted prompt; model-generated specialist suggestions can still inadvertently
contain sensitive details. Users should not submit credentials, and sensitive
health details require a separate privacy review before personal use. A rejected
handoff yields a clear failed status; the server does not silently rewrite
what the user reported.

The changes above are only active once this reviewed source is separately
deployed to Hetzner. Passing CI does not verify the running image.

## Calendar access (verified; Planning opt-in source only)

- [Calendar availability architecture and rollout gates](CALENDAR.md) document
  the owner-consented Google OAuth grant on the private server and the
  separately staged explicit free/busy verification check.
- Production does not yet use Calendar in check-ins. The verification
  probe (once deployed) checks only the primary calendar for 24 hours and
  returns success/failure, not appointments or availability slots.
- Calendar-to-Planning integration requires a further review, live read-only
  verification, scoped data handling and rollout.

- Source-only Planning integration adds a **default-off** one-time owner
  setting. If enabled after deployment, only relevant nonurgent Planning
  check-ins can read bounded primary-calendar free/busy samples, with clear
  fallback when Google is unavailable. No Calendar events are listed or
  modified and no raw availability is persisted. Do not mark this deployed
  until a pinned candidate and a live read-only canary are verified.

## Quality evidence

- [Daily quality gate](QUALITY.md) contains seven fictional offline journeys plus a small real-model manual canary rubric. A green offline test is not a live-model quality result.
- Real-account test reports must exclude keys, access codes, private check-in text and identifying account details.

## Deployment

Keep this project isolated from the public demo and MCP services. A private env file supplies `AGENCY_ORIGIN=https://stoq.page`, `AGENCY_LOGIN_HASH` (generated with `password_hash`), and optional `AGENCY_MODEL` (default gpt-4.1-mini). Never commit private files or an actual access code. Mount `/opt/agency-daily/private/data` to `/data`; permissions must be 0700/UID 10001. Run one Gunicorn worker; in-process submission serialization and executor are deliberately single-process. Startup marks interrupted runs before serving requests.

The existing demo proxy forwards only `/daily/` to `agency-daily:8000`. Runtime DNS lookup allows the public demo to work if the private service is absent. Health is loopback-only and isn't publicly routed. Both services retain independent images/rollback.

Check: `python3 -m unittest discover -s daily/tests -v` and `node --check daily/static/app.js`, plus existing generated demo/HTTP checks. Build/release and live model canary must be recorded separately. Synthetic tests inject the provider; production has no mock mode.

Source API contract: https://developers.openai.com/api/docs/guides/structured-outputs and https://developers.openai.com/api/reference/resources/responses/methods/create.

## Morning entry and saved plans (P0 correction)

The landing screen starts at **Not started** with **Start morning check-in** as
the primary action and **Write a check-in instead** as an alternative. The start
tap opens the optional three-question guide and attempts a welcome via browser
speech synthesis. It never starts a microphone or submits a check-in. Speak
answer is a separate explicit browser-permission action; Stop cancels audio.
Unavailable recognition exposes **Use keyboard dictation** and instructions,
including typing when device dictation is absent. Actual iPhone Brave voice
support requires owner device acceptance; API presence does not prove audibility.

Completed results are kept in collapsed, dated **Previous check-ins**, including
same-day/fictional runs. Only a newly submitted or recovered running check-in
uses the current result area automatically. An open result crossing local
midnight becomes a labeled saved check-in. Drafts are memory-only: reload or
lock discards them. Review and explicit submission remain required.

Run `node --test daily/tests/test_morning*.cjs` for prompt and UI interactions,
plus the existing Python regressions and production image CI. No schema,
credentials, Calendar consent or server configuration changes are required for
this frontend correction. Build the merged revision as a pinned candidate, use
the existing isolated smoke/backup/rollback procedure, then check the phone UI.
