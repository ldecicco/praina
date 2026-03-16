# Frontend Component Contracts (MVP)

## 1) Onboarding Wizard
Core components:
- `ProjectBasicsForm`
- `PartnersTableEditor`
- `PartnerMembersEditor`
- `StructureBuilder`
- `WizardFooterActions`

State contract:
- `stepIndex: number`
- `draftProject: ProjectDraft`
- `validationErrors: Record<string, string[]>`
- `isSaving: boolean`

Interaction rules:
- Next step blocked on invalid required fields.
- Save draft allowed at every step.

## 2) Assignment Matrix
Core components:
- `AssignmentFilterBar`
- `AssignmentGrid`
- `AssignmentCellEditor`
- `ValidationPanel`

State contract:
- `filters: AssignmentFilters`
- `rows: AssignmentRow[]`
- `selectedRowIds: string[]`
- `pendingChanges: AssignmentChange[]`

Interaction rules:
- `responsible_person` dropdown filtered by selected `leader_organization`.
- Invalid rows highlighted and not submittable.

## 3) Document Library
Core components:
- `DocumentUploadDropzone`
- `DocumentScopeFilters`
- `DocumentTable`
- `DocumentMetadataDrawer`

State contract:
- `documents: DocumentRow[]`
- `activeDocumentId: string | null`
- `uploadQueue: UploadItem[]`
- `indexingStateByDocId: Record<string, IndexingState>`

Interaction rules:
- Upload requires scope before final submit.
- Version history accessible from row action.

## 4) Assistant Workspace
Core components:
- `ChatThread`
- `QuestionComposer`
- `CitationPanel`
- `ScopeSelector`

State contract:
- `messages: ChatMessage[]`
- `activeScope: AssistantScope`
- `isAnswerLoading: boolean`
- `selectedCitationId: string | null`

Interaction rules:
- Each assistant answer must render citations.
- Missing evidence shows explicit warning banner.

## 5) Audit Timeline
Core components:
- `AuditFilterBar`
- `AuditTimeline`
- `AuditEventDrawer`

State contract:
- `events: AuditEventRow[]`
- `filters: AuditFilters`
- `activeEventId: string | null`
- `isLoading: boolean`

Interaction rules:
- Event row opens structured before/after payload.
- Filter state is preserved in URL query params.
