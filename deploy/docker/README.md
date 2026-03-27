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

## Telegram Notifications

Optional environment variables:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_BOT_USERNAME`

If these are set, users can link Telegram from their profile and receive their own Praina notifications through the bot.

## Telegram User Setup

### Operator setup

1. Set these variables in `deploy/docker/.env`:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_BOT_USERNAME`
2. Restart the backend after updating the environment.
3. No webhook or polling worker is required for this setup.

### User setup

1. Open `Profile` in Praina.
2. Click `Generate Link`.
3. Click `Open Bot`.
4. Press `Start` in Telegram.
5. Return to Praina.
6. Click `Find Chat`.
7. Once linked, enable or disable Telegram notifications from the same profile section.

### Notes

- One Telegram chat can be linked to one Praina user.
- Link codes expire after 15 minutes.
- Telegram delivery only forwards notifications already addressed to that specific Praina user.
- This setup is outbound-only from Praina to Telegram and works for VPN/on-prem deployments.

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
