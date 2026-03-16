# API Contracts (Initial Draft)

## Project Onboarding
- `POST /api/v1/projects`
- `GET /api/v1/projects`
- `GET /api/v1/projects/{id}`
- `POST /api/v1/projects/{id}/partners`
- `GET /api/v1/projects/{id}/partners`
- `POST /api/v1/projects/{id}/members`
- `GET /api/v1/projects/{id}/members`
- `POST /api/v1/projects/{id}/work-packages`
- `GET /api/v1/projects/{id}/work-packages`
- `POST /api/v1/projects/{id}/tasks`
- `GET /api/v1/projects/{id}/tasks`
- `POST /api/v1/projects/{id}/milestones`
- `GET /api/v1/projects/{id}/milestones`
- `POST /api/v1/projects/{id}/deliverables`
- `GET /api/v1/projects/{id}/deliverables`
- `GET /api/v1/projects/{id}/assignment-matrix`
- `PATCH /api/v1/projects/{id}/work-packages/{entity_id}/assignment`
- `PATCH /api/v1/projects/{id}/tasks/{entity_id}/assignment`
- `PATCH /api/v1/projects/{id}/milestones/{entity_id}/assignment`
- `PATCH /api/v1/projects/{id}/deliverables/{entity_id}/assignment`
- `POST /api/v1/projects/{id}/validate`
- `POST /api/v1/projects/{id}/activate`

## Documents and Knowledge Base
- `POST /api/v1/projects/{id}/documents/upload`
- `GET /api/v1/projects/{id}/documents`
- `GET /api/v1/projects/{id}/documents/{document_id}`
- `GET /api/v1/projects/{id}/documents/by-key/{document_key}/versions`
- `POST /api/v1/projects/{id}/documents/{document_key}/versions/upload`
- `POST /api/v1/projects/{id}/documents/{document_id}/reindex`
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

## Auth and Collaboration Chat
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/projects/{id}/memberships`
- `POST /api/v1/projects/{id}/memberships`
- `GET /api/v1/projects/{id}/rooms`
- `POST /api/v1/projects/{id}/rooms`
- `POST /api/v1/projects/{id}/rooms/{room_id}/members`
- `DELETE /api/v1/projects/{id}/rooms/{room_id}/members/{user_id}`
- `GET /api/v1/projects/{id}/rooms/{room_id}/messages`
- `POST /api/v1/projects/{id}/rooms/{room_id}/messages`
- `WS /api/v1/projects/{id}/rooms/{room_id}/ws?token=<access_token>`

## Contract Principles
- Validation errors must be explicit and field-level where possible.
- Mutating endpoints must return resulting entity version and audit event reference.
- Assistant endpoints must return citations with document and chunk pointers.

For concrete payloads, see [API JSON Examples](/home/luca/dev/code/agentic-project-management/docs/api-examples.md).
