# Project Tracker (AI-First MVP)

AI-first project tracking platform for research and innovation programs with:
- Core project entities: consortium, partners, teams, WPs, tasks, milestones, deliverables, reporting periods
- Project-grounded AI assistant with citations
- ChatOps workflows for safe data changes with explicit confirmation
- Full auditability for governance and reporting

## Architecture Direction
- Backend: Python (`FastAPI` + `SQLAlchemy` + `PostgreSQL` + `pgvector`)
- Agentic AI: `Agno`-based specialized agents
- Frontend: Tailwind CSS + shadcn/ui-ready structure
- LLM serving: Ollama

## Repository Structure
- `backend/`: Python API, data model, services, and Agno agent modules
- `docs/`: architecture decisions, entity model, and API contracts

## Installation
### Prerequisites
- Python `3.11+`
- Docker + Docker Compose
- `jq` (optional, for smoke-test convenience)

### 1. Start PostgreSQL (with pgvector)
```bash
cd backend
docker compose up -d
```

### 2. Create and activate Python virtual environment
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies
```bash
pip install --upgrade pip
pip install -e .
```

### 4. Configure environment
```bash
cp .env.example .env
```

`POSTGRES_PORT` in `.env` controls the exposed Docker Postgres port.
Backend DB connection is derived from `POSTGRES_*` variables (or `DATABASE_URL` if explicitly set).

### 5. Run database migrations
```bash
alembic upgrade head
```

### 6. Start backend API
```bash
uvicorn app.main:app --reload
```

API will be available at `http://127.0.0.1:8000`.

### 7. Test quickly (onboarding flow)
Create a project:
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/projects \
  -H "Content-Type: application/json" \
  -d '{
    "code": "HEU-ALPHA",
    "title": "Alpha Research Program",
    "description": "Initial integration test project."
  }'
```

Health check:
```bash
curl -s http://127.0.0.1:8000/api/v1/health
```

Full onboarding smoke test is documented in [docs/backend-smoke-test.md](/home/luca/dev/code/agentic-project-management/docs/backend-smoke-test.md).

## Next Step
Start from [backend/README.md](/home/luca/dev/code/agentic-project-management/backend/README.md) and [docs/backend-architecture.md](/home/luca/dev/code/agentic-project-management/docs/backend-architecture.md).

Frontend quality requirements are documented in [docs/frontend-quality-standard.md](/home/luca/dev/code/agentic-project-management/docs/frontend-quality-standard.md).
Full documentation index: [docs/README.md](/home/luca/dev/code/agentic-project-management/docs/README.md).
