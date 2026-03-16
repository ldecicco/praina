# Execution Plan — Phase 3: Intelligent Agents, Notifications & Reporting

## Current State (post Phase 2)

The platform has: project onboarding + activation, document ingestion with chunked knowledge base, ChatOps propose-confirm-apply flow, project chat rooms, meeting management with LLM action extraction, calendar integration, deliverable review findings, risk register, and audit logging.

**What's missing:** The 4 core agents are stubs (retrieval, validation, coherence, governance). There is no notification system, no reporting/export, and the dashboard doesn't leverage agent intelligence. Tests cover onboarding, chat, and documents but not the newer modules.

---

## Execution Order

| Step | Feature | Estimated Files | Depends On | Status |
|------|---------|-----------------|------------|--------|
| 1 | Retrieval Agent | 3 modify | — | DONE |
| 2 | Validation Agent + Service | 3 create, 3 modify | — | DONE |
| 3 | Coherence Agent | 1 create, 3 modify | Step 2 | DONE |
| 4 | Governance Agent | 1 create, 3 modify | Step 2 | DONE |
| 5 | Notification System | 5 create, 4 modify | — | DONE |
| 6 | Reporting & Export | 3 create, 3 modify | Steps 1-4 | DONE |
| 7 | Dashboard Intelligence | 2 modify | Steps 1-4 | DONE |
| 8 | Test Coverage | 4 create | Steps 1-7 | |

---

## Step 1: Retrieval Agent

**Goal:** Replace the token-based TF ranking in `chat_service.py` with proper semantic retrieval, improving assistant answer quality.

### 1a. Implement RetrievalAgent

**Modify** `backend/app/agents/retrieval_agent.py`

Current state: 10-line stub with empty `answer()` method.

Implement:
- `retrieve(query: str, project_id: UUID, db: Session, top_k: int = 5) -> list[RetrievalResult]`
- `RetrievalResult` dataclass: `chunk_id, source_type, source_id, source_key, title, version, chunk_index, content, score`
- Strategy (two-tier, no external embedding service needed):
  1. **Token overlap scoring** (improved): TF-IDF-like weighting instead of raw token count. Weight title matches 2x, boost recent documents. This is an improvement over the current `_retrieve_citations()` in chat_service.
  2. **Future-ready embedding path**: If `DocumentChunk.embedding` is not null, compute cosine similarity. The embedding column exists in pgvector but is currently always null. This path activates when an embedding pipeline is added later.
- Query both `DocumentChunk` (via `ProjectDocument`) and `MeetingChunk` (via `MeetingRecord`)
- Return results sorted by score descending, deduplicated by source_id+chunk_index

### 1b. Wire into ChatService

**Modify** `backend/app/services/chat_service.py`

- Replace `_retrieve_citations()` body with call to `RetrievalAgent.retrieve()`
- Map `RetrievalResult` to the existing citation dict format `{document_id, document_key, title, version, chunk_index, snippet, source_type}`
- Keep the same top-3 limit for prompt context, but return top-5 as citations in the response
- No API or schema changes needed — the citation format stays the same

### 1c. Add scope filtering

**Modify** `backend/app/agents/retrieval_agent.py`

- Add optional `scope_filter: str | None` parameter (values: "documents", "meetings", None for both)
- Add optional `entity_id: UUID | None` for scoped queries (e.g., only chunks from a specific deliverable's documents)
- The assistant prompt already tells the LLM about document scopes; this makes retrieval scope-aware too

---

## Step 2: Validation Agent + Assignment Validation Service

**Goal:** Implement structural and assignment validation that runs on project activation and can be triggered on-demand. Goes beyond schema checks into semantic validation.

### 2a. Implement AssignmentValidationService

**Modify** `backend/app/services/assignment_validation_service.py`

Current state: 11-line stub.

Implement `validate(project_id: UUID, db: Session) -> list[ValidationIssue]`:

`ValidationIssue` dataclass: `entity_type, entity_id, code, field, message, severity (error|warning)`

Rules to check:
1. **Assignment completeness**: Every WP/Task/Milestone/Deliverable has leader_organization_id and responsible_person_id
2. **Assignment consistency**: responsible_person belongs to leader_organization (query TeamMember.organization_id)
3. **Timeline bounds**: Task start/end within parent WP start/end
4. **Deliverable WP link**: Every deliverable has at least one wp_id
5. **Milestone WP link**: Every milestone has at least one wp_id
6. **Duplicate codes**: No duplicate codes within entity type per project
7. **Empty project**: At least one WP exists
8. **Orphaned tasks**: No tasks referencing trashed WPs
9. **Duration overflow**: No work entity end_month > project.duration_months

### 2b. Implement ValidationAgent

**Modify** `backend/app/agents/validation_agent.py`

Current state: 10-line stub with empty `run()` method.

Implement `run(project_id: UUID, db: Session) -> ValidationReport`:

`ValidationReport`: `project_id, errors: list[ValidationIssue], warnings: list[ValidationIssue], is_valid: bool`

- Calls `AssignmentValidationService.validate()` for structural rules
- Calls LLM (Ollama, same pattern as ChatAssistantAgent) for semantic checks:
  - Prompt includes: project context (compact), list of structural issues found
  - LLM reviews for: naming inconsistencies, suspiciously short/long task windows, deliverables with no meaningful description, risks without mitigation plans
  - Output: additional warnings (never errors — LLM findings are advisory)
- Merge structural errors + LLM warnings into final report

### 2c. Wire into project validation endpoint

**Modify** `backend/app/api/v1/routes/projects.py`

- The `POST /{project_id}/validate` endpoint currently calls `OnboardingService.validate_project()`
- Add a call to `ValidationAgent.run()` alongside it
- Merge results: OnboardingService errors + ValidationAgent errors/warnings
- Return the combined `ProjectValidationResult` (schema already has `errors` and `warnings` lists)

### 2d. Validation schemas

**Create** `backend/app/schemas/validation.py`

- `ValidationIssue`: entity_type, entity_id, code, field, message, severity
- `ValidationReport`: project_id, errors, warnings, is_valid

---

## Step 3: Coherence Agent

**Goal:** Cross-entity consistency checking. Finds contradictions, gaps, and misalignments that pass structural validation but indicate real problems.

### 3a. Implement CoherenceAgent

**Modify** `backend/app/agents/coherence_agent.py`

Current state: 9-line stub with empty `check_project()` method.

Implement `check_project(project_id: UUID, db: Session) -> list[CoherenceIssue]`:

`CoherenceIssue` dataclass: `category, entity_ids: list[str], message, suggestion, severity (warning|info)`

Categories of checks:

**Rule-based checks (no LLM):**
1. **Timeline gaps**: WPs that don't cover the full project duration (M1 to duration_months) — warning if gap > 3 months
2. **Milestone clustering**: Multiple milestones in the same month — info
3. **Deliverable bunching**: More than 3 deliverables due in the same month — warning
4. **Unbalanced WPs**: A WP with 0 tasks while others have 5+ — warning
5. **Risk coverage**: Open risks with no linked WP/task (based on risk.code prefix matching WP/task codes) — warning
6. **Reporting alignment**: Deliverable due_months that don't align with reporting_dates — info

**LLM-based checks (optional, best-effort):**
7. **Description coherence**: Send project description + WP descriptions + deliverable descriptions to LLM, ask for contradictions or missing links
8. **Timeline narrative**: Given the ordered list of milestones and deliverables, does the progression make logical sense?

Prompt pattern: same as ChatAssistantAgent (`_generate_with_ollama_chat`), with JSON output schema.

### 3b. Coherence endpoint

**Create** `backend/app/api/v1/routes/coherence.py`

- `POST /{project_id}/coherence-check` → returns `CoherenceReport`
- `CoherenceReport`: project_id, issues: list[CoherenceIssue], checked_at: datetime

**Modify** `backend/app/api/router.py` — register coherence router

### 3c. Schema

**Modify** `backend/app/schemas/validation.py` (created in Step 2d)

- Add `CoherenceIssue` and `CoherenceReport` to the same file

### 3d. Frontend integration

**Modify** `frontend/src/lib/api.ts`

- `runCoherenceCheck(projectId)` → POST

**Modify** `frontend/src/types.ts`

- Add `CoherenceIssue` and `CoherenceReport` types

---

## Step 4: Governance Agent

**Goal:** Policy enforcement layer that evaluates high-impact actions before they execute. Integrates into the ChatOps confirm flow.

### 4a. Implement GovernanceAgent

**Modify** `backend/app/agents/governance_agent.py`

Current state: 9-line stub with empty `evaluate_action()` method.

Implement `evaluate_action(action: dict, project_context: dict, db: Session) -> GovernanceDecision`:

`GovernanceDecision`: `allowed: bool, requires_approval: bool, reason: str, policy_refs: list[str]`

Policy rules (hard-coded, no LLM needed for v1):

1. **Activation guard**: Project activation requires: >= 1 WP, >= 1 partner, >= 1 member, 0 validation errors
2. **Scope change guard**: Changing `duration_months` or `start_date` on an active project requires explicit reason
3. **Bulk delete guard**: Trashing a WP with > 3 tasks requires confirmation
4. **Assignment change guard**: Changing leader_organization on an active WP requires reason
5. **Deliverable workflow guard**: Can only transition: draft→in_review→changes_requested/approved→submitted (no skipping)

Future LLM extension point: evaluate free-text "reason" field for sufficiency.

### 4b. Wire into ChatOps confirm flow

**Modify** `backend/app/services/chat_service.py`

- In `_confirm_proposal()`, before calling `_execute_payload()`:
  - Call `GovernanceAgent.evaluate_action(proposal.payload_json, project_context)`
  - If `not allowed`: return error message with `reason`
  - If `requires_approval`: store proposal status as `needs_approval`, return message asking for admin/PM confirmation
  - If `allowed`: proceed as before

### 4c. Governance schema

**Modify** `backend/app/schemas/validation.py`

- Add `GovernanceDecision`: allowed, requires_approval, reason, policy_refs

---

## Step 5: Notification System

**Goal:** In-app notifications + optional email digest. Makes collaboration features sticky by alerting users about events that need their attention.

### 5a. Notification model

**Create** `backend/app/models/notification.py`

- Enum: `NotificationChannel(in_app, email, both)`
- Enum: `NotificationStatus(unread, read, dismissed)`
- `Notification` class:
  - `user_id` (FK to user_accounts)
  - `project_id` (FK to projects, nullable)
  - `channel` (Enum NotificationChannel)
  - `status` (Enum NotificationStatus, default unread)
  - `title` (String 255)
  - `body` (Text)
  - `link_type` (String 64, nullable — e.g., "meeting", "action_item", "deliverable", "risk")
  - `link_id` (UUID, nullable — entity ID to link to)
  - `created_at`, `updated_at`

**Create** `backend/alembic/versions/20260310_0021_notifications.py`

**Modify** `backend/app/models/__init__.py` — register Notification + enums

### 5b. Notification service

**Create** `backend/app/services/notification_service.py`

- `NotificationService(db)`:
  - `notify(user_id, project_id, title, body, link_type?, link_id?, channel?)` — create notification
  - `notify_project_members(project_id, title, body, link_type?, link_id?, exclude_user_id?)` — notify all members of a project
  - `list_notifications(user_id, project_id?, unread_only?, page, page_size)` — paginated list
  - `mark_read(user_id, notification_id)` — mark single as read
  - `mark_all_read(user_id, project_id?)` — bulk mark read
  - `unread_count(user_id, project_id?)` — for badge

### 5c. Notification triggers

**Modify** `backend/app/services/action_item_service.py`

- After `promote_to_task()`: notify assignee "Action item promoted to task {code}"
- After `bulk_create()` with source=assistant: notify meeting creator "AI extracted {n} action items from {meeting.title}"

**Modify** `backend/app/services/meeting_service.py`

- After `create_meeting()`: notify project members "{member} added meeting: {title}"

**Modify** `backend/app/services/chat_service.py`

- After proposal confirmed: notify proposal creator "Your action was applied: {summary}"

### 5d. Notification endpoints

**Create** `backend/app/api/v1/routes/notifications.py`

- `GET /notifications` — list (paginated, optional project_id filter, optional unread_only)
- `GET /notifications/unread-count` — returns `{count: int}`
- `POST /notifications/{id}/read` — mark as read
- `POST /notifications/read-all` — mark all as read (optional project_id)

**Modify** `backend/app/api/router.py` — register notifications router

### 5e. Notification schemas

**Create** `backend/app/schemas/notification.py`

- `NotificationRead`: id, user_id, project_id, title, body, link_type, link_id, status, created_at
- `NotificationListRead(PaginatedResponse)`: items list
- `UnreadCountRead`: count

### 5f. Frontend notification UI

**Modify** `frontend/src/types.ts` — add `Notification` type

**Modify** `frontend/src/lib/api.ts` — add notification API methods

**Modify** `frontend/src/App.tsx`:
- Add notification bell icon in top bar next to user badge
- Poll `unread-count` every 30 seconds (or on tab focus)
- Dropdown panel showing recent notifications
- Click notification → navigate to relevant view (meeting, deliverable, etc.)

---

## Step 6: Reporting & Export

**Goal:** Generate downloadable project reports. This is what stakeholders consume outside the platform.

### 6a. Report generation service

**Create** `backend/app/services/report_service.py`

- `ReportService(db)`:
  - `generate_status_report(project_id) -> str` — returns Markdown
    - Project header: code, title, status, current month, duration
    - WP summary table: code, title, status, progress (tasks done/total)
    - Deliverable status: code, title, workflow_status, due month
    - Open risks: code, title, probability, impact, status
    - Recent meetings: last 5, with summaries (if available)
    - Pending action items: grouped by meeting
    - Timeline health: output from CoherenceAgent (if available)
  - `generate_meeting_report(project_id, meeting_id) -> str` — returns Markdown
    - Meeting header: title, date, participants
    - Summary (if available)
    - Action items checklist with status
    - Content excerpt (first 2000 chars)
  - `export_audit_log(project_id, event_type?, start_date?, end_date?) -> list[dict]` — returns rows for CSV

### 6b. Report endpoints

**Create** `backend/app/api/v1/routes/reports.py`

- `GET /{project_id}/reports/status` → returns Markdown (Content-Type: text/markdown) or JSON with `{markdown: str}`
- `GET /{project_id}/reports/meeting/{meeting_id}` → returns Markdown
- `GET /{project_id}/reports/audit-log` → returns CSV (Content-Type: text/csv) with optional query params: event_type, start_date, end_date

**Modify** `backend/app/api/router.py` — register reports router

### 6c. Frontend download UI

**Modify** `frontend/src/components/ProjectDashboard.tsx`

- Add "Export Status Report" button in summary bar → fetches markdown, triggers download as `.md` file
- Add "Export Audit Log" button in activity section → fetches CSV, triggers download

**Modify** `frontend/src/components/MeetingsHub.tsx`

- Add "Export Report" button per meeting → fetches meeting markdown report, triggers download

**Modify** `frontend/src/lib/api.ts`

- `getStatusReport(projectId)` → GET (returns text)
- `getMeetingReport(projectId, meetingId)` → GET (returns text)
- `getAuditLogCsv(projectId, params?)` → GET (returns blob)

---

## Step 7: Dashboard Intelligence

**Goal:** Make the ProjectDashboard the convergence point for all agent insights.

### 7a. Dashboard health endpoint

**Create** `backend/app/api/v1/routes/dashboard.py`

- `GET /{project_id}/dashboard/health` → aggregated health check:
  - Runs `ValidationAgent.run()` (cached for 5 min)
  - Runs `CoherenceAgent.check_project()` (cached for 5 min)
  - Returns: `{validation: ValidationReport, coherence: CoherenceReport, action_items_pending: int, risks_open: int, overdue_deliverables: int}`

**Modify** `backend/app/api/router.py` — register dashboard router

### 7b. Frontend dashboard enhancements

**Modify** `frontend/src/components/ProjectDashboard.tsx`

Add new sections:

1. **Health Score widget**: Visual indicator (green/yellow/red) based on validation errors + coherence warnings count
2. **Coherence issues panel**: List of CoherenceIssues with category icons, collapsible
3. **Action items burndown**: Count of pending vs done action items across all meetings (small bar chart or simple numbers)
4. **"Run Health Check" button**: Triggers the dashboard health endpoint, refreshes all panels
5. **Risk heatmap**: 2x2 grid (probability x impact) with risk counts per cell — data already exists in `project_risks`

### 7c. Frontend types & API

**Modify** `frontend/src/types.ts` — add `DashboardHealth` type

**Modify** `frontend/src/lib/api.ts` — add `getDashboardHealth(projectId)` method

---

## Step 8: Test Coverage

**Goal:** Cover the new modules with integration tests following existing patterns.

### 8a. Agent tests

**Create** `backend/tests/test_retrieval_agent.py`

- Test token scoring with known documents
- Test scope filtering (documents only, meetings only)
- Test empty project returns empty results
- Test deduplication

### 8b. Validation & coherence tests

**Create** `backend/tests/test_validation_api.py`

- Test assignment completeness check catches missing responsible_person
- Test assignment consistency catches cross-org assignment
- Test timeline bounds catches task outside WP window
- Test valid project passes all checks
- Test coherence detects timeline gaps
- Test coherence detects deliverable bunching

### 8c. Action item tests

**Create** `backend/tests/test_action_items_api.py`

- Test CRUD: create, list, update status
- Test promote to task: creates task with correct WP, code, assignment
- Test bulk create with assistant source replaces old assistant items
- Test extract endpoint (mock LLM response)

### 8d. Notification tests

**Create** `backend/tests/test_notifications_api.py`

- Test create notification and list
- Test mark read / mark all read
- Test unread count
- Test project-scoped filtering

---

## File Summary

### Create (16 files)
| File | Step |
|------|------|
| `backend/app/schemas/validation.py` | 2 |
| `backend/app/api/v1/routes/coherence.py` | 3 |
| `backend/app/models/notification.py` | 5 |
| `backend/alembic/versions/20260310_0021_notifications.py` | 5 |
| `backend/app/schemas/notification.py` | 5 |
| `backend/app/services/notification_service.py` | 5 |
| `backend/app/api/v1/routes/notifications.py` | 5 |
| `backend/app/services/report_service.py` | 6 |
| `backend/app/api/v1/routes/reports.py` | 6 |
| `backend/app/api/v1/routes/dashboard.py` | 7 |
| `backend/tests/test_retrieval_agent.py` | 8 |
| `backend/tests/test_validation_api.py` | 8 |
| `backend/tests/test_action_items_api.py` | 8 |
| `backend/tests/test_notifications_api.py` | 8 |

### Modify (18 files)
| File | Steps |
|------|-------|
| `backend/app/agents/retrieval_agent.py` | 1 |
| `backend/app/agents/validation_agent.py` | 2 |
| `backend/app/agents/coherence_agent.py` | 3 |
| `backend/app/agents/governance_agent.py` | 4 |
| `backend/app/services/assignment_validation_service.py` | 2 |
| `backend/app/services/chat_service.py` | 1, 4 |
| `backend/app/services/action_item_service.py` | 5 |
| `backend/app/services/meeting_service.py` | 5 |
| `backend/app/api/v1/routes/projects.py` | 2 |
| `backend/app/api/router.py` | 3, 5, 6, 7 |
| `backend/app/models/__init__.py` | 5 |
| `frontend/src/types.ts` | 3, 5, 7 |
| `frontend/src/lib/api.ts` | 3, 5, 6, 7 |
| `frontend/src/App.tsx` | 5 |
| `frontend/src/components/ProjectDashboard.tsx` | 6, 7 |
| `frontend/src/components/MeetingsHub.tsx` | 6 |

---

## Verification Checklist

After each step:

1. **Step 1**: Chat assistant answers should include better-ranked citations. Test: ask about a specific deliverable, verify citations come from relevant documents.
2. **Step 2**: `POST /{project_id}/validate` returns structural errors + LLM warnings. Test: create a task with end_month > WP end_month, verify error appears.
3. **Step 3**: `POST /{project_id}/coherence-check` returns timeline gaps, deliverable bunching, etc. Test: create 4 deliverables all due in M6, verify warning.
4. **Step 4**: ChatOps `confirm` on a scope change without reason gets blocked. Test: propose duration_months change on active project, confirm, verify governance rejection.
5. **Step 5**: Creating a meeting triggers notifications for project members. Promoting an action item notifies the assignee. Unread count endpoint works.
6. **Step 6**: Download status report as markdown. Download audit log as CSV. Download meeting report with action items.
7. **Step 7**: Dashboard shows health score, coherence issues, action items burndown. "Run Health Check" button refreshes data.
8. **Step 8**: All new tests pass. `pytest backend/tests/` green.

---

## Recommended Execution Sequence

Steps 1 and 2 can be parallelized (no dependencies).
Steps 3 and 4 depend on Step 2 (validation schemas).
Step 5 is independent and can be parallelized with Steps 1-4.
Steps 6 and 7 depend on Steps 1-4 (they consume agent outputs).
Step 8 should be done incrementally after each step, but a final pass at the end.

```
            ┌─── Step 1 (Retrieval) ──────────────────────────────┐
            │                                                      │
Start ──────┤                                                      ├─── Step 6 (Reports) ─── Step 7 (Dashboard) ─── Step 8 (Tests)
            │                                                      │
            ├─── Step 2 (Validation) ─── Step 3 (Coherence) ──────┤
            │                         └── Step 4 (Governance) ─────┤
            │                                                      │
            └─── Step 5 (Notifications) ──────────────────────────┘
```
