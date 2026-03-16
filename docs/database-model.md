# Database Model (MVP)

## Core Entities
- `projects`
- `partner_organizations`
- `team_members`
- `work_packages`
- `tasks`
- `milestones`
- `deliverables`
- `project_documents`
- `document_chunks`
- `audit_events`

## Mandatory Responsibility Rule
For each `work_package`, `task`, `milestone`, and `deliverable`:
- `leader_organization_id` is required
- `responsible_person_id` is required
- `responsible_person_id` must be an active member of `leader_organization_id`
- collaborating partners are optional via relation tables

## Document Knowledge Base
- `project_documents` stores scoped document versions and metadata
  - `document_key` groups versions of the same logical document
  - `version` increments per `document_key`
  - scope can be `project`, `wp`, `task`, `deliverable`, `milestone`
  - optional link fields: `wp_id`, `task_id`, `deliverable_id`, `milestone_id`
  - `status`: `uploaded`, `indexed`, `failed`
- `document_chunks` stores chunk text and embeddings (`pgvector`)
- uploaded binaries are stored on disk (configured by `DOCUMENTS_STORAGE_PATH`) and referenced by `storage_uri`

## Governance and Audit
- `audit_events` is append-only
- records actor, event type, entity, reason, and before/after state payloads

## Notes
- IDs are UUIDs.
- Uniqueness is scoped by `project_id` + `code` for WPs/tasks/milestones/deliverables.
