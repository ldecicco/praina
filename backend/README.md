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
set -a && source .env && set +a
uvicorn app.main:app --host "$APP_HOST" --port "$APP_PORT" --reload
```

All ports are configured via `backend/.env` (`APP_PORT`, `POSTGRES_PORT`, `POSTGRES_INTERNAL_PORT`).
Set `CORS_ALLOWED_ORIGINS` in `backend/.env` to frontend origins.
`DOCUMENTS_STORAGE_PATH` configures where uploaded files are stored (default `storage/documents`).
Auth config:
- `JWT_SECRET_KEY`
- `JWT_ALGORITHM`
- `ACCESS_TOKEN_EXPIRE_MINUTES`
- `REFRESH_TOKEN_EXPIRE_DAYS`
Chat assistant model config:
- `OLLAMA_BASE_URL`
- `OLLAMA_MODEL`
- `ASSISTANT_TEMPERATURE`
- `ASSISTANT_HTTP_TIMEOUT_SECONDS`
- `ACTION_EXTRACTION_HTTP_TIMEOUT_SECONDS`

To enable LLM-backed chat, run Ollama locally and pull the configured model:
```bash
ollama serve
ollama pull qwen3.5:9b
```

The backend Python environment also needs the `ollama` client package (installed automatically by `pip install -e .`).
If your `.venv` was created before this dependency, run:
```bash
pip install ollama
```

Assistant mutation flow for project entities is propose-confirm-apply:
- Send command in chat (`add/update wp|task|deliverable|milestone ...`)
- Assistant returns `Proposal ID`
- Execute only with `confirm <proposal_id>` (or `cancel <proposal_id>`)

Project user chat (member-to-member) is available through:
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `POST /api/v1/auth/refresh`
- `GET /api/v1/auth/me`
- `GET /api/v1/projects/{project_id}/memberships`
- `POST /api/v1/projects/{project_id}/memberships`
- `GET /api/v1/projects/{project_id}/rooms`
- `POST /api/v1/projects/{project_id}/rooms`
- `POST /api/v1/projects/{project_id}/rooms/{room_id}/members`
- `DELETE /api/v1/projects/{project_id}/rooms/{room_id}/members/{user_id}`
- `GET /api/v1/projects/{project_id}/rooms/{room_id}/messages`
- `POST /api/v1/projects/{project_id}/rooms/{room_id}/messages`
- `WS /api/v1/projects/{project_id}/rooms/{room_id}/ws?token=<access_token>`

Room permissions are inherited from project roles only (no room admin role).

## Admin Bootstrap
Use the CLI to create or promote a platform admin:

```bash
cd backend
source .venv/bin/activate
python scripts/user_admin.py create --email admin@example.com --password 'change-me-123' --name 'Admin User'
python scripts/user_admin.py promote --email existing.user@example.com
python scripts/user_admin.py demote --email existing.user@example.com
```

## Database Migrations
```bash
cd backend
alembic upgrade head
```

Initial migration is available at:
- `alembic/versions/20260305_0001_initial_schema.py`

## Tests
```bash
cd backend
source .venv/bin/activate
pytest -q
```

## Initial Priorities
1. Implement onboarding endpoints and validation services.
2. Add Alembic migrations from current model definitions.
3. Implement document ingestion and retrieval indexing pipeline.
4. Implement ChatOps confirmation and audit logging flow.
