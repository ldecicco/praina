# API Contracts (Initial Draft)

## Project Onboarding
- `POST /api/v1/projects`
- `POST /api/v1/projects/{id}/partners`
- `POST /api/v1/projects/{id}/teams`
- `POST /api/v1/projects/{id}/members`
- `POST /api/v1/projects/{id}/work-packages`
- `POST /api/v1/projects/{id}/tasks`
- `POST /api/v1/projects/{id}/milestones`
- `POST /api/v1/projects/{id}/deliverables`
- `POST /api/v1/projects/{id}/validate`
- `POST /api/v1/projects/{id}/activate`

## Documents and Knowledge Base
- `POST /api/v1/projects/{id}/documents`
- `GET /api/v1/projects/{id}/documents`
- `POST /api/v1/documents/{id}/reindex`
- `POST /api/v1/assistant/query`

## Deliverable Governance
- `POST /api/v1/deliverables/{id}/submit-review`
- `POST /api/v1/deliverables/{id}/approve`
- `POST /api/v1/deliverables/{id}/baseline`
- `POST /api/v1/projects/{id}/coherence-check`

## ChatOps and Audit
- `POST /api/v1/chatops/command`
- `POST /api/v1/chatops/confirm`
- `GET /api/v1/audit/events`

## Contract Principles
- Validation errors must be explicit and field-level where possible.
- Mutating endpoints must return resulting entity version and audit event reference.
- Assistant endpoints must return citations with document and chunk pointers.

For concrete payloads, see [API JSON Examples](/home/luca/dev/code/agentic-project-management/docs/api-examples.md).
