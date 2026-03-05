# Database Model (MVP)

## Core Entities
- `projects`
- `partner_organizations`
- `teams`
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
- collaborating teams are optional via relation tables

## Document Knowledge Base
- `project_documents` stores metadata and scope
- `document_chunks` stores chunk text and embeddings (`pgvector`)
- document binaries live in object storage and are referenced by `storage_uri`

## Governance and Audit
- `audit_events` is append-only
- records actor, event type, entity, reason, and before/after state payloads

## Notes
- IDs are UUIDs.
- Uniqueness is scoped by `project_id` + `code` for WPs/tasks/milestones/deliverables.
