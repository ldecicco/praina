#!/bin/bash

source .venv/bin/activate
alembic upgrade head
uvicorn app.main:app --host "127.0.0.1" --port "9999" --reload --log-level info