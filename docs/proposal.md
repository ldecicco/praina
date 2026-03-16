Project Mode: Proposal vs Execution                                                                                                          │
│                                                                                                                                              │
│ Context                                                                                                                                      │
│                                                                                                                                              │
│ The app currently treats all projects as execution-mode (funded projects being managed). The user wants two distinct creation paths:         │
│                                                                                                                                              │
│ 1. Proposal mode — writing a funding proposal from scratch. No execution views needed. Minimal creation (code + title). Navigation limited   │
│ to: Dashboard, Proposal, Chat, Assistant, Documents, Setup.                                                                                  │
│ 2. Execution mode — current behavior. Full onboarding wizard, all views available.                                                           │
│                                                                                                                                              │
│ A project in proposal mode transitions to execution via an explicit "Mark as Funded" action that collects the real timeline data. Status     │
│ stays draft after transition so the user can complete Setup wizard before activation.                                                        │
│                                                                                                                                              │
│ Key DB design choice: start_date and duration_months remain NOT NULL in the DB (they have server defaults). For proposal mode, the service   │
│ fills in placeholder defaults (today(), 36). This avoids cascading nullable changes throughout the codebase.                                 │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 1. Database Migration                                                                                                                        │
│                                                                                                                                              │
│ Create: backend/alembic/versions/20260310_0033_project_mode.py                                                                               │
│ - Chain from 20260310_0032                                                                                                                   │
│ - Add project_mode column (String(16), NOT NULL, server_default="execution")                                                                 │
│ - Existing projects automatically get "execution"                                                                                            │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 2. Backend Model                                                                                                                             │
│                                                                                                                                              │
│ Modify: backend/app/models/project.py                                                                                                        │
│                                                                                                                                              │
│ - Add ProjectMode enum (proposal, execution) after ProjectStatus                                                                             │
│ - Add column: project_mode: Mapped[str] = mapped_column(String(16), default="execution")                                                     │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 3. Backend Schemas                                                   
Modify: backend/app/schemas/project.py                                                                                                       │
│                                                                                                                                              │
│ - ProjectCreate: add project_mode: str = "execution", change start_date: date | None = None, duration_months: int | None =                   │
│ Field(default=None, ge=1, le=120). Add @model_validator: execution mode requires both, proposal mode doesn't.                                │
│ - ProjectRead: add project_mode: str = "execution"                                                                                           │
│ - ProjectUpdate: add project_mode: str | None = None                                                                                         │
│ - New MarkAsFundedPayload: start_date: date, duration_months: int = Field(ge=1, le=120), reporting_dates: list[date] = []                    │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 4. Backend Services                                                                                                                          │
│                                                                                                                                              │
│ Modify: backend/app/services/onboarding_service.py                                                                                           │
│                                                                                                                                              │
│ 4a. create_project                                                                                                                           │
│                                                                                                                                              │
│ - Use payload.start_date or date.today() and payload.duration_months or 36 as defaults                                                       │
│ - Pass project_mode to Project constructor                                                                                                   │
│                                                                                                                                              │
│ 4b. New: mark_as_funded(project_id, start_date, duration_months, reporting_dates)                                                            │
│                                                                                                                                              │
│ - Validate: must be proposal mode, not archived                                                                                              │
│ - Set project_mode = "execution", update timeline fields                                                                                     │
│ - Log audit event project.marked_as_funded                                                                                                   │
│ - Status stays draft                                                                                                                         │
│                                                                                                                                              │
│ 4c. validate_project                                                                                                                         │
│                                                                                                                                              │
│ - If project_mode == "proposal": only validate proposal sections (if template assigned). Skip WP/task/milestone/deliverable/coordinator/PI   │
│ checks.                                                                                                                                      │
│                                                                                                                                              │
│ 4d. _project_json                                                                                                                            │
│                                                                                                                                              │
│ - Add project_mode to dict                                                                                                                   │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 5. Backend Routes                                                                             
Modify: backend/app/api/v1/routes/projects.py                                                                                                │
│                                                                                                                                              │
│ - New: POST /{project_id}/mark-as-funded → accepts MarkAsFundedPayload, returns ActivationResultRead                                         │
│ - _project_read: add project_mode                                                                                                            │
│ - Import MarkAsFundedPayload from schemas                                                                                                    │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 6. Frontend Types + API                                                                                                                      │
│                                                                                                                                              │
│ Modify: frontend/src/types.ts                                                                                                                │
│ - Add project_mode: "proposal" | "execution" to Project                                                                                      │
│                                                                                                                                              │
│ Modify: frontend/src/lib/api.ts                                                                                                              │
│ - createProject: make start_date and duration_months optional, add project_mode?                                                             │
│ - New: markAsFunded(projectId, payload) → POST                                                                                               │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 7. NewProjectModal                                                                                                                           │
│                                                                                                                                              │
│ Modify: frontend/src/components/NewProjectModal.tsx                                                                                          │
│                                                                                                                                              │
│ - Add mode state (default "proposal")                                                                                                        │
│ - Two card-style toggle buttons at top: "Write a Proposal" / "Manage Execution"                                                              │
│ - Proposal mode: show only Code + Title + Description. Button: "Create Proposal"                                                             │
│ - Execution mode: show all current fields. Button: "Create Project"                                                                          │
│ - Send project_mode in payload; omit timeline fields for proposal mode                                                                       │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 8. App.tsx Nav Filtering                                                                                                                     │
│                                                                                                                                              │
│ Modify: frontend/src/App.tsx                                                                                                                 │
│                                                                                                                                              │
│ - PROPOSAL_MODE_VIEWS = new Set(["dashboard", "proposal", "project-chat", "assistant", "documents", "wizard"])                               │
│ - Filter navItems by project mode                                                                                                            │
│ - useEffect guard: redirect to dashboard if switching to proposal project while on execution-only view                                       │
│ - Topbar badge: show "Proposal" instead of status for proposal-mode projects                                                                 │
│                                                                                                                                              │
│ ---                                                                                                                                          │
│ 9. MarkAsFundedModal                                                                                                                         │
│                                                                                                                                              │
│ Create: frontend/src/components/MarkAsFundedModal.tsx                                                                                        │
│                                                                                                                                              │
│ - Fields: start_date (required), duration_months (required, default 36), reporting_dates (optional CSV)                                      │
│ - Calls api.markAsFunded(), then onProjectUpdated()                                                                                          │
│                                                                                                             