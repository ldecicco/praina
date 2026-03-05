# Frontend IA (MVP - 5 Screens)

## 1) Project Onboarding Wizard
Purpose: Create project and consortium baseline with guided steps.

Sections:
- Project basics
- Partner organizations
- Teams and members
- Structure setup (WP/task/milestone/deliverable)
- Review and submit

Primary actions:
- Save draft
- Continue
- Submit for validation

Quality requirements:
- No hidden validation errors
- Progress state always visible
- Keyboard-friendly form navigation

## 2) Assignment Matrix
Purpose: Assign leader organization, responsible person, and collaborator teams.

Sections:
- Filter bar (entity type, WP, partner, status)
- Matrix table
- Inline assignment editor

Primary actions:
- Bulk assign
- Resolve invalid rows
- Revalidate project

Quality requirements:
- Invalid assignment combinations prevented before submit
- Responsible person list filtered by selected leader organization
- Fast table interactions at scale

## 3) Document Library
Purpose: Manage project-wide and scoped documents with strong traceability.

Sections:
- Upload panel
- Scope/tag filters
- Document list with version and status
- Metadata side panel

Primary actions:
- Upload
- Edit metadata
- Reindex
- Open version history

Quality requirements:
- Upload flow is frictionless
- Scope is explicit and searchable
- Version context is always visible

## 4) Assistant Workspace (Cited Q&A)
Purpose: Ask project questions and get grounded answers with evidence.

Sections:
- Chat thread
- Citation panel
- Scope selector (project, WP, task, deliverable)

Primary actions:
- Ask
- Open source reference
- Refine scope

Quality requirements:
- Citations are first-class in UI, not secondary
- Empty evidence states are explicit
- Responses are readable for PM workflows

## 5) Audit and Governance Timeline
Purpose: Inspect all project mutations and approvals.

Sections:
- Event timeline
- Filter/search controls
- Event detail drawer (before/after, actor, reason)

Primary actions:
- Filter by entity or actor
- Inspect event payload
- Export filtered timeline

Quality requirements:
- Timeline is scannable under high volume
- Critical changes are clearly highlighted
- Event details are structured, not raw blobs
