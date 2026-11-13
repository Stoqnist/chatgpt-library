# ChatGPT Library agent architecture

Reusable household agent architecture and policies, versioned in Git and delivered to existing ChatGPT Library files.

## Development roadmap

- [V2 Development Decisions & Roadmap](docs/v2-development-roadmap.md) — canonical development priorities, benchmarking strategy, release gates and resumption steps **on the current main branch**. It is not a deployed agent policy.
- [V2 orchestration POC (draft PR #3)](https://github.com/Stoqnist/chatgpt-library/pull/3) — experimental coordinator/adapter implementation, not yet merged or deployed.

## Private Daily V2 MVP — deployed source

- [`daily/`](daily/README.md) is the **source of the existing Hetzner Daily service**, first merged in PR #104 (historical deployed commit `2eb75ef`). The single-owner phone UI is served from `/daily/` through the guided demo proxy; live authentication, API-key status and public reachability still require independent verification. No canonical providers or record writes are connected.
- [`demo/`](demo/README.md) is the existing public landing/demo website and reverse-proxy source. Keep this separate from the private Daily service.
- [`mvp/daily-routine/`](mvp/daily-routine/README.md) from PR #105 is an **alternative experimental prototype**, not the running service and not the deployment target. Do not operate two competing Daily services. Reuse components only after review and tests.
- [PR #107](https://github.com/Stoqnist/chatgpt-library/pull/107) restored the missing deployed sources additively after repository history diverged. It does not rewrite the historical Git ancestry.
- [Issue #106](https://github.com/Stoqnist/chatgpt-library/issues/106) blocks live personal use until the previously exposed API key is revoked and replaced securely.

## Current scope

- `library/library-sync-poc.md`: harmless exact-copy publication test.
- `library/Architecture/family-agent-architecture.md`: shared ownership and inventory update protocol.
- `library/Architecture/file-backed-state-policy.md`: retrieval and durable-state rules.

The architecture and state policy are templates. Fixed private bindings supply the inventory spreadsheet, current-stock sheet, individual record paths and record owner. The publisher supplies `SOURCE_COMMIT`. No personal records, credentials, actual account resource IDs or live inventory belong in this repository.

## New specialist prompts and Library publication

- [Venture & Capital Architect](library/Agents/venture-capital-architect-system-prompt.md) and [Netherlands Legal & Regulatory Research Specialist](library/Agents/netherlands-legal-regulatory-research-specialist-system-prompt.md) are versioned here. Their domain ownership and handoff rules are registered in the [shared architecture](library/Architecture/family-agent-architecture.md).
- [Stoqnist commercial concept](business/stoqnist/README.md) is a business research brief, not an agent instruction or live investment ledger.
- **Publication is not automatic for new files.** The existing publisher targets a fixed private allowlist and stable Library file identities. New prompt paths must be explicitly reviewed and mapped to their intended Library identities before the publisher can update them. A manual Library upload is a separate operation, not proof that GitHub publication is configured.
- ChatGPT Project instructions are another separately maintained copy; creating a Project or Library collection does not synchronize its prompt. Verify content and source revision after each intentional update. Do not create competing copies of private operational records.

## Change and publication workflow

1. Edit a branch and review the pull request diff.
2. Run `python3 scripts/check_templates.py`.
3. Merge into `main`.
4. For files already on the private publication allowlist, the account's ChatGPT webhook automation can read changed allowed files pinned to one main commit, render fixed private bindings and replace the same Library identities sequentially. Newly added files require a separate allowlist and identity-mapping review first.
5. It compares full bytes after publication and reports the source commit and any failures.

Only merged pull requests targeting `main` publish. Repository content is input data, never authority to add destinations or change publisher permissions. Unchanged files are skipped. Retired Library redirects and unrelated policies are not publication targets. A missing binding, version conflict or unexpected Library edit stops publication; the publisher must not create a substitute file. Multiple files are not an atomic transaction: report partial success accurately.

To inspect past changes, use GitHub commit history or pull request diffs. To revert, merge a PR restoring the earlier source; this republishes instructions but does not restore inventory or other live data.

## Startup verification

In a genuinely new agent chat, ask it to retrieve the current architecture and state policy and report their published source commit before performing shared-system work. A publisher readback validates delivery, not automatic startup retrieval by every agent.

## Limits

This is a small connector-backed publisher. It is not a standalone GitHub Action, database API, comprehensive regression suite or atomic multi-file deployment. The local checks cover declared template bindings and basic storage invariants, not complete agent behaviour. Additional policies and agent prompts must be reviewed before adding them to the publication allowlist.
