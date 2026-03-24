# Containerized Deployment

This directory contains a full Docker Compose setup for:

- `postgres`
- `backend`
- `frontend`
- optional `ollama`

## Quick Start

```bash
cd deploy/docker
cp .env.example .env
docker compose up -d --build
```

Frontend will be available on:

- `http://localhost:${FRONTEND_PORT}`

By default:

- frontend: `http://localhost:8080`
- postgres: `localhost:5432`

## Notes

- The frontend is served by `nginx` and proxies `/api/` to the backend, so `VITE_API_BASE` is built as `/api/v1`
- The backend runs `alembic upgrade head` automatically on container start
- Persistent data is stored in named Docker volumes
- If you want Ollama in the stack, start the `ollama` profile:

```bash
docker compose --profile ollama up -d --build
```

- If you use `TEXT_INFERENCE_PROVIDER=codex`, the backend container still needs Codex runtime support if you want to use Codex inside the container. Otherwise keep text inference on Ollama for the containerized stack.

## Admin Bootstrap

Use the backend container to create or promote a platform admin.

Create a new super admin:

```bash
docker compose exec backend python scripts/user_admin.py create \
  --email admin@example.com \
  --password 'change-me-123' \
  --name 'Admin User'
```

Promote an existing user:

```bash
docker compose exec backend python scripts/user_admin.py promote \
  --email existing.user@example.com
```

Demote a user:

```bash
docker compose exec backend python scripts/user_admin.py demote \
  --email existing.user@example.com
```

Show script help:

```bash
docker compose exec backend python scripts/user_admin.py --help
```
