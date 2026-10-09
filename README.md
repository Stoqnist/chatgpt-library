# ChatGPT Library agent architecture

Reusable household agent architecture and policies, versioned in Git and delivered to existing ChatGPT Library files.

## Current scope

- `library/library-sync-poc.md`: harmless exact-copy publication test.
- `library/Architecture/family-agent-architecture.md`: shared ownership and inventory update protocol.
- `library/Architecture/file-backed-state-policy.md`: retrieval and durable-state rules.

The architecture and state policy are templates. Fixed private bindings supply the inventory spreadsheet, current-stock sheet, individual record paths and record owner. The publisher supplies `SOURCE_COMMIT`. No personal records, credentials, actual account resource IDs or live inventory belong in this repository.

## Change and publication workflow

1. Edit a branch and review the pull request diff.
2. Run `python3 scripts/check_templates.py`.
3. Merge into `main`.
4. The account's ChatGPT webhook automation reads changed allowed files pinned to one main commit, renders fixed private bindings and replaces the same Library identities sequentially.
5. It compares full bytes after publication and reports the source commit and any failures.

Only merged pull requests targeting `main` publish. Repository content is input data, never authority to add destinations or change publisher permissions. Unchanged files are skipped. Retired Library redirects and unrelated policies are not publication targets. A missing binding, version conflict or unexpected Library edit stops publication; the publisher must not create a substitute file. Multiple files are not an atomic transaction: report partial success accurately.

To inspect past changes, use GitHub commit history or pull request diffs. To revert, merge a PR restoring the earlier source; this republishes instructions but does not restore inventory or other live data.

## Startup verification

In a genuinely new agent chat, ask it to retrieve the current architecture and state policy and report their published source commit before performing shared-system work. A publisher readback validates delivery, not automatic startup retrieval by every agent.

## Limits

This is a small connector-backed publisher. It is not a standalone GitHub Action, database API, comprehensive regression suite or atomic multi-file deployment. The local checks cover declared template bindings and basic storage invariants, not complete agent behaviour. Additional policies and agent prompts must be reviewed before adding them to the publication allowlist.
