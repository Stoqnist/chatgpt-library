# V2 deterministic coordinator POC

**Default status:** offline simulation; **not deployed**. The default coordinator makes no model calls, network requests or file writes. A separate opt-in adapter can call model APIs using only the verified fictional fixture, without access to bank connectors, Google Drive, inventory or remote services.

Run from this directory with Python 3.10+:

```bash
PYTHONPATH=. python3 -m v2_poc.coordinator fixtures/purchase.json
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

The test fixture represents a fictional €49.90 desk lamp receipt, a corresponding card payment, one duplicate bank-export row, and a €100 own-account transfer. Purchase & Resale, Finance and Home return structured simulated results. The coordinator deduplicates the bank payment, excludes the internal transfer, retains domain owners, and produces one result. Home does **not** mark an item possessed until physical receipt is confirmed; all write proposals are blocked from execution.

The adapter interface is `handlers[domain](evidence, prior_results) -> specialist_result`. A future real agent adapter must preserve domain allowlists, input minimization, no recursive delegation, explicit approval enforcement, idempotency preconditions, provider readback, and private-data isolation. This POC does **not** prove real multi-agent calls or provider-side concurrency safety.

See `docs/v2-orchestration-contract.md` for the proposed production contract. V1's deployed policies and services remain unchanged.

## Opt-in model-backed specialist adapter (development only)

The optional `v2_poc.agents_sdk_adapter` invokes actual OpenAI Agents SDK
`Agent` instances under the **same deterministic coordinator**. The agent
calls are individually bounded to one turn with structured outputs; tools,
handoffs, and tracing are disabled. The existing deterministic specialists
retain exclusive control over verified fixture facts, numeric calculations,
and **unexecuted** write proposals. AI findings are separately labeled
`inferred`, checked against the specialist's visible evidence IDs, and never
written to canonical records.

The default CLI above remains fully offline. The optional **billable** smoke
test needs explicit flags, an installed SDK, a separately managed API key and
fictional evidence only. It cannot use production data, bank connectors, home
inventory, deployed services or a saved chat as input. No key is stored in Git.

```bash
python3 -m pip install -r requirements-live.txt
PYTHONPATH=. python3 -m v2_poc.live fixtures/purchase.json --check-only
# Only after explicit approval to incur API charges:
read -rsp "OpenAI API key: " OPENAI_API_KEY; echo
export OPENAI_API_KEY
PYTHONPATH=. python3 -m v2_poc.live fixtures/purchase.json --allow-api-calls --model gpt-4.1-mini
unset OPENAI_API_KEY
```

If no key or SDK is available, run only the unit suite. Regression tests use a
fake SDK and make no external requests:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

**Status:** adapter code and mocked integration tests; a successful paid live
model-call smoke test is **not yet verified**. This proof of concept is not a
production multi-agent service and cannot call ChatGPT custom GPTs directly.

### Safety, costs and CI

The billable CLI accepts **only the committed synthetic fixture**, checked by
absolute path and SHA-256. The `--check-only` preflight makes zero API calls and
prints whether the optional SDK and key are configured; it never prints a key.
Each model call uses one turn, no tools/handoffs, disabled tracing, and
structured results with at most three findings and three questions. The fixture
requests three specialists. These limits reduce exposure but **are not a token
or monetary cap** (network retries and billing policies remain provider-controlled). Verify project-level API limits
before authorizing live traffic. Never put a key in a GitHub commit or chat.

GitHub PR CI installs the pinned SDK and checks its offline construction/schema
interfaces; no API secrets are supplied to the workflow and no model calls
are made. A green CI run confirms local compatibility, **not** a live API test.

### Live-smoke review follow-up

The first real three-specialist fixture run completed successfully without writes. It
also showed repeated AI paraphrases and two equivalent questions about possession.
The coordinator now consolidates strongly overlapping questions, and the adapter
filters specialist questions already represented in the deterministic baseline.
Model instructions explicitly prohibit treating equal amounts as proof of a
receipt-to-bank transaction match. These guardrails improve presentation but
cannot guarantee that every unsupported AI claim is caught; provenance and
human review remain required. No production permissions have changed.

### Model-output validation gate (V2 POC)

Typed issue codes now replace free-form model-authored findings and questions as
user-facing AI contributions. A source ID merely establishes where a claim
purports to come from; it does not establish that the content is true. The
read-only validator independently checks each issue code against domain-owned,
scoped fixture evidence. Only policy-authored follow-up questions from accepted
codes are allowed into the consolidated result. Model-generated narrative is
quarantined, counted under `model_review.rejected_model_items`, and never
promoted as verified evidence or as record writes. The result preserves the
initial deterministic findings and unexecuted proposals.

Implemented issue codes in this pilot are `delivery_unconfirmed` and
`receipt_payment_link_unverified`. A matching receipt amount is *not* proof
of a shared transaction; an explicit shared identifier suppresses the issue.
Rejected model output may require human review and must not silently authorize
a domain action. This bounded gate does not establish generalized factual
verification, safe ingestion of arbitrary personal records, or VPS readiness.

### Seeded golden-journey benchmark (development, offline)

Run the fixed 24-case suite without an API key or model calls:

```bash
PYTHONPATH=. python3 -m v2_poc.benchmark --cases 24 --seed-start 100
```

Each seeded synthetic household purchase varies item identity, EUR amount,
receipt/transaction IDs and source row order. The test oracle is derived from
fixture parameters, rather than reading the coordinator's computed total.
Cases assert unique spending, transfer exclusion, duplicate detection,
correct specialist ownership, explicit uncertainty, unexecuted write proposals,
and read-only behavior. Each case also checks invariance under item renaming,
reordered evidence and another overlapping bank-export row.

The command prints a JSON report with case-level failures, seed, source commit
(if passed in `GITHUB_SHA`), timing, safety count, and explicitly zero API cost.
Use the **same fixed seeds** to compare versions; separately use alternate seeds
to discover failures. Timing is environmental and does not support strict
performance comparisons across unlike machines. This is a deterministic
coordinator benchmark, **not** a live-model quality/cost benchmark.
