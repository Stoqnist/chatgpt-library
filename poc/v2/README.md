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
