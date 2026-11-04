# Private conversation foundation

Status: source candidate, not a completed V2 release or verified deployment.

## Scope

A single-owner ongoing conversation at `/daily/chat`, using the existing access
code, server-held API key, Responses provider and configured model. The Daily
check-in and optional Calendar integration remain separate. This assistant has
no tools or external-account access and cannot perform development, browse,
update canonical records, send messages or schedule events. It does not inherit
ChatGPT history, memory, subscriptions, custom GPTs or connectors.

This slice adds:
- Exact saved messages and replies, with accepted/running/completed/failed/
  interrupted states. Provider failure does not erase the accepted message.
- Explicit Save draft and Save background actions. They return a server save
  acknowledgment; concurrent stale edits are rejected by revision. Unsaved text
  is still vulnerable to reload, session expiry or device loss. No browser storage.
- One bounded context note written by the owner, not extracted model memory.
  No existing canonical records are migrated or duplicated automatically.
- Recent conversational context with explicit omitted-history counts and stored
  input provenance (background snapshot, prior turn IDs, model and local time sent).
- Export and application deletion, phone dictation through the keyboard, optional
  browser read-aloud after a tap, and a no-audio-input fallback.

## Storage and privacy contract

New `chat_turns` and `chat_notes` tables share the existing private SQLite file.
Conversation messages and explicitly saved drafts/background remain until the
owner deletes the conversation. The page states this before use. Daily check-ins
retain their existing seven-day policy; Daily Clear history does not erase chat.
Conversation deletion removes all chat messages/background/drafts from application
state but cannot erase filesystem remnants, existing backups or provider records.
Lock revokes the session and clears visible private data; saved chat remains.

Private file permissions are not encryption at rest. No personal record, API key,
conversation export or screenshot belongs in public Git. All private routes reuse
session protection; mutations require the exact Origin and CSRF token. Recognizable
credentials are rejected before saving or model submission, but detection is not
comprehensive. Never store credentials in conversation or background notes.

Each model call receives the current message, owner-written background, bounded
recent exchanges and current local time. There is no automatic access to other
conversations, Daily history, Drive, Yandex, Calendar or canonical domain files.
The existing provider uses `store:false`; this is not a claim of zero provider
retention. See OpenAI's [conversation-state](https://developers.openai.com/api/docs/guides/conversation-state)
and [data controls](https://developers.openai.com/api/docs/guides/your-data) documentation.

## Bounds and failure handling

- Chat message/draft: 12,000 Unicode code points. Background: 4,000.
- Earlier context: newest contiguous exchanges fitting 24,000 characters. Older
  exchanges remain stored/exportable but are not silently represented as recalled.
- UI shows the latest 50 exchanges; export contains all saved exchanges.
- One provider call per chat message, using the existing 1,100 output-token cap.
  Long/incomplete model responses fail visibly; no automatic paid retry.
- Shared rolling 24-hour allowance: 20 chat submissions/check-ins combined.
  Daily may use up to five calls per submission; chat uses one. This is not a
  monetary limit. Provider billing/model access must be checked independently.
- Shared single active job; request UUIDs deduplicate transport retries. A changed
  message cannot reuse an accepted ID. Restart marks in-flight work interrupted
  without replay. An explicit follow-up is a new charged attempt.
- Guided Daily input no longer silently slices answers or uses HTML maxlength;
  the existing Daily 4,000-character processing limit is visibly enforced without
  deleting the input. The new chat supports longer messages. Guided drafts remain
  memory-only and are not automatically moved into chat.

## Before personal cutover

1. Pass offline Python/Node checks and CI production-image tests at the exact SHA.
2. Rebuild the demo proxy as well: its request-body ceiling changes from 16 KiB
   to 192 KiB for Unicode chat payloads; the application keeps per-endpoint
   limits (160,000 bytes for chat, 16,000 otherwise). Build a pinned candidate; use the existing deployment's isolated smoke test,
   fresh consistent SQLite backup, runtime UID permissions and image rollback.
   Do not copy a live SQLite file without a consistent backup method.
3. Deploy using existing operator access; verify `/daily/chat`, unauthorized
   state/export 401, rejected bad-Origin/CSRF writes, and existing Daily behavior.
4. In an explicitly initiated small API canary, verify model access/billing,
   a factual follow-up about a synthetic first message, saved draft after reload,
   failed/limited response handling, export, delete, and lock/unlock on iPhone.
5. Before importing real records, choose the essential knowledge set, preserve
   source paths/versions and canonical ownership, and verify retrieval/correction.
   A manual background note alone does not fulfill the full knowledge requirement.
6. Configure an encrypted off-server backup destination with separate recovery
   key handling and perform a restore drill. Drive/Yandex capacity and access are
   unverified; no cloud synchronization or backup is installed by this change.

Schema changes are additive. The previous image ignores the chat tables, so image
rollback keeps chat data but removes the chat UI. Avoid restoring an older database
over newer messages unless intentional data loss has been assessed. No deletion
or migration of existing canonical records is part of this release.

## Remaining V2 release work

Essential knowledge import/retrieval with provenance and corrections; off-server
backup/restore; model quality/cost acceptance; cross-session resume UX; optional
multiple conversations/search; scoped tool adapters with explicit authority.
Analytics, Gmail, subscription billing and customer SLAs follow the personal
cutover. The experimental orchestration branch is not bulk-merged by this slice.
