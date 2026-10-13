# P4 Connector Feasibility and Least-Privilege Review

**Status:** 2026-10-13, experimental audit, not release clearance. This file contains **no private account identifiers**. Repository `main` remains V1; P3 test doubles are not a production API.

## Read-only discovery evidence

The connected capabilities were inspected without changing any record. The registered food spreadsheet was located using the deployed Library architecture; metadata confirmed a native Sheet with a `Stock` tab. Google Drive returned the file MIME type and modification metadata. Calendar list access returned six calendar entries with reader/owner roles and a primary calendar. Library search found current Health, Finance, and Purchase canonical record names with editor role. No sensitive record content, stock quantities, calendar event details, or private locator is included here.

These observations establish **only metadata discovery**, and may become stale. They do **not** verify OAuth scope grants, principal identity, effective write rights, target ownership for execution, delivery of notifications, version-based compare-and-swap, or idempotency after timeout. Private bindings and operational facts remain outside Git.

## Capability and owner matrix

| Domain / destination | Canonical owner | Available capability observed or tool contract | Required proof before any production write | Gate |
| --- | --- | --- | --- | --- |
| Health / physical and mental records (Library) | Health | Canonical Library file discoverability; file read and managed revision workflow available in conversation tools | Exact canonical identity, current revision, approved mutation, conflict guard, readback, scoped principal, private disposable integration | Blocked |
| Food stock (registered Google Sheet) | Home | Registered native spreadsheet metadata and `Stock` tab accessible; bounded range-read and update actions advertised | Verify row/item identity, exact tab, independent consent, current values, per-row serialization, duplicate recovery, non-atomic provider semantics | Blocked |
| Financial records (Library / connected finance sources) | Finance | Canonical record names discoverable; bank transaction/account access and grants **not** verified | Read scope and freshness, minimal financial envelope to other agents; Finance-only edits and approval/readback on disposable target | Blocked |
| Purchase lifecycle (Library) | Purchase & Resale | Canonical file discoverable; purchase provider/order capability not verified | Never place orders as part of a record-test; verify owner approval, lifecycle revision, provider side-effect semantics separately | Blocked |
| Google Calendar | Calendar action owner under orchestration and user consent | Calendar listing accessible; calendar create/read/update tools advertised, but no event or notification delivery tested | Exact calendar ACL (reader is never sufficient for writes), user-approved neutral title, bounded event search, event ID/readback and ambiguous-timeout recovery | Blocked |
| Connector-independent P3 mock backend | Respective owners | In-memory operation markers and optimistic revisions verified only by offline tests | **Not transferable** to Google Sheets, Library, or Calendar without adapter-specific evidence | Mock only |

## Least-privilege execution contract

1. Resolve canonical provider and owner from the current deployed architecture; obtain private resource bindings at runtime. Do not infer mappings from mock destinations or Git.
2. Start read-only; read only the minimum authorized fields. Health detail must not reach Finance/Purchase/Calendar. Return unknown for stale or inaccessible sources; do not substitute old chat or screenshots.
3. Treat a successful metadata probe as metadata only. For a synthetic **read** probe, compare the stated ACL role against the minimum read role (`viewer` for Library, `reader` for Sheets/Calendar): editor/writer/owner is flagged `excess_read_privilege` and blocked until a separately reviewed exception or narrower connection is established. This role comparison is **not** a real effective-grants, principal, ACL-inheritance or OAuth scope audit; no exception is granted here. The offline P4 classifier has **no execution path** and always returns `execution_allowed=false`, even when all synthetic capabilities are true.
4. For a **separately authorized** future disposable write: confirm dedicated test resource, principal, required provider scopes, owner, exact operation preview and explicit user approval; verify current version and that no other writer has changed it.
5. Execute only through an independently gated adapter. Capture attempt/operation ID, provider response, provider state after readback, partial outcomes and unknown state. Inspect unknown outcomes before retry; never assume exactly-once or transactional writes.
6. No production or private-record writing, deletions, purchasing, notification delivery, or calendar mutations occur in this PR or CI.

## Remaining gaps and repair plan

- **Library:** Tool-level version preconditions and partial failure semantics must be exercised against an **approved disposable Library target** without overwriting canonical identities.
- **Sheets:** Google Sheets lacks an established database-level compare-and-set guarantee in this architecture; serialize owner writes, reread current rows, and fail on conflict. Recover through authoritative readback rather than blind retry.
- **Calendar:** Calendar roles can differ between calendars; confirm the specific target ACL. Create a one-off neutral-titled event only in a separately approved disposable test calendar, verify with read, and delete only with separate explicit authorization. Unknown create results require bounded search and inspection; do not promise an exactly-once event.
- **Finance/Purchase:** External account and order APIs are not inspected or authorized by this metadata check; real purchase/payment actions are out of scope.
- **Identity/scope:** Effective OAuth grants, tenant/account identity and private resource bindings were not obtained. A synthetic minimum-role regression now rejects overprivileged read ACLs, but does **not** prove actual granted scopes or effective permissions; these still require private, provider-specific verification. Discovery is not authorization.
- **Privacy/operations:** Keep private probe logs and identifiers out of CI, repo, and artifacts. For live tests, keep redacted event IDs, exact provider error type, and manual repair status privately.
- **Rollback:** Multi-provider operations are not atomic; no automatic global rollback. For each verified partial write, stop new dependent actions, report verified changes, seek owner/user approval for compensating action, then verify compensation. Do not delete an uncertain write blindly.

## P4 acceptance status

**Offline preflight implementation:** implemented and CI-checkable; verifies structural owner/provider gates and rejected permission/stale/timeout/scope cases. **Live connector integration:** not run; deliberately gated by separate user approval. **Production readiness:** blocked until private disposable trial, permission/scope evidence, failure-recovery review, and explicit release decision. Passing P4 synthetic tests must not lift P6 release gates.
