# Configuration

Every runtime setting is defined in `backend/app/core/config.py` as a Pydantic `Settings` model and
loaded from environment variables (locally via `backend/.env`). A starter template with safe
placeholders lives in [`backend/.env.example`](../backend/.env.example).

> **Loading order.** Settings are read from the process environment, then `backend/.env`. Empty
> values are ignored (`env_ignore_empty=True`) so a blank line never overrides a default, and unknown
> keys are ignored (`extra="ignore"`). The `env_file` path is relative, so the process must start from
> the repository root — or inside the container, where the working directory is `/app`.
>
> **Production.** Every secret is stored in AWS SSM Parameter Store (SecureString) and pulled at deploy
> time; nothing sensitive lives in source or git history. See [DEPLOYMENT.md](../DEPLOYMENT.md).

Legend: a ✅ in **Required** means the app will not boot without it. Everything else falls back to the
listed default.

## Database

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `POSTGRES_SERVER` | ✅ | — | Database host — `db` under Docker Compose, the RDS endpoint in production |
| `POSTGRES_USER` | ✅ | — | Database user |
| `POSTGRES_PASSWORD` | ✅ | — | Database password |
| `POSTGRES_DB` | ✅ | — | Database name |
| `POSTGRES_PORT` | — | `5432` | Database port |

Two SQLAlchemy URIs are derived from these values: a **sync** URI (`postgresql+psycopg://…`) used by
Alembic and synchronous background tasks, and an **async** URI (`postgresql+psycopg_async://…`) used by
request handlers. Both append `connect_timeout=10`.

## Redis

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `REDIS_HOST` | — | `redis` | Redis host |
| `REDIS_PORT` | — | `6379` | Redis port |
| `REDIS_PASSWORD` | — | `""` | Redis auth password (blank = no auth) |
| `REDIS_SSL` | — | `false` | `true` switches all Redis clients to `rediss://` (TLS-only providers like Upstash) |
| `REDIS_DB_TASKS` | — | `2` | Logical DB for the async task store — set `0` on single-database providers |
| `REDIS_DB_DENYLIST` | — | `1` | Logical DB for the JWT deny-list — set `0` on single-database providers |

Redis backs the slowapi rate limiter, the JWT revocation deny-list, and the async task store that drives
job-match and agent progress.

## Authentication & Security

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `SECRET_KEY` | ✅ | — | JWT signing key — **validated to be ≥ 32 characters** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | — | `60` | Access-token lifetime in minutes |
| `ADMIN_SECRET` | — | `""` | Shared secret for `/admin/*` — **if set, must be ≥ 32 characters**; blank disables those routes |
| `BASE_URL` | — | `http://localhost:8000` | Public API base URL, used when building n8n callback URLs |

> The password policy (minimum 12 characters) is enforced at the model level, not through an environment
> variable.

## LLM Backend

The app runs a **dual-path** LLM stack. When `GROQ_API_KEY` is set, the computed `USE_GROQ` flag is true
and production uses Groq through `instructor`; otherwise it falls back to Ollama for local development.

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `GROQ_API_KEY` | — | `""` | Groq API key — **takes priority over Ollama when set** (free key at console.groq.com) |
| `GROQ_LLM_MODEL` | — | `llama-3.1-8b-instant` | Groq model id |
| `OLLAMA_BASE_URL` | — | `http://ollama:11434` | Ollama endpoint (local dev) |
| `OLLAMA_LLM_MODEL` | — | `llama3.2:3b` | Ollama chat model |
| `OLLAMA_EMBED_MODEL` | — | `nomic-embed-text` | Ollama embedding model |

## RAG / Vector Store

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `CHROMA_PERSIST_DIR` | — | `/app/chroma_data` | On-disk path for the persistent ChromaDB collections, mounted as a named Docker volume |

## Workflow Orchestration (optional)

When both variables are set, the computed `N8N_ENABLED` flag is true and cover-letter generation is
dispatched to n8n Cloud; otherwise generation runs as a local `BackgroundTask`.

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `N8N_WEBHOOK_URL` | — | `""` | n8n Cloud trigger URL |
| `N8N_WEBHOOK_SECRET` | — | `""` | Shared secret used to authenticate the n8n callback |

## CORS

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `ALLOWED_ORIGINS` | — | `http://localhost:8501` | Comma-separated allow-list of browser origins, parsed into `CORS_ORIGINS` |

## Observability

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `SENTRY_DSN` | — | `""` | Sentry project DSN; blank disables error reporting. PII capture is off (`send_default_pii=False`) |

## Runtime Flags

| Variable | Required | Default | Description |
|---|:--:|---|---|
| `PRODUCTION` | — | `false` | `true` hides `/docs` and `/redoc` and enables HSTS |
| `TESTING` | — | `false` | `true` (CI/tests) disables rate limiting — never set in production |

## Computed settings

These are derived from the values above — you do not set them directly:

| Field | Derivation |
|---|---|
| `SQLALCHEMY_DATABASE_URI` | Sync Postgres URI from the `POSTGRES_*` values (Alembic, sync tasks) |
| `SQLALCHEMY_ASYNC_DATABASE_URI` | Async Postgres URI (request handlers) |
| `USE_GROQ` | `true` when `GROQ_API_KEY` is non-empty |
| `N8N_ENABLED` | `true` when both `N8N_WEBHOOK_URL` and `N8N_WEBHOOK_SECRET` are set |
| `CORS_ORIGINS` | `ALLOWED_ORIGINS` split on commas |
