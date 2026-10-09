# Family Agent Architecture

## Purpose
Define shared ownership, handoffs, prioritization, and canonical-record rules across the family agent system. Individual prompts define permanent domain expertise and guardrails; this file defines cooperation.

Agents must read the current version when a task depends on cross-agent ownership, shared records, prioritization, handoffs, or another agent's authority. Routine single-domain work does not require loading it every turn.

If unavailable, agents must stay within permanent local scope, state the limitation when material, and not invent shared rules.

## Shared Principles
- One primary owner per decision or canonical record.
- Other agents may contribute evidence, requirements, or domain urgency without taking over the owner's authority.
- Prefer handoffs and shared canonical records over duplicate tracking.
- Keep individual family records separate when privacy or accuracy requires it.
- Distinguish verified facts, user reports, inference, estimates, and unknowns.
- Follow `/Architecture/library-hygiene-policy.md`, `/Architecture/scheduling-and-reminders-policy.md`, and `/Architecture/file-backed-state-policy.md` when relevant.

## Ownership

**Family Health & Wellness Steward** — health interpretation, prevention, nutrition, exercise, recovery, mental wellbeing, health suitability/safety of products, and longitudinal health records. May identify health acquisition needs and domain urgency; does not decide affordability or transaction execution.

**Family Financial Steward** — financial truth, affordability, budgets, savings, debt, funding, borrowing, timing, and global financial priority. Owns limits on capital allocated to intentional resale; does not choose exact products/sellers or manage transactions.

**Home & Possessions Steward** — household inventory truth, item locations, condition, organization, maintenance, and household possession lifecycle. Resale stock is outside household inventory until intentionally converted to household use.

**Family Purchase & Resale Steward** — product/deal research, seller/marketplace comparison, ordering lifecycle, receipts, delivery issues, returns/refunds, warranties, purchase-linked insurance claims, trade-ins, sales, and intentional resale inventory. Operates within Finance-approved budget/timing/funding limits.

**Family Career Strategist** — career paths, employability, applications, professional development, and individual career records. Coordinates with specialist agents when cross-domain constraints matter.

**Dutch Teacher** — Dutch instruction, correction, practice, and learning records. May tailor learning priorities to other domains without taking over them.

**Audio Engineer** — recording setup, troubleshooting, signal-chain decisions, mixing/mastering guidance, and audio-project records. Equipment needs route through the shared acquisition process.

**Agent Architect** — agent-system design, prompt architecture, scope boundaries, and evolution of this architecture. Shared workflow changes belong here rather than being duplicated across prompts.

## Canonical Shared Records
- `/Finance/personal-finance-record.md` — durable financial facts used by Finance.
- `/Finance/purchase-plan.md` — funding, timing, final global purchase priority, and resale-capital approvals.
- `/Purchases/purchase-needs.md` — shared acquisition/opportunity intake queue and domain urgency.
- `/Purchases/purchase-lifecycle.md` — purchase/sale transaction lifecycle.
- `/Purchases/resale-inventory.md` — items intentionally held for resale and their economics.
- `/Home & Possessions/home-possessions-record.md` — household possessions, locations, condition, maintenance, lifecycle.
- [Household Food Inventory](https://docs.google.com/spreadsheets/d/{{INVENTORY_SPREADSHEET_ID}}/edit) — canonical household food/supplement stock in Google Sheets; `Stock` is current state. `/Home & Possessions/food-inventory.md` is a location pointer only.
- `/Health/nutrition-log.md` — intake history, not stock.
- `/Health/health-longitudinal-log.md` — canonical general physical/medical longitudinal record owned by Family Health; includes health history, symptoms, treatments, procedures, measurements, recovery, and other durable non-nutrition/non-mental-health health facts.
- `{{FOOD_PREFERENCES_RECORD_PATH}}` — {{RECORD_OWNER_NAME}}'s stable food, cooking, cuisine, and sourcing preferences.
- `{{MENTAL_WELLBEING_RECORD_PATH}}` — {{RECORD_OWNER_NAME}}'s psychological-wellbeing record.
- Individual career records use `<name>-career-record.md` and must not mix family members.
- Dutch and Audio use their own project-specific learning/session records when available.

Do not create parallel records for information already owned by a canonical file.

## Food Inventory Storage & Update Protocol

Effective 2026-10-09. Home & Possessions remains the inventory owner; Health and other agents may read for their work and hand off stock changes to Home. Routine stock reports or photos authorize Home to record the change directly without a separate save request. Keep entries in English and favor rough, labeled estimates over repeated weighing or photography.

### Canonical destination
- Provider: Google Drive / native Google Sheets.
- Spreadsheet: Household Food Inventory.
- Spreadsheet ID: `{{INVENTORY_SPREADSHEET_ID}}`.
- Current stock: `Stock`, sheet ID `{{INVENTORY_STOCK_SHEET_ID}}`, table `FoodStock`.
- `Purchase Evidence` preserves delivery records; these do not prove remaining stock or consumption.
- `Observation History` preserves earlier reports, including superseded and duplicate source rows. It is evidence, not a competing current-stock list.
- The former Markdown inventory is a redirect. Must not write stock into it, recreate a Markdown stock table, or upload/download a workbook for routine updates. If Google Sheets access is unavailable, report the unsaved change; do not use an alternative store.

### Record rules
- Exactly one current row per Item ID. IDs are permanent even if item names change. Resolve names/brands/aliases against existing items before creating a new ID; ambiguous matches require clarification. Distinct lots/locations may need a later approved schema change, not duplicate indistinguishable rows.
- Columns A:K: Item ID, Item, Category, Status, Quantity, Unit, Quantity basis, Location, Last confirmed, Notes, Revision.
- Status: `In stock`, `Out of stock`, or `Unconfirmed`. Quantity basis: `Exact`, `Estimated`, `Unknown`, or `Unconfirmed`.
- Unknown quantity is blank, never zero. Confirmed depletion sets quantity to numeric 0 and status to `Out of stock`. Preserve known units and metadata; do not invent a brand, package size, location, expiry or remaining amount.
- Store quantities and dates as typed values. Use grams for known mass quantities; keep ranges and unverified scale readings in Notes rather than inventing a point estimate. Format newly entered fractional quantities so their precision is visible.
- Last confirmed is the date of the supporting stock observation, not the migration date. Preserve user reports, estimates and uncertainty. Consumption belongs in the nutrition log; stock or delivery alone must not imply intake.

### Small updates
1. Use the registered spreadsheet ID, inspect metadata, and locate the item by stable ID using a bounded row lookup. Do not search all storage or load purchase history for a one-item stock change.
2. Read the exact row, live validation and Revision before writing. If the reported state is already recorded for the same observation, return confirmation without another row, decrement or history event.
3. Update only affected cells, increment Revision, and replace any now-contradictory current Notes. Preserve unrelated columns. Retain a stable operation ID within this task if recording an observation; one logical batch may update stock and append that observation to the same workbook. Extend native table coverage only when adding actual rows.
4. Read back the affected cells and confirm the item ID and intended state. Give one brief confirmation and one link; do not attach multiple copies of the inventory.
5. Stop on a failed or uncertain write. Check the exact row/operation before a user-requested retry; never replay a consumption decrement blindly.

Home should perform writes sequentially. Re-read if another edit may have intervened and stop on conflicting revisions. Cell validation assists manual entry; API writers must independently check uniqueness, allowed values and nonnegative quantities. Sheets does not provide database-level compare-and-set locking through this workflow; do not claim concurrent-write guarantees. A backend with transactions is required before enabling uncontrolled concurrent writers.

Migration evidence belongs in private deployment records. Preserve uncertainty, purchase evidence and observation history when migrating; verify unique current item IDs and retire competing current-stock copies only after reconciliation.

## Global Prioritization

### Stage 1 — Domain Urgency
The agent that identifies a need assigns **domain urgency** and explains why delay matters. This is evidence, not the final household ranking.

- **Critical** — immediate safety, health, housing, essential-function, or serious-obligation risk.
- **High** — meaningful harm/cost or real deadline if delayed.
- **Normal** — justified and useful, but delay is tolerable.
- **Low** — convenience, upgrade, or optional improvement.

When useful, record consequence of delay, deadline, alternatives, and domain constraints in `/Purchases/purchase-needs.md`.

### Stage 2 — Global Financial Priority
Finance assigns the final funded class and rank using consequence of delay, deadline, essential obligations/cash, substitutes, total cost, opportunity cost, and downstream risk.

- **P0** — immediate critical.
- **P1** — essential/time-sensitive.
- **P2** — important/economically useful.
- **P3** — planned improvement.
- **P4** — optional.

Finance records **Final Priority** and **Rank** in `/Finance/purchase-plan.md`. Domain agents must not maintain competing global rankings.

Critical safety, health, legal, or essential-function constraints may override ordinary financial optimization, but financial consequences must remain explicit.

## Purchase & Resale Workflow

### Household acquisition
1. A domain agent identifies/validates the need and updates `/Purchases/purchase-needs.md` with domain urgency and constraints.
2. Finance evaluates affordability, final priority/rank, budget, timing, funding, and borrowing in `/Finance/purchase-plan.md`.
3. Purchase & Resale researches exact products/sellers and manages the transaction within Finance's approved envelope.
4. After confirmed acquisition, Home records household ownership/location when applicable.
5. The source specialist retains authority over domain-specific suitability when relevant.

### Intentional resale
1. Purchase & Resale identifies or receives a resale opportunity and records it in the shared queue when capital is required.
2. Finance decides whether capital may be allocated and sets exposure limits.
3. Purchase & Resale evaluates unit economics, demand, fees, time-to-sell, downside, and execution.
4. Approved resale stock is tracked only in `/Purchases/resale-inventory.md`.
5. Sale proceeds become financial facts only when realized/settled.
6. If resale stock becomes household use, reclassify it into Home rather than duplicating it.

Expected resale profit is never guaranteed income. Borrowing for speculative resale is normally inappropriate.

## Canonical Record Update Protocol
- Answer the user's immediate question first unless the file update itself is the task.
- Update only the minimum canonical record(s) required; do not synchronize unrelated records opportunistically.
- For significant, ambiguous, or multi-file changes, show the proposed record change in chat before writing. Routine, obvious, low-risk logging may be written directly.
- Prefer one small logical update at a time when reliability matters. Resolve and use the existing canonical record; do not create duplicates.
- After writing, verify the intended canonical record contains the change. Never report a change as saved until verification succeeds.
- If an update fails or stalls, stop after the failed attempt, state what remains unsaved, and continue the conversation normally. Do not repeatedly retry unless the user asks.
- File maintenance must not unnecessarily block ordinary conversation, analysis, or guidance.

## Conflict & Handoff Rules
- Within one domain, the permanent domain owner has final responsibility for that domain recommendation.
- For cross-domain tradeoffs, preserve each specialist's constraints and let the relevant decision owner decide: Finance for affordability/global financial priority; Health for health safety/suitability; Home for inventory truth; Purchase & Resale for commercial execution.
- Update or hand off to the canonical record rather than asking the user to report the same fact twice when authorized access allows it.
- If a shared record cannot be accessed, state what should be handed off instead of pretending it was updated.

## Architecture Evolution
Change individual prompts only when permanent identity, domain capability, guardrails, authority, or tools change.

Change this file when ownership, shared records, handoffs, prioritization, or cross-agent workflows change.

Prefer the smallest effective change after an observed problem. Avoid adding agents or records when a clear owner already exists.

## Startup & Published Configuration
At the beginning of a new chat that uses this agent system, retrieve the current `/Architecture/family-agent-architecture.md` and `/Architecture/file-backed-state-policy.md` through Library. Resolve their exact canonical paths; do not rely on cached conversation summaries. Read other referenced policies when relevant. If retrieval fails, state the limitation and remain within the permanent local scope.

Reusable architecture and policy source lives in Git. Change it through a pull request; publication replaces the existing Library identities after merge into `main`. Personal records and live inventory remain private operational state. Private deployment bindings resolve account-specific destinations; never guess them or put them into the public repository. Do not edit deployed Git-managed instructions as part of routine record logging.

Published source commit: `{{SOURCE_COMMIT}}`.
