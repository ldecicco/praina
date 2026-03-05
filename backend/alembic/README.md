# Alembic

Initialize migrations in `backend/` with:

```bash
alembic init alembic
```

Then configure:
- `sqlalchemy.url` in `alembic.ini` (or via env var indirection)
- model metadata import from `app.db.base.Base`

Generate first migration:

```bash
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```
