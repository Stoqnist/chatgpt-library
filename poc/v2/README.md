# V2 deterministic coordinator POC

**Status:** simulation only; **not deployed**. It does not call model APIs, agent runtimes, bank connectors, Google Drive, inventory or remote services. It makes **zero file writes** when invoked. The fixture contains fictional data only.

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
export OPENAI_API_KEY=...  # supply privately; never commit or print the value
PYTHONPATH=. python3 -m v2_poc.live fixtures/purchase.json --allow-api-calls --model gpt-4.1-mini
```

If no key or SDK is available, run only the unit suite. Regression tests use a
fake SDK and make no external requests:

```bash
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

**Status:** adapter code and mocked integration tests; a successful paid live
model-call smoke test is **not yet verified**. This proof of concept is not a
production multi-agent service and cannot call ChatGPT custom GPTs directly.
