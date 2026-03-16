SHELL := /bin/bash

.PHONY: backend-up backend-down backend-install backend-migrate backend-api backend-test frontend-install frontend-dev

backend-up:
	cd backend && docker compose up -d

backend-down:
	cd backend && docker compose down

backend-install:
	cd backend && python3 -m venv .venv && source .venv/bin/activate && pip install --upgrade pip && pip install -e .[dev]

backend-migrate:
	cd backend && source .venv/bin/activate && alembic upgrade head

backend-api:
	cd backend && source .venv/bin/activate && set -a && source .env && set +a && uvicorn app.main:app --host "$${APP_HOST}" --port "$${APP_PORT}" --reload

backend-test:
	cd backend && source .venv/bin/activate && pytest -q

frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev
