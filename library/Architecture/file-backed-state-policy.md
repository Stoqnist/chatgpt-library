# File-Backed State Policy

**Purpose:** Make registered canonical records—not chat history or model memory—the durable source of truth for the family agent system. The filename is retained for existing prompt references.

## 1. Durable State Lives in Canonical Records
Any information that should survive beyond the current conversation must be stored in the canonical record registered by `/Architecture/family-agent-architecture.md`. Library files remain the default for instructions and narrative records. Structured state may use a specifically registered connected spreadsheet or database; this does not authorize an agent to choose a new store on its own.

Examples include personal records and profiles; inventories and logs; financial facts and plans; health history and longitudinal tracking; career history and progress; learning progress; purchase/resale state; preferences that materially affect future work; decisions, commitments, and durable project configuration.

Chat history is not a durable database.

## 2. Do Not Rely on Cross-Chat Memory
Agents must not use account memory, remembered prior chats, conversation summaries, or inferred historical context as authoritative state.

If a fact is not present in:
1. the user's current message;
2. an authorized canonical record; or
3. current connected/live data retrieved for the task;

then treat it as unknown.

A remembered detail may prompt retrieval of the relevant canonical file, but it must not be used as the factual basis for a decision unless independently confirmed by an authorized source.

## 3. Current Chat Is Temporary Working Context
Agents may use information provided in the active conversation to complete the current task.

When information from the current chat is materially useful for future sessions, update the appropriate canonical record during the task when authorized and possible. Do not assume the conversation will remain available later.

## 4. Persistence Before Closure
When a conversation produces durable changes—new facts, decisions, preferences, inventory changes, financial changes, health updates, progress, or workflow state—persist those changes to the canonical record before treating the work as complete when tool access allows it.

If the canonical record cannot be updated:
- state what durable information still needs to be persisted;
- do not claim it was saved;
- avoid creating a competing ad-hoc record.

## 5. Retrieval Before Recall
For continuity questions such as “what do we know?”, “continue where we left off”, or “what is my current status?”, retrieve the relevant canonical record first when available.

Prefer the newest canonical record over remembered conversation content. When records conflict, surface the conflict instead of resolving it from memory.

## 5A. Canonical Path Resolution
Slash-prefixed canonical paths named in architecture or policy files, such as `/Health/...`, are Library paths unless the source explicitly identifies another provider. Resolve them through the Library first; do not substitute Google Drive or another connector merely because it is connected.

When the canonical path is already known, locate that existing Library file, use its returned file/library identifier for reads or updates, and verify the same canonical file after writing. Do not ask the user to provide a path that the architecture already defines. If the named Library file is not accessible, state that specific limitation and do not create a duplicate.

## 5B. Registered Structured Stores
For household food/supplement inventory, follow the Google Sheets destination and update protocol in the current family architecture. `/Home & Possessions/food-inventory.md` is a redirect only. Resolve the registered provider and ID directly; do not fall back to stale Markdown copies or re-import a workbook for routine cell updates. Verify the changed row after writing. Keep unknowns, stable IDs and current state distinct from historical evidence.

## 6. Canonical Source Discipline
Each durable fact should have one primary canonical home. Do not mirror live state across files and structured stores. Use location pointers when needed; a pointer must not contain a competing current-state table. Archive evidence and dated snapshots must be explicitly non-authoritative.

Shared architecture and ownership rules are defined in `/Architecture/family-agent-architecture.md`.

## 7. Chat Cleanup Compatibility
The system should remain functional if old chats are deleted.

Deleting a chat must not remove required operational state once that state has been correctly persisted to canonical files. Agents should design workflows so conversations can be treated as disposable working sessions after durable changes have been persisted.

## 8. Memory Independence
The architecture must not require ChatGPT Memory to function.

If account Memory is enabled, agents must still treat it as non-authoritative and verify durable facts from canonical files or current user input before using them.

## 9. Safety and Privacy
Do not persist passwords, PINs, recovery codes, full payment-card numbers, authentication secrets, or other credentials in canonical records.

Store only information necessary for the project's function and follow the Library Hygiene Policy.

## 10. Versioned Instructions & Private Operational State
Reusable architecture and policies are versioned in Git and published to their existing Library identities after a pull request merges into `main`. Propose instruction changes in Git instead of independently editing the deployed copies. Keep live personal records and inventory outside the public source repository. Account-specific destinations are supplied by private deployment bindings.

For a new chat using this system, retrieve the current architecture and this policy before work that relies on the shared system. A fresh chat is not evidence that retrieval happened. If deployed content differs from the published source, report the conflict before overwriting it. Publication verifies complete rendered bytes, retains stable Library IDs, and skips unchanged content.

Published source commit: `{{SOURCE_COMMIT}}`.
