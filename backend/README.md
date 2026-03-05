# Backend

Python backend for the Project Tracker MVP.

## Stack
- FastAPI for HTTP APIs
- SQLAlchemy 2.0 for ORM models
- Alembic for schema migrations
- PostgreSQL + pgvector for relational data and semantic retrieval
- Pydantic for API contracts
- Agno for agent orchestration

## Directory Layout
- `app/main.py`: FastAPI app entrypoint
- `app/api/`: route registration and API modules
- `app/models/`: SQLAlchemy entities
- `app/schemas/`: Pydantic request/response models
- `app/services/`: domain and use-case services
- `app/agents/`: Agno agent modules
- `app/db/`: engine/session/base setup
- `app/core/`: settings and app-level helpers

## Local Setup
```bash
cd backend
cp .env.example .env
# Optional: change POSTGRES_PORT in .env before starting docker.
docker compose up -d
python -m venv .venv
source .venv/bin/activate
pip install -e .
alembic upgrade head
uvicorn app.main:app --reload
```

## Database Migrations
```bash
cd backend
alembic upgrade head
```

Initial migration is available at:
- `alembic/versions/20260305_0001_initial_schema.py`

## Initial Priorities
1. Implement onboarding endpoints and validation services.
2. Add Alembic migrations from current model definitions.
3. Implement document ingestion and retrieval indexing pipeline.
4. Implement ChatOps confirmation and audit logging flow.
