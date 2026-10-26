# V2 Personal Daily Routine — private MVP

**Status:** isolated implementation awaiting offline CI, security review, private
Cloudflare Access setup, and a validated server deployment. Not a release.

## User journey

On an iPhone, open the private daily check-in page. Enter one short check-in
(sleep, energy, concerns, priorities). The server runs bounded, sequential,
**advisory-only** specialist calls: Health, then Home and Finance if relevant,
then Planner for one synthesized daily plan. The response is displayed as
editable-reading cards: synthesized plan first, supporting specialist advice
second. No ChatGPT agent or connector is remotely invoked; this is an API-based
prototype with scoped specialist instructions, not the entire V2 architecture.

The prototype **does not read or update** the canonical Health/Finance/Home
records, household inventory, or Google Calendar. It does not write reminders,
schedule tasks, contact doctors, order products, or persist check-in content.
User reports and model interpretations are not provider-verified facts.

Emergency keyword checks stop the normal routine and show a professional-care
warning; they are intentionally conservative and are **not** a complete
medical triage system. Never rely on this application in an emergency.

## Requirements

- The private server runs as a separate container bound to host loopback.
- A Cloudflare Tunnel connected to that host maps a private hostname to
  `http://127.0.0.1:18080`. The hostname MUST be protected by an Access
  application policy restricted to one user; create the Access application
  **before** publishing the tunnel route.
- The backend independently checks Cloudflare's signed Access assertion
  (issuer, RS256 signature, audience, expiry, owner email). The server MUST
  NOT be reachable through another ingress path.
- Never put tokens, runtime environment files or personal information in Git.
- Use a **new** API key created for this private app, with project billing caps.
  A previously disclosed key is not suitable for a live release.

## Server setup (after review and key rotation)

In the repository root, pull the reviewed commit. From `mvp/daily-routine/`,
create a local `private.env` using the following **names only**; supply
the values on the server, and keep the file mode 0600:

```env
CF_ACCESS_TEAM=YOUR_CLOUDFLARE_TEAM_SLUG
CF_ACCESS_AUD=YOUR_ACCESS_APPLICATION_AUDIENCE
AGENCY_OWNER_EMAIL=YOUR_LOGIN_EMAIL
AGENCY_PUBLIC_ORIGIN=https://YOUR_PRIVATE_HOSTNAME
OPENAI_API_KEY=SET_ON_SERVER_ONLY
AGENCY_DAILY_MODEL=gpt-4.1-mini
```

Use `chmod 600 private.env`. Start the isolated service:

```sh
cd mvp/daily-routine
docker compose build --pull
docker compose up -d
docker compose ps
curl -fsS http://127.0.0.1:18080/_internal/live
curl -i http://127.0.0.1:18080/
```

The liveness check is expected to succeed; the unauthenticated page request
MUST return HTTP 401. Once the separate Cloudflare Access policy and Tunnel
route are active, authenticate from the phone through the private HTTPS
hostname. Confirm the page loads, one prompt yields one synthesis and bounded
specialist advice, unauthorized identities fail, and a routine does not
create records/calendar entries. No changes to V1 services or the landing page.

## Offline checks

```sh
python -m pip install -r mvp/daily-routine/requirements.txt
cd mvp/daily-routine
python -m unittest discover -v
python -m py_compile app.py
```

The CI workflow runs offline checks without an API key. Those tests alone
do **not** prove deployed authentication or live model safety.

## Blocking release checklist

- [ ] Offline tests pass and focused medical privacy/urgency review completed.
- [ ] Fresh OpenAI API key replaces the previously shared one; old key revoked,
      private server secret configured and API budget capped.
- [ ] Cloudflare Access policy tested with allowed and denied identities.
- [ ] Tunnel hostname exclusively reaches loopback container; no direct origin.
- [ ] Real-model check with harmless, non-sensitive test text and explicit
      low budget; inspect failures, latency and spending.
- [ ] Confirm no record writes, calendar writes or V1 changes.
- [ ] Verify UI on iPhone and desktop and confirm there are no credentials in
      code, Git history, CI logs, client JavaScript or HTTP responses.

Do not merge or deploy as a production personal service until these pass.
Additional providers/canonical writes require independent consent and
verification implementation, not an expansion of this MVP's privileges.
