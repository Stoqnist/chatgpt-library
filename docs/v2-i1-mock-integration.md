# I1 scripted journey → disposable mock execution

This implementation is a **fictional offline integration test harness**, not a
runtime agent workflow or production approval system.

`health_i1.MockJourneyIntegration` reuses the J1/J2/J3 scripted runner,
observed mock trace and independent health journey oracle before creating
any P3 preview. Only currently proposed operations from the latest
**routine** turn are eligible. A new turn revokes the old preview's authority **inside P3's approval ledger**;
even direct P3 executor or disposable-store calls with a previously approved
operation must be rejected before a new write attempt. Urgent and clarify
turns cannot execute routine actions. Revocation is irreversible for the
same request/operation ID, including a later re-preview or decision.

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

`advance()` reports `withdrawn_operation_ids` for **not-yet-attempted**
previews only. It does not retroactively withdraw actions already attempted.
`execute()` preserves a current-turn `outcomes` list plus
`prior_outcomes`, `cumulative_outcomes`, and `cumulative_status`.
The historical snapshots keep their original `verified`, `failed`, or
`unknown` status and attempt history after a later urgent/changed turn.
An unknown mock effect is not marked cancelled or verified by revocation.
The mock supports explicit `reconcile(operation_id, requester_owner=...)`
**after a later turn supersedes it**. The bridge retains the exact prior
attempted operation. P3's separate `inspect_only(operation,
requester_owner=...)` first requires matching original owner and a trusted
fixture-backed, exact request/operation/resource **recovery-read permission**,
then checks the registered intent, prior `write_attempt`, and ambiguous marker
before inspecting. A missing read permission or foreign owner fails closed
without inspecting, reading back, or disclosing target metadata. At the
I1 entry point, a narrow mock-grant check runs **before** prior-operation and
outcome-history lookups; unauthorized probes of existing, missing, or no-longer
eligible recovery IDs return the same `PermissionError("recovery read not
authorized")` without inspecting records or changing history. Write approvals,
including old approvals, never confer recovery-read permission.
These APIs do not consult or restore approval, do not call `apply`, and cannot
create a new write. Matching applied markers plus successful readback can
change historical `unknown` to `verified` with the original unknown/attempt
trace retained; missing or inaccessible evidence remains `unknown`.
Current-turn `execute()` continues to block stale consent.

The synthetic requester owner is supplied by the caller; the fictional
read permission is assigned by the mock runner when a scoped ambiguous
operation is superseded. **Neither mechanism authenticates a real principal**
or proves provider/connector read access. A real integration must obtain
trusted requester identity and operation-specific read authorization outside
this simulator. This introduces no general role/permissions framework.

This is a deterministic in-memory repair demonstration, **not** a safe real
provider reconciliation protocol. In particular, a missing mock marker is
not evidence that an external write did not happen, and real provider lookup
identity, persistence and later conflicting changes remain unverified.

One mock store is scoped to one simulated session and does not persist consent
or operation markers across restarts. Clinical validity, semantic quality,
actual authentication and OAuth grants, real user consent, provider-side
concurrency/idempotency, recovery and external effects remain unverified.
Passing offline tests does not authorize production writes or V1 cutover.

Run from `poc/v2`:

```bash
PYTHONPATH=. python -m unittest discover -s tests -p test_health_i1.py -v
PYTHONPATH=. python -m unittest discover -s tests -v
```
