# V2 Calendar Gateway — offline implementation

**Status:** Prototype on the experimental V2 branch, not a deployed VPS server. No HTTP listener, real OAuth connection, provisioned vault key, actual VPS configuration, live Google read or write, or user consent for provider side effects is part of this PR. V1 and canonical agent record ownership are unchanged.

## Narrow ownership and authorization boundary

The core verifies a short-lived, signed caller assertion (issuer, audience, calendar ID, role and expiry) **before** accessing an operation record. Only the role calendar_executor may prepare an event and register a separately approved attempt; only calendar_recovery may inspect an attempted operation. These are trusted-service roles, not self-identified AI-agent strings. **No real assertion issuer, external authentication service, TLS boundary or replay defense is implemented in this prototype.** Signing keys must remain outside agents, source control and routine logs. User approval is a separate exact-intent verifier; a mock callback cannot stand in for real user consent. The gateway does not implement event creation or a general-purpose permissions framework.

Google OAuth scopes govern what the **application** may access, not what an individual AI agent may access. For least privilege, configure one separately approved Calendar resource and a minimum accepted Calendar OAuth grant; consider an app-created secondary calendar and the calendar.app.created scope only if its creation and isolation are separately approved. That scope does not apply automatically to existing personal calendars.

## OAuth refresh design

The OfflineOAuth core builds a one-use Authorization Code + PKCE URL using access_type=offline, checks callback state and granted scopes, stores a refresh token only via an **injected private vault**, and silently requests a short-lived access token when necessary using an **injected Google HTTPS exchange client**. A minimal GoogleHTTPS adapter is implemented with fixed Google token and exact-ID Calendar read endpoints, default TLS verification, redirect refusal and bounded JSON/error responses; no general URL proxy or Calendar write operation exists. An offline implementation now provides EncryptedFileVault with AES-256-GCM authenticated encryption, owner-only directory/file checks, atomic replace and directory fsync. Its key must be provisioned independently through the VPS secret manager or protected root-only key file, **never next to its ciphertext or inside Git**. Concurrent writers, encryption-key rotation, backup/restore and actual VPS provisioning remain unverified. Missing, tampered or insecure vault data fails closed. A revoked or missing refresh token yields a reauthorization-needed outcome rather than attempts to recover automatically.

For production consent setup, **do not leave an external Google app in Testing indefinitely**: refresh tokens for Calendar scopes are generally subject to seven-day expiry in that mode. The VPS needs its own OAuth client; existing ChatGPT Google credentials are neither assumed transferable nor requested.

## Durable, exact readback design

A local SQLite test ledger stores one unique operation ID, generated Google-compatible event ID, opaque correlation marker, allowed calendar and expected start/end times. The attempt marker is committed before a hypothetical provider call, then the recovery method requests only ID, status, start/end and the private marker for that **exact** ID. Wrong owner, bad assertion, unknown ID and non-attempted ID fail before provider read. Event readback requests only event identity, status, start/end dateTime and private event properties, and accepts timestamp-equivalent timezone offsets. A missing event, read error, invalid marker, mismatched time or cancelled event stays unknown; nothing retries, writes or deletes in the recovery path. No Calendar POST is implemented.

Opaque private extended event properties are **not secret storage**. There is no atomic transaction across SQLite and Google. The current ledger is only an offline test fixture; production durability, single-writer behavior and read authority require independent proof.

## Next deployment gates

1. Create and configure an independent OAuth client with an approved redirect URI and minimum accepted scopes.
2. Provision an approved disposable Calendar and existing harmless test event; separately authorize exact event-ID readback with only needed fields.
3. Wire and review the implemented encrypted-vault and HTTPS client **on a privately configured VPS**, with secret-key provisioning, single-writer enforcement, backup/restore, process-level isolation, trusted caller issuer, TLS-only ingress, and safe audit metadata. Verify real callback state, expiry, granted scopes, refresh and revocation; *offline tests are not provider proof*.
4. Build a separate approval-bound Calendar create adapter only after the exact operation, calendar, stable client event ID, notification/attendee behavior, duplicate handling and post-timeout recovery are verified on disposable resources.
5. Preserve unknown outcomes, no blind retry, and no access through an unguarded direct Calendar connector. No production writes or deployment are authorized by green offline tests.

Run offline from poc/v2 after installing the pinned cryptography dependency:

```bash
python -m pip install -r requirements-gateway.txt
PYTHONPATH=. python -m unittest discover -s tests -p 'test_calendar_gateway*.py' -v
```

The tests use synthetic tokens, signed proofs and fake HTTP responses exclusively. CI additionally runs the full V2 suite on Python 3.11 and 3.13.

Google references: https://developers.google.com/identity/protocols/oauth2/web-server ; https://developers.google.com/identity/protocols/oauth2/ ; https://developers.google.com/workspace/calendar/api/auth ; https://developers.google.com/workspace/calendar/api/v3/reference/events

This experimental PR should remain separate from canonical roadmap decisions on main, which require a separate reviewed documentation PR.
