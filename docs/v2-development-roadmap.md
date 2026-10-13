# V2 Development Decisions & Roadmap

**Purpose:** Canonical *development* record for V2 priorities, course corrections, test strategy and resumable next steps. This is not an agent system prompt, runtime policy, source of personal facts, or a replacement for the [V2 orchestration contract](https://github.com/Stoqnist/chatgpt-library/pull/3).

**Status:** Benchmark-first strategy accepted on 2026-10-13. Priority 1 is implemented on experimental PR #3, with final CI/review pending; remaining priorities are tracked below. This file on `main` is the canonical development roadmap. V1 is unchanged; V2 has **not** been deployed.

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

## Prioritized execution plan

| Order | Work item | State | Completion evidence |
| --- | --- | --- | --- |
| **1 — Now** | Build seeded golden-journey generator (~20–30 cases), independent oracle and metamorphic assertions. | **Implemented in draft PR #3; review/final CI pending** | 24 fixed seeds and three metamorphic variants per case; regression tests passed on Python 3.11 and 3.13. Explicit CLI CI step awaiting verification. |
| **2 — Now** | Implement/organize four core adversarial scenarios and cross-domain safety invariants. Reuse existing tests; do not delete useful coverage merely to shrink the suite. | **Not started** | Explicit failure-mode cases pass and can be shown to fail under controlled regressions. |
| **3 — Next** | Add JSON report, stored comparison baseline, and version-to-version comparison summary. | **Not started** | Reports identify commit, seeds, outcomes, timing and applicable usage/cost fields. |
| **4 — Next** | Optimize CI: fast offline benchmark per PR, optional SDK compatibility on a controlled schedule/change trigger, dependency caching as justified. | **Not started** | Measured improvement in CI wall time with unchanged safety coverage; no model charges on PRs. |
| **5 — Next** | Run controlled ablations to test whether one/three AI specialists provide additional value over deterministic logic. | **Not started** | Quality vs. calls, latency and measured cost comparison across identical scenarios. |
| **6 — Later** | Optional, explicitly authorized low-cost real-model canary and usage review. | **Not started** | Logged usage/latency, input provenance and validated results; budget respected as far as provider controls allow. |
| **7 — Later** | Evaluate isolated read-only VPS staging, with no live personal records until separately reviewed. | **Blocked by benchmark/release gates** | Deployment checklist, rollback/cleanup plan and safety review. |

### Verified starting point

- [V2 POC / orchestration draft, PR #3](https://github.com/Stoqnist/chatgpt-library/pull/3) remains separate from this documentation proposal. Its deterministic coordinator, specialist adapter, evidence gate and offline CI already exist on the draft branch.
- A user-run synthetic three-specialist API smoke test reported 3/3 completed calls and zero record writes. That **does not** measure the full system's factual accuracy, incremental AI value or actual API billing.
- The preexisting regression suite covers key behaviors. A 24-seed independent-oracle benchmark is now implemented **in draft PR #3** and passed regression tests; explicit CLI CI verification is pending. Version-to-version comparison and persistent baseline reports remain **not implemented**.

## Risks to revisit at every release review

| Concern | Required response |
| --- | --- |
| Large happy-path tests mask localized bugs | Keep targeted safety/failure checks and provide failure diagnostics. |
| Overfitting to fixed seeds | Separate stable comparison seeds from held-out/rotating tests. |
| Test oracle shares production bugs | Construct expected values independently from fixture semantics. |
| Model nondeterminism / misleading short samples | Report sample size and repeat appropriately; label stochastic results. |
| Additional agents produce no marginal benefit | Compare 0/1/3 model-call variants before expanding orchestration. |
| Synthetic success mistaken for production safety | Keep real personal-data use and write permissions behind separate approvals. |

## Resumption and maintenance protocol

1. At the beginning of future V2 development work, read **this file on the current default branch**, the actual open V2 PR and its relevant CI results. Do not infer current status from remembered chat or old test counts.
2. Resume at the **first unfinished priority**, unless a new failure or explicit decision changes order. State blockers and the smallest verifiable next action.
3. Update this **same file via a reviewed Git PR** when a new architecture/product-development decision changes priorities or acceptance gates. Keep a short dated entry below for materially changed decisions; avoid creating parallel roadmaps or rewriting history as if plans were completed.
4. Advance a work item only after the supporting commit, test report or review is verifiable. Mark uncertain or provider-limited facts as such. Preserve links to implementation PRs instead of copying experimental code or private evidence here.
5. No automatic merge or production deployment is implied by a passing benchmark.

### Decision log

- **2026-10-13 — Benchmark-first strategy accepted:** small and fast seeded golden journey, limited focused adversarial tests, independent oracle, release safety gates, version metrics, controlled paid canary, and 0/1/3-agent ablation. Prioritize implementation before VPS staging. This file is proposed as the project's single development decision/roadmap record.

- **2026-10-13 — Priority 1 implementation proposed in draft PR #3:** added reproducible 24-seed fixture generation, an independent oracle, three metamorphic invariants per case, zero-API JSON reporting and regression tests. Both Python 3.11 and 3.13 regression jobs passed for the initial code. A newer commit added a dedicated benchmark command to PR CI; its run still requires verification. No merge, production deployment or personal-data access is implied.
