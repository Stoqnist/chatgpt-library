# Daily Service-Level and Subscription Blueprint

Updated: 2026-11-04  
Status: Internal working blueprint v0.1. Not a customer agreement, published offer,
approved price list or operational guarantee.

## Purpose and audience

Define what Stoq Daily can responsibly offer future subscribers and connect each
promise to implementation, measurement, support capacity and release evidence.
The development roadmap owns delivery priority; this document owns the service
design and commitment register.

Working audience hypothesis: adults seeking private, voice-friendly daily reflection,
practical planning and understandable personal trends. Validate the initial cohort,
countries, languages, accessibility needs and willingness to pay before packaging.
The current service is a single-owner private pilot; a multi-user subscription
service is not implemented or validated.

## Document structure

Maintain these distinct artifacts as the service matures:
1. **Service description:** available features, supported devices, limits,
   dependencies and honest user-facing expectations.
2. **Service-level agreement (SLA):** only approved measurable commitments,
   coverage, measurement, incident/support process and remedies.
3. **Subscription schedule:** entitlements, usage rules, prices, billing model,
   changes, cancellation and what happens to retained data after downgrade/exit.

This blueprint is their initial common specification. Customer terms and privacy
information require their own publication review; an SLA does not substitute for
them. Legal jurisdiction, contracting entity and applicable customer protections
remain unresolved. No legal compliance or enforceability is asserted here.

## Personal-release priority update — 2026-11-04

The owner has prioritized a private API-backed conversation and essential knowledge
cutover within a one-week planning horizon. Customer subscription/SLA launch is
deferred behind that personal release. The new [conversation source candidate](../daily/CONVERSATION.md)
is not a deployed service promise; the baseline below describes the previously
reviewed main revision. New explicit conversation retention is separate from
Daily's seven-day check-in history.

## Evidence baseline

Source inspected at main commit
[0501c74](https://github.com/Stoqnist/chatgpt-library/commit/0501c74d480ac38fc7cfa3c02d93ef74ce85a07a),
which merged PR #126. Owner reports deployment/testing; live image identity,
database state, restore performance and service availability were not measured.

| Area | Current verified source behavior | Gap before a subscriber promise |
| --- | --- | --- |
| Text capture | Guided answers limited/cut to 900 characters; review/API limit 4,000 | Eliminate silent loss, validate limits and real-device behavior |
| Drafts | Memory-only; reload/lock loses unsent text | Private recovery, expiry, deletion and lock behavior |
| Submitted reports | SQLite stores prompt/time/status/result, including failures; seven-day purge on state retrieval | Separate durable report lifecycle from plan attempts; retention policy and recovery tests |
| Continuity | Each plan uses current report; specialists get selected excerpts | Scoped historical retrieval, provenance and correction handling |
| Planning | Bounded AI routing and specialist advice; failures can withhold output | Monitor completion and usefulness separately; recover without bypassing grounding |
| Usage | 20 submissions per rolling 24 hours; up to five model calls per check-in | Define billable units, retry policy and cost controls; current cap is not a priced entitlement |
| Billing | Owner supplies an OpenAI project API key | Decide included usage versus bring-your-own-key; no subscription billing proven |
| Voice | Device keyboard dictation; browser speech synthesis; no Daily audio recording | Supported-device matrix and honest fallback; cannot guarantee words never delivered by device |
| Calendar | Optional read-only primary free/busy for relevant Planning work | Permission lifecycle, provider failure handling and tenant isolation |
| Other integrations | No Gmail, inventory, bank or Library connector access in Daily | Separately scoped implementation and user authorization |
| Customer service | Single-owner pilot | Account lifecycle, isolation, billing, support ownership and incident operations |

Evidence links: [UI](../daily/static/index.html),
[guided assembly](../daily/static/morning.js), [server](../daily/app.py).
These are implementation facts, not uptime evidence or guarantees.

## Commitment design

Use three explicit states for every commitment:
- **Observed capability:** verified behavior at a named revision/environment.
- **Internal objective (SLO):** a measured target used to improve operations.
- **Customer commitment (SLA):** an approved obligation with defined measurement
  and remedy. Never automatically promote an SLO into an SLA.

Suggested register below; all numeric targets and support times remain TBD.

| Measure | Proposed measurement | Evidence needed before committing |
| --- | --- | --- |
| Availability | Successful scheduled synthetic authenticated save/read checks divided by eligible checks in a defined monthly window | Monitoring coverage, incident history, precise endpoint/region and outage definitions |
| Accepted-report integrity | Exact round-trip source/version comparison for synthetic fixtures; confirmed loss/alteration incidents tracked separately | Transactional save acknowledgment, encoding tests, recovery and migration tests |
| Plan completion | Valid eligible attempts reaching a usable completed result / eligible attempts | Instrument failures, partial results, no-action results and intended safety interruptions separately |
| Plan latency | p50/p95 time from accepted attempt to terminal result, with timeout rate | Representative device/network/provider measurements and sample counts |
| Support response | Time from received support case to first meaningful human response within published coverage | Named operator, channel, timezone, working hours and incident severity rules |
| Recovery | Demonstrated restore time and data-loss window in isolated drills | Backup schedule, access controls, successful restores, explicit RTO/RPO targets |

Availability must not hide planning failures behind a healthy landing page.
Report missing monitoring periods as unknown. Declare maintenance and dependency
treatment explicitly; also show end-to-end customer impact rather than excluding
all provider failures. Do not promise 99.9% uptime, zero data loss, instant support,
perfect transcription, clinical outcomes or guaranteed AI accuracy without evidence.

For capture, the proposed acceptance contract starts at text the application
actually receives. It cannot recover speech that OS dictation never delivered.
Show separate states for draft saved, report accepted, plan processing and plan
failed. Never imply a successful save solely because text is visible on screen.

## Proposed customer agreement outline

Before publication, fill and approve:
- Service identity, eligible subscriber group, covered plan/version and effective date.
- Supported operations/devices/languages and explicit usage/size limits.
- Availability and processing commitments, calculation windows, monitoring source,
  maintenance notice and narrowly defined exclusions.
- Support channel, service hours/timezone, severity definitions, acknowledgment
  target and update cadence; distinguish response from resolution.
- Incident communication and report/draft recovery behavior.
- Retention, export, correction, deletion and backup expiry; identify AI/provider
  processing and responsibilities without claiming unverified provider behavior.
- Remedies and eligibility/claim process for missed commitments, reviewed for
  operational affordability and applicable customer rights.
- Plan changes, downtime notices, version changes, termination and data exit.
- Escalation contact, review cadence and approval owner.

Customer copy should state limitations plainly, without making the user understand
internal coordinators, handoffs, token budgets or database architecture.

## Subscription strategy

Start with one validated paid offering after a bounded pilot, rather than three
unproven tiers. The following are packaging hypotheses, not announced products.

| Stage | Intended value | Possible differentiation | Entry gate |
| --- | --- | --- | --- |
| Private pilot | Validate reliable natural check-ins | Explicit test scope and bounded usage | Capture/flow acceptance and transparent limits |
| Core subscription | Dependable check-ins and understandable history | Published processing allowance and retention | Account isolation, billing/exit, tested recovery and staffed support |
| Extended plan, later | Deeper history, trends and selected integrations | Higher capacity, longer chosen retention, optional connectors | Proven analytics, permission lifecycle, cost and support capacity |

Basic privacy, evidence integrity, corrections and honest failure reporting belong
in every plan. Do not sell them as premium safeguards. Capacity and convenience
may differ; do not imply higher prices guarantee more accurate medical judgments.
Memory/trends may be advertised only after historical retrieval is operational.

Measure model cost per accepted report and per successful plan, retries/failures,
storage/backup cost, hosting, support time and payment overhead before pricing.
Decide trial duration, usage rollover, overage behavior, currency/tax presentation,
downgrade/retention transitions and cancellation. Prefer a visible hard allowance
over surprise overage charges for the initial offering. Prices remain undecided.

## Analytics and knowledge-base alignment

Keep original reports distinct from extracted observations and generated advice.
Each derived observation references a report/version, report time, extraction
version and uncertainty; corrections supersede interpretations without silently
rewriting the original. Explicit test scenarios must not contaminate personal trends.
Do not convert qualitative mood into invented numeric ratings.

The dashboard should expose data coverage, source details and corrections.
Relevant historical excerpts may inform the appropriate specialist, but Daily
must not create competing canonical health or inventory records. Register storage
and ownership decisions in shared architecture before connecting those records.

## Delivery and publication gates

1. **Now:** record limitations, agreed product priorities and this blueprint.
   No customer-facing guarantees or prices become active.
2. **Capture release:** remove loss paths, add designed private recovery, test
   real iPhone dictation and failure states; record deployed evidence.
3. **Instrument and observe:** measure save success, plan outcomes/latency,
   dependency failures, cost and restore drills over a declared representative
   period. Select SLOs from evidence, not marketing preference.
4. **Subscriber readiness:** validate intended cohort; implement account isolation,
   account lifecycle, permission handling, billing/exit and support operations.
   Review data policy and customer documents for the actual operating market.
5. **Customer publication:** approve a dated service description, plan schedule
   and achievable SLA, with contact, measurement, remedies and change process.
   Only advertise capabilities that passed their gates.
6. **Ongoing:** review incidents, usage costs and commitment compliance; update
   versioned documentation and give required customer notices before changes.

Next design decisions: initial cohort; draft storage/expiry; chosen report
retention; included-model-cost versus bring-your-own-key; operator support hours.
Resolve these when implementing the dependent slice, without blocking P0 loss fixes.

See [development roadmap](v2-development-roadmap.md) for accepted priority and
acceptance checks. This document does not authorize deployment, external actions,
new data collection, additional model spending or commercial launch.
