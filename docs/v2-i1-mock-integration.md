# I1 scripted journey → disposable mock execution

This implementation is a **fictional offline integration test harness**, not a
runtime agent workflow or production approval system.

`health_i1.MockJourneyIntegration` reuses the J1/J2/J3 scripted runner,
observed mock trace and independent health journey oracle before creating
any P3 preview. Only currently proposed operations from the latest
**routine** turn are eligible. A new turn invalidates previous pending
previews; urgent and clarify turns cannot execute routine actions.

Only three safe mock destinations are supported:
- Purchase lifecycle proposal → `purchase_note` / `routine_review`,
  **not an order, payment, or physical stock decrement**.
- Health record proposal → `health_note` or `mental_note` with the
  harmless code `followup_needed`, not raw symptom/mental health content.
- Calendar follow-up → `calendar_create` with fixed neutral title
  `Personal follow-up` in the disposable `mock:calendar` store only.

The test caller must explicitly invoke `decide(preview, "approve" | "deny")`;
planning does not authorize actions. P3 enforces fingerprint-bound approval,
owner/destination mapping, optimistic mock revision checks, operation IDs,
readback, and inspection without blind retry after ambiguous outcomes.
The adapter reports per-operation verified, denied, blocked, failed, or unknown
states, including partial execution, without claiming real provider changes.

One mock store is scoped to one simulated session and does not persist consent
or operation markers across restarts. Clinical validity, semantic quality,
actual authentication and OAuth grants, real user consent, provider-side
concurrency/idempotency, recovery and external effects remain unverified.
Passing offline tests does not authorize production writes or V1 cutover.

Run from `poc/v2`:

```bash
PYTHONPATH=. python -m unittest tests.test_health_i1 -v
PYTHONPATH=. python -m unittest discover -s tests -v
```
