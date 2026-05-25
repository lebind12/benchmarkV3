# Environment variables template

Copy the block below into a local `.env` (gitignored) and fill real values.
This file lives under `docs/` because dot-files starting with `.env` are
blocked by the agent sandbox; the canonical SSOT is right here.

```dotenv
# --- Database ---
# Supabase: settings -> Database -> Connection string -> URI (pooled, ?sslmode=require).
# SQLAlchemy + psycopg3 form:
#   postgresql+psycopg://USER:PASSWORD@HOST:PORT/DBNAME
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres
DB_POOL_SIZE=2
DB_MAX_OVERFLOW=0
DB_POOL_TIMEOUT=10
DB_POOL_RECYCLE=300

# --- Worker scheduler ---
# Local dev should normally keep this false so `uvicorn --reload` does not run
# production sync jobs against Supabase. Enable only on the single process that
# owns scheduled workers.
WORKER_SCHEDULER_ENABLED=false

# Optional: separate DB used by `pytest -m integration`. If unset, integration
# tests are skipped via conftest guard.
TEST_DATABASE_URL=

# --- API-Football (Ultra plan) ---
API_FOOTBALL_KEY=
API_FOOTBALL_HOST=v3.football.api-sports.io
API_FOOTBALL_CONCURRENCY=6
API_FOOTBALL_REQUESTS_PER_MINUTE=300

# --- Upstash Redis (refresh token rotation / blacklist) ---
UPSTASH_REDIS_REST_URL=
UPSTASH_REDIS_REST_TOKEN=

# --- OpenAI (translation-filler / news-translator) ---
OPENAI_API_KEY=

# --- Frontend local dev ---
# false/empty = call FastAPI through Vite proxy. true = use MSW mock handlers.
VITE_USE_MOCK=false
VITE_BACKEND_URL=http://127.0.0.1:8000
```

## Notes

- `DATABASE_URL` is read by `app/core/config.py` (pydantic-settings) and by
  alembic's `env.py` (with `SQLALCHEMY_DATABASE_URL` taking priority for
  per-run overrides — see integration test fixture).
- Supabase session pooler can expose a small session cap. Keep local/API worker
  SQLAlchemy pools conservative unless the Supabase pool size is increased.
- `pydantic-settings` lower-cases env keys; `DATABASE_URL` → `database_url`.
- For the integration test runner only, `TEST_DATABASE_URL` must point at a
  Postgres where it is safe to `CREATE SCHEMA test_*` and `DROP` them.
