# Daily integrated conversation — source candidate

Status: merged V2 conversation foundation was owner-deployed and verified on a real
iPhone on 2026-11-04. This next revision is source-only until a separately
tested release. The private Daily service remains the single deployment.

## One Daily surface

- `/daily/` is the one primary experience for morning check-ins, previous
  check-in plans and continued conversation. The old `/daily/chat` address
  redirects to `/daily/#conversation`; it is not a second app.
- Login, Settings, API key status and logout are shared. The private chat UI
  has no editable background/system-prompt field. Agent instructions are
  application-owned and versioned, never supplied by an initial user prompt.
- If the API key is missing, Daily opens Settings and links to the official
  API key and spending-limit pages. The key belongs in the password-type
  Settings field, never a chat message, Git, screenshot or console output.
- Native keyboard dictation, edit-before-send, explicit Save draft,
  saved messages/replies, export, delete and optional tapped read-aloud remain.
  No in-page microphone, audio storage, automatic model calls or background
  transcription is added.

## Conversation coordination

Every **submitted conversation message** first goes through a model-based
coordinator. The coordinator selects zero to three currently implemented Daily
specialists (Wellbeing, Home, Planning) only when relevant; general conversation
can proceed without a specialist. Handoffs must quote exact substrings of the
latest message and reject ungrounded or high-confidence sensitive handoffs to
Home/Planning. Specialists receive only their excerpts, not earlier chat history.
Planning gets Europe/Amsterdam time context but **no Calendar access from chat**.
Wellbeing's existing conservative safety checks remain. The final coordinator
receives bounded conversation history and scoped specialist proposals, and
responds to the user in prose; it can distinguish near-term next steps from
longer-term possibilities when grounded.

This is **not** deployment of the full experimental V2 collaboration framework
or all family-agent prompts. The three existing Daily roles are the available
runtime subset. They have no tools and do not fetch, infer or update Health,
Home, Finance, inventory, Library, Drive, Yandex or other canonical records.
Suggested actions are not scheduled, accepted or executed. Previous AI replies
are not canonical evidence. The user can correct text through a new message,
but there is no verified durable action/obligation store.

Coordination uses one router call, up to three specialist calls and one final
reply call: **2–5 bounded model calls per message** (urgent interruption may use
only one). This is still one of the shared 20 submissions/check-ins per rolling
24 hours, not a monetary budget. Existing request-ID deduplication, single
active job, no automatic replay and `store:false` remain. OpenAI API spending
and availability require independent checks.

## Storage and privacy

SQLite continues to own private `chat_turns` and saved chat drafts; accepted
turns and replies remain until explicitly deleted. A 12,000-code-point message
limit and 24,000-character contiguous prior-history context bound remain. The
latest 50 exchanges are displayed; export includes the complete saved history.
Omitted-history counts are visible. Check-in history has a separate seven-day
retention rule. Logout clears visible content and revokes the session.
The old `chat_notes.context` and historical `chat_turns.context` columns are
preserved for backward compatibility and export, but no owner-written context
is included in **new** model requests and the editor endpoint is disabled.
The source patch does not delete or migrate existing user data. Export can
still contain historical notes; explicit Clear conversation removes them from
application state, not existing backups or provider retention.

Server files are private but not encrypted at rest. The existing authenticated
Origin and CSRF protections, credentials rejection, session expiry, and Cloudflare
gate remain necessary. Nothing in this change broadens provider access or
introduces autonomous writes.

## Release and acceptance gates

1. Review this PR diff; run full Python/Node, template, demo and container CI at
   the exact head SHA. Confirm no new external grants or private records.
2. Build isolated pinned Daily and demo proxy images. The proxy still requires
   the 192 KiB chat request-body allowance from the prior release.
3. Create a fresh consistent SQLite backup, preserve Compose and tunnel
   overrides, and keep both prior images available. Deploy using only the
   existing operator-approved path. A green CI run does not deploy a server.
4. Test on iPhone: unlock once, use morning check-in, continue in conversation
   without a second login, reload a saved draft, verify a benign general
   question and a grounded multi-domain action request, test export/delete,
   lock/unlock and missing-API-key guidance. Confirm routing privacy with
   synthetic text and check the bounded API cost.
5. Verify rollback and a separate encrypted off-server backup/restore before
   subscription cutover. Canonical knowledge retrieval, corrections and
   verified action storage remain distinct release gates.

Do not present this source as full ChatGPT parity, live memory integration or
deployed multi-agent execution. Its scope is one coherent Daily workflow.
