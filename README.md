# Project Tracker (AI-First MVP)

AI-first project tracking platform for research and innovation programs with:
- Core project entities: consortium, partners, WPs, tasks, milestones, deliverables, reporting periods
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
- `frontend/`: React + Vite MVP UI (Onboarding Wizard + Assignment Matrix)
- `docs/`: architecture decisions, entity model, and API contracts
- `api-collections/`: Postman and Bruno API collections

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
Set `CORS_ALLOWED_ORIGINS` to frontend origin(s), comma-separated.

### 5. Run database migrations
```bash
alembic upgrade head
```

### 6. Start backend API
```bash
set -a && source .env && set +a
uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT" --reload
```

API will be available at `http://$APP_HOST:$APP_PORT`.

### 7. Test quickly (onboarding flow)
Create a project:
```bash
curl -s -X POST "http://$APP_HOST:$APP_PORT/api/v1/projects" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "HEU-ALPHA",
    "title": "Alpha Research Program",
    "description": "Initial integration test project."
  }'
```

Health check:
```bash
curl -s "http://$APP_HOST:$APP_PORT/api/v1/health"
```

Full onboarding smoke test is documented in [docs/backend-smoke-test.md](/home/luca/dev/code/agentic-project-management/docs/backend-smoke-test.md).

### 8. Start frontend MVP
```bash
cd ../frontend
cp .env.example .env
npm install
npm run dev
```

Frontend uses `VITE_DEV_PORT` and `VITE_API_BASE` from `frontend/.env`.
On first access, use the built-in `Register` / `Login` screen.

### 9. Chat Assistant
Run latest migrations to enable chat tables:
```bash
cd ../backend
alembic upgrade head
```

Chat API endpoints:
- `GET /api/v1/projects/{project_id}/chat/conversations`
- `POST /api/v1/projects/{project_id}/chat/conversations`
- `GET /api/v1/projects/{project_id}/chat/conversations/{conversation_id}/messages`
- `POST /api/v1/projects/{project_id}/chat/conversations/{conversation_id}/messages`
- `POST /api/v1/projects/{project_id}/chat/conversations/{conversation_id}/messages/stream`

User-to-user project chat and auth endpoints:
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/projects/{project_id}/rooms`
- `POST /api/v1/projects/{project_id}/rooms`
- `GET /api/v1/projects/{project_id}/rooms/{room_id}/messages`
- `POST /api/v1/projects/{project_id}/rooms/{room_id}/messages`
- `WS /api/v1/projects/{project_id}/rooms/{room_id}/ws?token=<access_token>`

Chat runtime is configured in `backend/.env`:
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `ASSISTANT_TEMPERATURE`
- `ASSISTANT_HTTP_TIMEOUT_SECONDS`

Start Ollama and pull model:
```bash
ollama serve
ollama pull qwen3.5:9b
```

The frontend now includes an `Assistant` workspace in the left navigation.

Chat can create/update WPs, tasks, deliverables, and milestones through proposal-confirmation commands.
Each action is always staged first, then executed only after explicit confirmation:
- `confirm <proposal_id>`
- `cancel <proposal_id>`

## Developer Commands
Use the root [Makefile](/home/luca/dev/code/agentic-project-management/Makefile):
- `make backend-up`
- `make backend-install`
- `make backend-migrate`
- `make backend-api`
- `make backend-test`
- `make frontend-install`
- `make frontend-dev`

## API Collections
- Postman: [project-tracker-mvp.postman_collection.json](/home/luca/dev/code/agentic-project-management/api-collections/postman/project-tracker-mvp.postman_collection.json)
- Bruno: [api-collections/bruno/project-tracker-mvp](/home/luca/dev/code/agentic-project-management/api-collections/bruno/project-tracker-mvp)

Set `baseUrl` in collection environments using your `.env` values (`APP_HOST`, `APP_PORT`).

## Next Step
Start from [backend/README.md](/home/luca/dev/code/agentic-project-management/backend/README.md) and [docs/backend-architecture.md](/home/luca/dev/code/agentic-project-management/docs/backend-architecture.md).

Frontend quality requirements are documented in [docs/frontend-quality-standard.md](/home/luca/dev/code/agentic-project-management/docs/frontend-quality-standard.md).
Full documentation index: [docs/README.md](/home/luca/dev/code/agentic-project-management/docs/README.md).
