# Backend Architecture

## Goal
Provide a reliable backend foundation for:
- Structured project onboarding and validation
- Document ingestion and project knowledge retrieval with citations
- Deliverable lifecycle and coherence checks
- ChatOps transactions with confirmation and full auditability

## Technology Choices
- Python 3.11+
- FastAPI for REST APIs
- SQLAlchemy 2.0 + Alembic for model and migration management
- PostgreSQL as system-of-record
- pgvector for semantic search embeddings
- S3-compatible object storage for document binaries
- Agno for multi-agent orchestration

## Layers
- `api`: HTTP routes, request parsing, response shaping
- `services`: use-case logic and transactional orchestration
- `models`: normalized relational entities
- `agents`: AI orchestration modules (validation, retrieval, coherence, governance)
- `db`: connection/session and migration integration

## Runtime Principles
- All mutations are transactional.
- High-impact writes require explicit confirmation.
- Every mutation emits an audit event with before/after payloads.
- Assistant answers must include citations or explicit "insufficient evidence."
