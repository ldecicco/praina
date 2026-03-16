# Concurrent Proposal Writing — Implementation Plan

## Goal

Enable multiple team members to edit the same proposal section simultaneously with real-time cursor presence, conflict-free merging, and live content sync — similar to Google Docs.

---

## Current State

| Aspect | Today |
|--------|-------|
| Editor | Tiptap v3.20.1 (ProseMirror-based) with markdown storage |
| Save model | Debounced HTTP PATCH every 700 ms — last-write-wins |
| Conflict handling | None — concurrent edits silently overwrite |
| Real-time infra | WebSocket already used for project chat (`RoomHub` in `project_chat.py`) |
| Content format | Markdown string in `project_proposal_sections.content` |

---

## Approach: Yjs CRDT + WebSocket Relay

**Yjs** is a high-performance CRDT library purpose-built for collaborative text editing. It has first-class bindings for ProseMirror/Tiptap (`y-prosemirror`) and a well-defined WebSocket sync protocol.

### Why Yjs over OT

- No central transform server needed — the CRDT merges automatically on every client.
- The backend only relays binary update messages and persists state — no transform logic.
- Battle-tested: used by Notion, Cargo, and many Tiptap deployments.
- `y-prosemirror` drops into Tiptap as a standard extension — minimal editor changes.

### Architecture Overview

```
 ┌──────────┐  WS (Yjs sync)  ┌──────────────┐  WS (Yjs sync)  ┌──────────┐
 │ Client A │ ◄──────────────► │   Backend    │ ◄──────────────► │ Client B │
 │ (Tiptap  │                  │  WS Relay    │                  │ (Tiptap  │
 │  + Yjs)  │                  │  + y-py      │                  │  + Yjs)  │
 └──────────┘                  └──────┬───────┘                  └──────────┘
                                      │
                                      │ debounced persist
                                      ▼
                               ┌──────────────┐
                               │  PostgreSQL   │
                               │  yjs_state +  │
                               │  content (md) │
                               └──────────────┘
```

---

## Data Model Changes

### New column on `project_proposal_sections`

```sql
ALTER TABLE project_proposal_sections
  ADD COLUMN yjs_state BYTEA;
```

- `yjs_state` — serialized `Y.Doc` snapshot (binary). The server loads this to bootstrap new connections.
- `content` (existing) — kept in sync as a markdown export of the Yjs document. Used for search indexing, PDF export, and API reads. Updated on every persist cycle.

### New table: `proposal_section_edit_sessions` (optional, for analytics)

```sql
CREATE TABLE proposal_section_edit_sessions (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  section_id    UUID NOT NULL REFERENCES project_proposal_sections(id) ON DELETE CASCADE,
  user_id       UUID NOT NULL REFERENCES user_accounts(id),
  connected_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  disconnected_at TIMESTAMPTZ,
  updates_count INT NOT NULL DEFAULT 0
);
```

Tracks who edited what and when. Purely observational — not required for sync.

---

## Backend Changes

### 1. New file: `app/services/proposal_collab_service.py`

Manages in-memory Yjs documents per section, handles persistence.

```
class ProposalCollabService:
    _docs: dict[UUID, tuple[Y.YDoc, datetime]]   # section_id → (doc, last_update)

    load_or_create(section_id) -> Y.YDoc
        # If doc in memory, return it.
        # Else load yjs_state from DB. If NULL, create new Y.YDoc
        # and seed it from the existing markdown content column.

    apply_update(section_id, update: bytes) -> None
        # Apply a Yjs binary update to the in-memory doc.
        # Mark dirty for persistence.

    get_state_vector(section_id) -> bytes
    get_update(section_id, state_vector) -> bytes
        # Standard Yjs sync protocol helpers (step 1 & 2).

    persist(section_id) -> None
        # Encode full Y.YDoc state → save to yjs_state column.
        # Also export doc content as markdown → save to content column.
        # Called on a debounced schedule (e.g. every 5 s while dirty).

    cleanup_idle(max_age=timedelta(minutes=30)) -> None
        # Evict docs with no updates in 30 min to free memory.
        # Persist before eviction.
```

**Library**: [`yrs`](https://github.com/y-crdt/yrs) (Rust-based Yjs port with Python bindings via `pycrdt`). Fast, compatible with the JS Yjs wire protocol.

### 2. New file: `app/api/v1/routes/proposal_collab.py`

WebSocket endpoint following the Yjs sync protocol.

```
@router.websocket("/projects/{project_id}/proposal-sections/{section_id}/ws")
async def proposal_section_ws(
    websocket: WebSocket,
    project_id: UUID,
    section_id: UUID,
):
    # 1. Authenticate via ?token= query param (same as project_chat.py)
    # 2. Validate user has access to project
    # 3. Load or create Y.YDoc for this section
    # 4. Yjs sync protocol:
    #    a. Send SyncStep1 (server state vector) to client
    #    b. Receive SyncStep1 from client → reply with SyncStep2 (diff)
    #    c. Receive SyncStep2 from client → apply
    # 5. Enter message loop:
    #    - Receive binary Yjs updates → apply to doc → broadcast to other clients
    #    - Receive awareness updates → broadcast to other clients
    # 6. On disconnect: remove from room, broadcast presence change
```

**Connection registry** (similar to existing `RoomHub`):

```
class CollabRoom:
    section_id: UUID
    connections: dict[WebSocket, UserInfo]  # ws → {user_id, display_name, color}

    async broadcast(sender: WebSocket, data: bytes)
        # Send to all connections except sender

    async broadcast_all(data: bytes)
        # Send to all connections including sender
```

```
class CollabHub:
    _rooms: dict[UUID, CollabRoom]       # section_id → room

    get_or_create_room(section_id) -> CollabRoom
    remove_connection(section_id, ws) -> None
    active_users(section_id) -> list[UserInfo]
```

### 3. Modify: `app/api/router.py`

Register the new WebSocket router:

```python
from app.api.v1.routes.proposal_collab import router as proposal_collab_router
api_router.include_router(proposal_collab_router, tags=["proposal-collab"])
```

### 4. Modify: `app/services/proposal_service.py`

Update `update_project_section()` to also invalidate/reload the in-memory Yjs doc when content is changed via the REST API (e.g., AI-generated drafts). This prevents stale Yjs state.

### 5. Dependencies: `pyproject.toml`

```toml
"pycrdt>=0.12",
```

(`pycrdt` is the maintained Python binding for `yrs`, the Rust Yjs implementation.)

---

## Frontend Changes

### 1. New dependencies: `package.json`

```json
"yjs": "^13.6",
"y-prosemirror": "^1.3",
"y-protocols": "^1.0",
"lib0": "^0.2"
```

### 2. New file: `src/lib/collab.ts`

WebSocket provider that implements the Yjs sync + awareness protocol.

```typescript
export class ProposalCollabProvider {
  doc: Y.Doc
  awareness: awarenessProtocol.Awareness
  private ws: WebSocket | null = null
  private sectionId: string
  private projectId: string

  constructor(projectId: string, sectionId: string, user: { id, name, color })

  connect(): void
    // Open WebSocket to /projects/{projectId}/proposal-sections/{sectionId}/ws?token=...
    // On open: send Yjs SyncStep1
    // On message: handle SyncStep1, SyncStep2, Update, Awareness
    // On close: attempt reconnect with exponential backoff

  disconnect(): void

  destroy(): void
    // Disconnect + clean up Y.Doc and awareness
}
```

This is intentionally a custom provider (not `y-websocket`'s `WebsocketProvider`) because:
- We need to pass the JWT token for auth.
- We want control over reconnection and error handling.
- The sync protocol itself is simple (~80 lines with `y-protocols`).

### 3. Modify: `src/components/ProposalRichEditor.tsx`

Replace local Tiptap state with Yjs-backed state:

```typescript
// Current (non-collaborative):
const editor = useEditor({
  extensions: [StarterKit, Image, Table, ...],
  content: markdownToHtml(initialContent),
  onUpdate: ({ editor }) => onChange(editor.getMarkdown()),
})

// New (collaborative):
const editor = useEditor({
  extensions: [
    StarterKit.configure({ history: false }),    // disable built-in undo
    Image, Table, ...
    Collaboration.configure({ document: ydoc }),  // Yjs binding
    CollaborationCursor.configure({               // remote cursors
      provider: collabProvider,
      user: { name: currentUser.name, color: userColor },
    }),
  ],
})
```

Key changes:
- **Disable Tiptap's built-in `history`** (undo/redo) — Yjs provides its own `UndoManager` that understands remote vs. local changes.
- **Add `Collaboration` extension** — binds the Tiptap editor to a `Y.XmlFragment` inside the `Y.Doc`.
- **Add `CollaborationCursor` extension** — shows colored cursors + name labels for other users.
- **Remove `onUpdate` → onChange` pattern** — content flows through Yjs, not through React state.

### 4. Modify: `src/components/ProposalWorkspace.tsx`

Replace the debounced HTTP save with Yjs provider lifecycle:

```typescript
// Per active section, maintain a provider:
const providerRef = useRef<ProposalCollabProvider | null>(null)

useEffect(() => {
  if (!activeSection) return
  const provider = new ProposalCollabProvider(
    selectedProjectId,
    activeSection.id,
    { id: currentUser.id, name: currentUser.display_name, color: assignedColor }
  )
  provider.connect()
  providerRef.current = provider
  return () => { provider.destroy() }
}, [activeSection?.id])
```

- Remove the `autoSaveTimer`, `saveState`, `localContent` debounce logic.
- The save indicator changes from "Saving…" to "N users editing" presence display.
- Keep the REST PATCH endpoint for metadata updates (status, owner, due_date, notes) — only `content` goes through Yjs.

### 5. New component: `src/components/CollabPresenceBar.tsx`

Small bar above or beside the editor showing active collaborators:

```
┌──────────────────────────────────────────────────┐
│ 🟢 Luca (you)   🔵 Maria   🟠 Ahmed             │
└──────────────────────────────────────────────────┘
```

- Reads from `provider.awareness` state.
- Updates reactively via awareness change events.
- Shows colored dot + name for each connected user (colors match their cursor).

---

## Sync Protocol Detail

The Yjs WebSocket sync protocol is a simple binary message exchange. Each message is prefixed with a type byte:

| Byte | Name | Direction | Purpose |
|------|------|-----------|---------|
| 0 | SyncStep1 | both | Send local state vector; ask peer for missing updates |
| 1 | SyncStep2 | both | Reply with the diff the peer is missing |
| 2 | Update | both | Incremental update (real-time keystrokes) |
| 3 | Awareness | both | Cursor position, user info, selection |

**Initial handshake** (on connect):
1. Client sends `SyncStep1(clientStateVector)`.
2. Server replies with `SyncStep2(diff)` — updates the client is missing.
3. Server sends `SyncStep1(serverStateVector)`.
4. Client replies with `SyncStep2(diff)` — updates the server is missing.
5. Both are now in sync.

**Ongoing**:
- Every keystroke generates a small `Update` message (~50–200 bytes) broadcast to all peers.
- Cursor moves generate `Awareness` messages broadcast to all peers.

---

## Persistence Strategy

### When to persist
- **Debounced**: 5 seconds after the last update (avoids write amplification during active typing).
- **On last disconnect**: when the final user leaves a section's room, persist immediately.
- **Periodic checkpoint**: every 60 seconds while any connection is active (crash safety).

### What to persist
1. `yjs_state` — full encoded `Y.Doc` snapshot. Used to bootstrap new connections.
2. `content` — markdown export of the current Yjs document. Keeps the REST API, search, and PDF export working without changes.

### Conflict with REST API writes
When an AI draft or REST PATCH updates `content` while no one is connected:
- The in-memory Yjs doc doesn't exist, so no conflict.
- On next WebSocket connect, `load_or_create()` finds `yjs_state` is stale vs. `content`.
- If `yjs_state IS NULL` or we detect a REST write since last Yjs persist, re-seed the Yjs doc from the new markdown content.
- Track this with a `content_updated_at` timestamp compared against `yjs_persisted_at`.

---

## Undo/Redo

Yjs provides `Y.UndoManager` which:
- Only undoes **local** changes (won't undo what another user typed).
- Integrates with ProseMirror/Tiptap via `y-prosemirror`.
- Replaces Tiptap's built-in `history` extension (which must be disabled).

No additional work needed — `y-prosemirror` handles this automatically.

---

## Scaling Considerations

### Single-server (current deployment)
- In-memory `Y.Doc` per active section works perfectly.
- All WebSocket connections land on the same process, so broadcast is direct.
- Expected load: <10 concurrent editors per section — trivial.

### Multi-server (future)
If the backend scales to multiple processes/servers:
- Option A: **Sticky sessions** — route all WebSocket connections for a given section to the same server (simplest).
- Option B: **Redis pub/sub relay** — each server subscribes to a Redis channel per section and rebroadcasts updates to local connections.
- Option C: **Dedicated Yjs server** — run a standalone `y-websocket` Node.js server and let the Python backend handle REST only.

Recommendation: start with single-server. Add sticky sessions when scaling.

---

## Offline & Reconnection

Yjs handles offline gracefully by design:
- The client accumulates local updates in the `Y.Doc`.
- On reconnect, the sync protocol exchanges only the missing deltas.
- No data loss — CRDTs guarantee convergence regardless of message ordering.

The `ProposalCollabProvider` should implement:
- Exponential backoff reconnection (1s → 2s → 4s → … → 30s cap).
- Visual indicator: "Reconnecting…" banner when disconnected.
- Queue awareness updates during disconnection.

---

## Migration Path

### Phase 0 — Add Yjs column (Alembic migration)
- DONE: Add `yjs_state BYTEA` to `project_proposal_sections`. Nullable, no data migration.

### Phase 1 — Backend relay
- DONE: Implement `ProposalCollabService` and WebSocket endpoint.
- No frontend changes yet — the endpoint exists but isn't called.
- Write integration tests: connect two test WebSocket clients, verify updates sync.

### Phase 2 — Frontend Yjs integration
- DONE: Install `yjs`, `y-protocols`, `lib0`, and Tiptap collaboration extensions.
- DONE: Build `ProposalCollabProvider`.
- DONE: Modify `ProposalRichEditor` to use `Collaboration` + collaboration caret extensions.
- Modify `ProposalWorkspace` to manage provider lifecycle.
- Remove the debounced HTTP save for content.

### Phase 3 — Presence UI
- Build `CollabPresenceBar` component.
- Add "N editing" indicator on the section list sidebar.
- Assign deterministic user colors (hash of user ID).

### Phase 4 — Polish
- Reconnection UX (banner, auto-retry).
- Handle AI draft writes while users are connected (server pushes new Yjs update into the doc).
- Offline queue and sync.
- Edit session analytics table (optional).

---

## Files Summary

| Action | File | What |
|--------|------|------|
| DONE Create | `backend/alembic/versions/20260313_0042_proposal_collab_state.py` | Migration: add `yjs_state` column and edit session table |
| DONE Create | `backend/app/services/proposal_collab_service.py` | In-memory Yjs doc management + persistence |
| DONE Create | `backend/app/api/v1/routes/proposal_collab.py` | WebSocket endpoint + `CollabHub`/`CollabRoom` |
| DONE Modify | `backend/app/api/router.py` | Register new WS router |
| DONE Modify | `backend/app/models/proposal.py` | Add `yjs_state` column to model |
| DONE Modify | `backend/app/services/proposal_service.py` | Invalidate Yjs doc on external REST content update |
| DONE Modify | `backend/pyproject.toml` | Add `pycrdt` dependency |
| DONE Create | `frontend/src/lib/collab.ts` | Yjs WebSocket provider |
| Create | `frontend/src/components/CollabPresenceBar.tsx` | Active users indicator |
| DONE Modify | `frontend/src/components/ProposalRichEditor.tsx` | Yjs Collaboration + caret extensions |
| Modify | `frontend/src/components/ProposalWorkspace.tsx` | Provider lifecycle, remove debounced save |
| DONE Modify | `frontend/package.json` | Add collaboration dependencies |

---

## Risk & Mitigations

| Risk | Mitigation |
|------|-----------|
| Yjs doc grows unbounded over time | Periodic compaction: `Y.encodeStateAsUpdate(doc)` produces a compact snapshot. Run on persist. |
| Server crash loses in-memory state | Periodic persistence (60s checkpoint) + client re-sync on reconnect fills gaps automatically. |
| Markdown round-trip loses formatting | Yjs stores the ProseMirror document tree natively — markdown is only an export format. The Yjs binary state is the source of truth. |
| User on slow connection causes lag | Yjs updates are tiny (~100 bytes per keystroke). Awareness updates throttled to 500ms. |
| REST API draft overwrites collaborative edits | Detect active connections before applying REST write. If users are connected, inject the new content as a Yjs update instead. |
