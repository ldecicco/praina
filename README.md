# Praina

Praina is an AI-first project supervision platform with three current product areas:

- `Research`: funded research projects, proposal work, delivery tracking, meetings, documents, and research collections
- `Teaching`: university student projects organized by course, with supervision workflows, progress reports, oral-exam support, course materials, and grading support
- `Resources`: shared lab equipment, bookings, downtime, labs, and lab closures across both research and teaching

## Current Product State

### Research
- project dashboard and planning timeline
- proposal and submission workspaces
- meetings, documents, todos, and project chat
- research workspace with collections, references, notes, and AI synthesis
- project assistant with grounded citations

### Teaching
- separate teaching section with `Courses` as the main entry point
- teacher / TA governance model
- teaching project dashboards
- progress reports, blockers, artifacts, assessment, and oral support
- course materials and teaching-specific assistant grounding

### Resources
- top-level resources section
- equipment inventory and project resource requirements
- equipment booking calendar
- labs and lab closures
- conflict detection, downtime, blocker-day tracking, and notification support

## Stack

- Backend: `FastAPI`, `SQLAlchemy`, `Alembic`, `PostgreSQL`
- Frontend: `React`, `TypeScript`, `Vite`
- Retrieval / embeddings: `pgvector` + Ollama embeddings
- Text inference: Ollama or Codex, selectable through backend `.env`

## Repository Layout

- `backend/`: API, models, services, agents, migrations
- `frontend/`: React application
- `docs/`: planning and architecture notes
- `api-collections/`: API collections

## Quick Start

### Prerequisites

- Python `3.11+`
- Node `18+`
- Docker + Docker Compose

### 1. Start PostgreSQL

```bash
cd backend
docker compose up -d
```

### 2. Create the backend virtual environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e .[dev]
```

### 3. Configure the backend

```bash
cp .env.example .env
```

Important backend settings:

- database: `POSTGRES_*` or `DATABASE_URL`
- CORS: `CORS_ALLOWED_ORIGINS`
- text inference: `TEXT_INFERENCE_PROVIDER=ollama|codex`
- embeddings: Ollama settings remain required

If you want to use Codex for text generation:

```env
TEXT_INFERENCE_PROVIDER=codex
CODEX_MODEL=gpt-5.4
CODEX_TIMEOUT_SECONDS=120
```

Embeddings still come from Ollama.

### 4. Run migrations

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

### 5. Start the backend

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 9999 --reload
```

### 6. Start the frontend

```bash
cd frontend
cp .env.example .env
npm install
npm run dev
```

## Containerized Deployment

A full Docker setup is available in [deploy/docker/README.md](/home/luca/dev/code/praina/deploy/docker/README.md).

Quick start:

```bash
cd deploy/docker
cp .env.example .env
docker compose up -d --build
```

## Authentication

The frontend includes built-in registration and login.

There are currently user-level section capabilities:

- `can_access_research`
- `can_access_teaching`

So a user may have access to:

- research only
- teaching only
- both

## AI Notes

Praina currently uses one assistant surface with domain-aware behavior:

- research assistant context for funded / proposal workflows
- teaching assistant context for supervision workflows
- resource context injected for equipment, bookings, downtime, and blockers

Text generation can run on either:

- Ollama
- Codex

Embeddings remain Ollama-backed.

## Developer Commands

Use the root [Makefile](/home/luca/dev/code/praina/Makefile):

- `make backend-up`
- `make backend-install`
- `make backend-migrate`
- `make backend-api`
- `make backend-test`
- `make frontend-install`
- `make frontend-dev`

## Documentation

Start from [docs/README.md](/home/luca/dev/code/praina/docs/README.md).

Useful current planning docs:

- [docs/teaching-projects-plan.md](/home/luca/dev/code/praina/docs/teaching-projects-plan.md)
- [docs/resources-equipment-plan.md](/home/luca/dev/code/praina/docs/resources-equipment-plan.md)
- [docs/codex-llm-provider-plan.md](/home/luca/dev/code/praina/docs/codex-llm-provider-plan.md)

