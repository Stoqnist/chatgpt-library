# V2 Development Decisions & Roadmap

**Purpose:** Canonical *development* record for V2 priorities, course corrections, test strategy and resumable next steps. This is not an agent system prompt, runtime policy, source of personal facts, or a replacement for the [V2 orchestration contract](https://github.com/Stoqnist/chatgpt-library/pull/3).

**Status (2026-10-13):** End-to-end, evidence-backed personal assistance is the V2 product target. The original purchase benchmark, baseline comparator, scripted 0/1/3 ablation, and deterministic Finance counterfactual are implemented on the **experimental V2 branch** through merged PRs #7–#10, not deployed. The orchestration POC remains draft PR #3 against `main`. Next work is cross-domain health-led acceptance tests and safety/authority contracts; a passing synthetic purchase benchmark alone is insufficient. V1 remains unchanged.

## Development north star

Measure **verified user value per unit of time and cost**, subject to uncompromising safety and privacy constraints. More agents, calls, or text are not indicators of improvement unless they improve correct, evidence-supported outcomes. Keep the recurring test suite small, fast, inexpensive and reproducible; do not reduce important safety coverage merely to lower the number of test functions.

## Accepted decisions (2026-10-13)

| ID | Decision | Rationale / safeguard |
| --- | --- | --- |
| D01 | Benchmark results become the principal *development* indicator, alongside safety gates and review. | Track product quality, latency and cost over versions; a single aggregate score is not a production-safety guarantee. |
| D02 | Use one representative end-to-end **golden journey** with approximately 20–30 reproducible seeded variants. | Vary synthetic item names, amounts, IDs and harmless ordering without changing expected rules. Keep a fixed comparison corpus plus separately generated discovery cases. |
| D03 | Keep a small focused adversarial suite in addition to the golden journey. | A passing happy path can hide missing-evidence, conflicting-evidence, unauthorized-action or fabricated-claim failures. |
| D04 | Compute expected outcomes using an **independent oracle** and explicit invariants. | Do not copy implementation logic into the expected-result calculation. Add metamorphic properties such as renaming an item not changing spending totals and duplicate input not changing unique spending. |
| D05 | Make routine PR checks **offline, deterministic, and zero API charge**. | Mock model boundaries. Real-model canaries are manually authorized or deliberately release-gated, with a known project budget and no credentials or personal data committed. |
| D06 | Measure task success, safety violations, unsupported accepted claims, time, and **cost per successful workflow**. | Store commit, configuration, model, seed, input family, timing, usage, outcomes and failures so baseline/candidate comparisons are meaningful. Do not treat estimated API pricing as measured cost. |
| D07 | **Safety violations block promotion** irrespective of an overall benchmark score. | Wrong-domain writes, unauthorized action, disclosure, fabricated execution and unsupported verified claims must remain unacceptable. Unresolved quality/cost regressions require explicit review. |
| D08 | Perform an **ablation comparison**: deterministic coordinator only; coordinator plus one needed AI specialist; coordinator plus three specialists. | The current narrowly typed model signals may be cheaply derivable without AI; prove the incremental benefit before paying for more calls. |
| D09 | Do not tune only on the public fixed seeds. | Prevent benchmark overfitting using held-out or freshly generated cases and periodic new case families; retain reproduction seeds for failures. |
| D10 | Deployment remains **isolated and read-only** until gates pass; no implicit V1 cutover or access to personal records. | A green synthetic benchmark does not establish production-data safety. Preserve specialist ownership and explicit approval boundaries. |

These are **agreed design decisions**, not claims that the corresponding benchmark features or deployment gates are implemented.

## Minimal benchmark contract (planned)

**Primary journey:** One fictional household purchase crosses Purchase & Resale, Finance, and Home. For every seeded case, independently assert:

- One consolidated result and only relevant specialists invoked; each domain owns its own decisions and proposed canonical records.
- Unique card-spending total equals the fixture-defined purchase amount; overlapping exports are deduplicated; own-account transfers are excluded.
- No physical possession is asserted without delivery/receipt evidence; no proof of receipt-payment linkage is inferred from matching amounts alone.
- Provenance and material uncertainty survive consolidation. No unsupported model prose is promoted as verified fact.
- All writes remain unexecuted in read-only mode, with zero unauthorized data sharing or external calls.

**Focused adversarial cases (initial four):** missing/ambiguous evidence; conflicting transaction identifiers or values; unauthorized action/wrong-domain write; invented evidence or unsupported AI assertions. Add regression cases after real failures rather than growing a large speculative matrix.

**Mutation checks:** Renaming/ID changes that preserve relationships do not change computed amounts; shuffling row order does not alter decisions; adding a duplicate export row does not change unique spend; removing delivery proof removes any possession conclusion.

**Result artifact:** A small machine-readable JSON report plus a compact human summary. Minimum fields: benchmark version, source commit, configuration/model, seeds, case pass/fail and failure reason, safety-violation count, unsupported accepted-claim count, p50 elapsed time (p95 only with sufficient samples), specialist calls, token usage when available, total measured or estimated cost (explicitly labeled), and cost per successful workflow when measurable. No personal data, API keys, or raw private inputs in public artifacts.

**Version comparisons:** Run baseline and candidate against the same fixed seeds and comparable environments; report sample count and variability. Run additional held-out/rotating cases separately. For real-model canaries, avoid interpreting one model sample as statistically conclusive; isolate SDK/model/prompt version effects.

**Promotion gates:** All fixed golden-journey cases and mandatory safety cases must pass; **zero critical safety violations**; no unexplained loss of task quality. Set numerical latency/cost regression thresholds only after an observed baseline exists. A successful test suite is a necessary gate, never sufficient authorization for production writes.

## Product-level V2 acceptance target (2026-10-13)

**User journey:** A user reports a physical or mental health concern in one request. V2 assesses urgency, retrieves only the necessary authoritative health/stock/financial/schedule context, engages relevant owners, returns one coherent plan, and—only with existing authority and appropriate consent—executes and verifies approved record and calendar changes. This is the intended system-level behavior, **not** a capability demonstrated by the current purchase POC.

- **Owner boundaries:** Health owns clinical interpretation, triage, wellbeing and health-suitability judgments. Home owns possession and live stock truth (registered Google Sheet for food/supplements). Finance owns affordability, funding/timing and global purchase priority. Purchase & Resale owns product/seller choice and transaction lifecycle within Finance's envelope. The coordinator owns orchestration and truthful consolidated status, not the canonical data. Google Calendar is the default for reminders and date-specific commitments; scheduled ChatGPT tasks are for future agent work. Never introduce a parallel record.
- **Conditional participation:** A simple issue may require Health alone; inventory, purchasing, budget and calendar steps are conditional on actual need. Relax the current POC's three-domain cap **only via a separately tested bounded dispatcher/schema change**. Keep one owner per decision/write, no recursive delegation, explicit dependencies and minimum necessary evidence.
- **Health-first gate:** Triage for urgent/worsening physical or mental-health red flags before shopping, planning or financial optimization. Escalation must not wait for a budget check or routine specialist completion. Do not diagnose from a photo, mood, wearable estimate or absent evidence. Reflect uncertainty and avoid unsupported treatment claims; professional care and emergency escalation take precedence when indicated. Clinical decision rules need independent health-domain review and periodic source/version checks.
- **Synthetic-first:** Public repository fixtures must be fictional and de-identified from inception, not sanitized exports of actual health, finance, calendar or inventory accounts. No provider tokens, private locators, medical records or sensitive free text in CI logs or artifacts.

### First three golden journeys and mandatory variants

| Journey | Normal-path acceptance | Required counterexamples |
| --- | --- | --- |
| **J1 Flu-like illness — first** | Health assesses symptoms/uncertainty and recovery needs; Home checks fresh stock; Finance/Purchase contribute only if a genuine shortage and spend exist; coordinator drafts a safe plan, owner-scoped record proposals and minimal calendar follow-up. | Urgent physical red flag; stale/unknown inventory; insufficient or unknown budget; contraindicated/unsuitable product; missing tool; denied purchase/calendar approval. |
| **J2 Minor wound** | Health determines whether self-care guidance is appropriate; Home checks supplies/condition; Purchase/Finance are conditionally invoked; follow-up/record proposals retain provenance. | Infection/worsening or high-risk wound flags; misleading photo; absent supplies, expiry/unknown quantities; contradictory evidence; medical unsuitability overrides cheap product. |
| **J3 Stress, poor sleep, low energy** | Health assesses wellbeing, functioning and uncertainty, proposes achievable non-diagnostic next steps; Calendar and other domains participate only as needed; mental-health record stays owner-scoped. | Acute mental-health safety concern; ambiguous self-report; privacy leak into Finance/Purchase/calendar title; unwanted persistent monitoring; unsupported mental-state inference. |

Build **3 base journeys and initially 6–9 targeted negative variations**, not dozens of superficial scripted responses. Add held-out/newly generated cases after observed failures. A fixture-specific oracle should check observable outcomes and invariants independently of coordinator decision code. Preserve the existing 24-seed purchase test and focused mutation suite as component-level regressions.

### Non-negotiable end-to-end invariants

1. **Safety and urgency:** critical physical/mental-health signals prevent unsafe reassurance and unnecessary routine workflow delay. No model-generated diagnosis or contraindicated product recommendation passes as established fact. Health decides health suitability; other owners cannot overrule it.
2. **Correct routing, data minimization and privacy:** only relevant specialists run; funding specialists see urgency/cost envelope rather than raw mental-health history; calendar titles/descriptions contain no unapproved sensitive details. A failed/blocked specialist causes a truthful partial result, not fabricated completion.
3. **Fresh sources and uncertainty:** read current registered canonical records, including timestamp/revision where available. Purchase receipts do not establish remaining stock, bank balances can be stale, and unknown ≠ zero. Missing connections or conflicting facts must remain unresolved; continue independent safe steps.
4. **Budget and purchases:** Finance validates essential spending constraints and global priority; Purchase researches only within a confirmed envelope. Unknown affordability cannot be treated as authorization. No order, payment, borrowing, deletion or other external commitment without explicit appropriate approval.
5. **Record and calendar actions:** separate **proposed → authorized → attempted → verified** outcomes; record denied, partial, failed and unknown states. Significant/ambiguous multi-file changes require an approval preview. A read-only request produces zero writes. Owner-scoped writes use stable request/operation IDs, source/revision preconditions, readback, and inspection before retry after uncertain results; no double decrement, double event, duplicate purchase need or duplicate appointment.
6. **Data boundaries and persistence:** one canonical home per fact. Health physical vs mental records, Home stock, Finance decisions and Purchase lifecycle must not be blindly mirrored. No unsolicited capture or background monitoring; no raw private data in Git/CI. Validate actual tool access before claiming updates or reminder delivery.
7. **Useful integrated outcome:** one consolidated plan distinguishes user reports, verified records, interpretations, and unknowns; includes minimal material questions, safe next actions and clear responsibility; no score rewards excessive delegation, question count or unneeded spending.
8. **Evidence and evaluation integrity:** different fixture families, independent expected outcomes, targeted mutation tests, fresh/held-out seeds, reproducible failures and explicit environment/latency/cost provenance. Synthetic green cannot authorize real-model canaries, production writes or V1 cutover.

### Prioritized execution plan — updated

| Priority | Work item / scope | Completion evidence and gate |
| --- | --- | --- |
| **P0 — now** | **Specify cross-domain contracts and acceptance oracle.** Define fictional Health/Home/Finance/Purchase/Calendar inputs and outputs, urgency/approval states, minimum data sharing, ordered dependencies, failure statuses and independently authored invariants. Confirm owner-specific record destinations and limit of the current read-only runtime. | Reviewed V2 experimental PR with J1 fixture and fail-first assertions; no unsupported implied integrations; urgent triage and data minimization invariants explicit. **Not implemented.** |
| **P1 — next** | **Implement J1 flu-like illness as an end-to-end simulated journey.** Conditional 1–4 domain planning and mock Calendar; mocked current vs stale stock/budget; read-only recommendations and recorded action proposals, no real health data. | End-to-end CI assertions for safe triage, necessary owner routing, coherent plan, accurate unknowns, no unintended actions; urgent/insufficient-budget/missing-connection negatives pass. **Not implemented.** |
| **P2 — next** | **Add J2 wound and J3 mental-wellbeing cases plus 6–9 negative controls.** Include photo/observation uncertainty, crisis escalation, privacy and medical suitability. | Independent oracle, privacy-leak mutations, unsafe-reassurance/contraindication negatives, held-out variants; correct status on partial failures. **Not implemented.** |
| **P3 — after read-only** | **Simulated approval and transaction-safe execution.** Disposable canonical test records + mock Calendar, explicitly authorized owner writes, stable IDs, precondition/version checks, readback, no duplicates; partial outcomes and failed/unknown writes. | Negative tests for approval refusal, conflicting versions, retried timeouts, repeated events, and one domain failing while others safely complete. No actual user accounts touched. **Not implemented.** |
| **P4 — gated integration** | **Verify actual connector/runtime feasibility and least-privilege boundaries** for canonical Library files, registered food Sheet, Finance/Purchase sources and Google Calendar. Time-sensitive reads and multi-file writes remain per-owner. | Explicit scope/permission matrix, consent and dry-run verification, private disposable integration trial, provider errors and rollback/repair path. Actual side effects only with separate user approval. **Not implemented.** |
| **P5 — measured optimization** | Evaluate **verified user value vs. cost/latency** across realistic journeys: deterministic, one needed specialist and multiple needed specialists. Maintain seed parity, independent oracles, bounded call budgets and real-model uncertainty. Optimize PR CI (SDK-trigger/caching) only after coverage is safe. | Quality/safety improvements measured per task, cost per successful workflow when measurable, time distribution from properly scoped timers; no unsupported free-text assertions. Real-model canaries need explicit separate spend approval. **Not implemented for health-led journeys.** |
| **P6 — release gate** | Separately review and, if justified, pilot isolated read-only staging before any real records or production execution. Preserve V1 until an explicit migration plan and rollback are approved. | Documented approvals, clinical/safety/privacy audit, tool behavior, observability, recovery and rollback; no release based solely on synthetic green. **Blocked.** |

### Existing component-level evidence — retain, do not confuse with product readiness

- Original **Priority 1/2:** 24 synthetic fixed purchase seeds, independent oracle, 72 metamorphic checks, focused adversarial tests and 9/9 source mutations. Implemented on experimental branch under draft [PR #3](https://github.com/Stoqnist/chatgpt-library/pull/3); not deployed.
- Original **Priority 3:** verified fixed-seed baseline, JSON comparison and provenance safeguards, merged to experimental V2 via [PR #7](https://github.com/Stoqnist/chatgpt-library/pull/7).
- Original **Priority 4 (partial):** Node.js 24 GitHub Action upgrades through [PR #8](https://github.com/Stoqnist/chatgpt-library/pull/8). Full CI speed/caching/SDK split is **not** completed or necessary before P0.
- Original **Priority 5:** 0/1/3 **scripted/mock** specialist harness via [PR #9](https://github.com/Stoqnist/chatgpt-library/pull/9), and deterministic Finance typed-question counterfactual via [PR #10](https://github.com/Stoqnist/chatgpt-library/pull/10); both merged to experimental V2. They demonstrate only synthetic harness equivalence and safety, not real-model value/cost/latency, clinical suitability, authenticated side effects or release readiness.
- The canonical development record on `main` previously lagged these experimental commits. This status reconciliation updates documentation only; no runtime or publishing rules change.

## Risks to revisit at every release review

| Priority | High-probability failure | Required test or mitigation |
| --- | --- | --- |
| **P0** | Emergency symptoms buried under shopping/budget/calendar; photo or model output mistaken for diagnosis | Independent urgency oracle, escalation-first negative fixtures, Health-owned suitability gate; block downstream unsafe tasks. |
| **P0** | Inappropriate access to mental-health history, health details in Finance or public calendar | Domain-specific minimal disclosure schemas, private simulation snapshots, adversarial data-leak assertions. |
| **P0** | Plan presented as executed action; unauthorized purchase or mutation | Explicit authority and per-action lifecycle states; zero side effects in read-only and denied cases; verified readback before success claims. |
| **P1** | Incorrect current stock/budget from stale file, shopping receipt, screenshot or previous chat | Fresh registered-store retrieval and revision checks; unknown and conflicting sources remain unresolved. |
| **P1** | Wrong specialist count or arbitrary three-domain cap blocks a four-owner case | Conditional evidence-based dispatcher with bounded parallelism/dependency order and owned write destinations. |
| **P1** | Budget optimization overrules health safety or treats unknown balances as affordable | Health suitability veto; Finance funding envelope; defer nonurgent spend if budget data unavailable. |
| **P2** | Medical contraindication, infection red flags or acute distress missed | Independent expert-reviewed scenario criteria, targeted negative controls, time-sensitive guidance revisions. |
| **P2** | More specialists/questions create noise without useful marginal improvement | Task-outcome score penalizes redundant calls, invented conclusions, unnecessary purchases and duplicate questions. |
| **P3** | Partial write failure, retries or concurrent changes double-decrement stock, duplicate calendar events or corrupt files | Stable operation IDs, owner-only writes, optimistic preconditions and readback; inspect unknown outcomes before retry; report partial completion. |
| **P3** | Medication intake/delivery inferred from inventory, footage or device values | Separate observation vs consumption vs possession; user confirmation for uncertain intake and clinically material history. |
| **P4** | Test doubles mask unavailable connectors, scopes, notification delivery or provider side effects | Disposable integration tests, actual permissions audit, explicit success vs queued action, no assumed exactly-once semantics. |
| **P5** | Benchmark overfitting, correlated oracle and implementation, ill-defined timing, or scripted “benefit” marketed as measured AI value | Hold-outs and metamorphic checks, independently defined oracle, direct candidate timing and measured usage/cost fields. |
| **P6** | Synthetic CI treated as deployment approval; live data leak into public Git or logs | Separate human release/clinical/privacy review, read-only staging, redacted telemetry, explicit rollout/rollback and V1 isolation. |

## Resumption and maintenance protocol

1. At the beginning of future V2 development work, read **this file on the current default branch**, the actual open V2 PR and its relevant CI results. Do not infer current status from remembered chat or old test counts.
2. Resume at the **first unfinished priority**, unless a new failure or explicit decision changes order. State blockers and the smallest verifiable next action.
3. Update this **same file via a reviewed Git PR** when a new architecture/product-development decision changes priorities or acceptance gates. Keep a short dated entry below for materially changed decisions; avoid creating parallel roadmaps or rewriting history as if plans were completed.
4. Advance a work item only after the supporting commit, test report or review is verifiable. Mark uncertain or provider-limited facts as such. Preserve links to implementation PRs instead of copying experimental code or private evidence here.
5. No automatic merge or production deployment is implied by a passing benchmark.

### Decision log

- **2026-10-13 — Benchmark-first strategy accepted:** small and fast seeded golden journey, limited focused adversarial tests, independent oracle, release safety gates, version metrics, controlled paid canary, and 0/1/3-agent ablation. Prioritize implementation before VPS staging. This file is proposed as the project's single development decision/roadmap record.

- **2026-10-13 — Priority 1 implementation proposed in draft PR #3:** added reproducible 24-seed fixture generation, an independent oracle, three metamorphic invariants per case, zero-API JSON reporting and regression tests. Both Python 3.11 and 3.13 regression jobs passed for the initial code. A newer commit added a dedicated benchmark command to PR CI; its run still requires verification. No merge, production deployment or personal-data access is implied.

- **2026-10-13 — Priority 2 implementation proposed in draft PR #3:** [commit f417b87](https://github.com/Stoqnist/chatgpt-library/commit/f417b87d98c66337f4a21e7d917d378e2445f165) adds four focused safety families and an offline mutation gate without changing runtime behavior. Existing tests remain. Nine isolated regressions cover missing transaction identity, conflicting values, account-scoped identity, action authority, domain write ownership, fabricated execution, evidence scope, unsupported prose, and invented evidence. Each must cause assertion failures; test errors and surviving mutations fail the gate. Local verification: 46 tests passed, one optional installed-SDK test skipped; golden journey 24/24 with 72 metamorphic checks; mutations 9/9 detected. [CI run 38399801680](https://github.com/Stoqnist/chatgpt-library/actions/runs/38399801680) passed on Python 3.11 and 3.13, including the installed-SDK, benchmark, mutation and preflight steps. Prior Priority 1 CI is now verified rather than inferred. No merge, paid model calls, production writes, or deployment.

- **2026-10-13 — Health-led cross-domain golden journeys reprioritized:** User clarified V2 must solve one-request real-world scenarios across Health, Home, Finance, Purchase and Calendar, with owner-scoped canonical updates after approval. Introduced P0–P6 acceptance, execution and release gates for flu-like illness, wound and mental-wellbeing cases, with safety escalation, privacy, stale-data, authority, partial failure, deduplication and integrated outcome scoring. Preserve the existing purchase benchmark as component evidence and defer real-model canary/staging. This is a roadmap decision only; no runtime capability or deployment is implied.
