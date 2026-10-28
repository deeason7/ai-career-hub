# Configuration

[Documentation](README.md) · [Local setup](../CONTRIBUTING.md#running-locally) · [Deployment](../DEPLOYMENT.md)

Use [`backend/.env.example`](../backend/.env.example) as the local template. Never commit a populated environment file or `.streamlit/secrets.toml`. Active deployment settings live in Hugging Face Spaces, Streamlit Community Cloud and GitHub Environments; the retained AWS target uses SSM Parameter Store. See [Deployment](../DEPLOYMENT.md).

## Loading settings correctly

Most backend settings come from [`Settings`](../backend/app/core/config.py). Process environment values take precedence over its relative `backend/.env` file. Empty values are ignored by this Pydantic loader, and unknown keys are ignored. Start a direct local backend process from the repository root if relying on that file. In containers, Compose `env_file` or the host injects the process environment; `/app/backend/.env` is not a required image file.

Redis clients, rate limiting, `TESTING` and `ATS_MODEL_PATH` also read `os.environ` directly. The Pydantic file loader does **not** export those values into the process environment. For direct host execution, export the relevant variables; using Compose's `env_file` performs that injection. Do not assume a setting works merely because it appears in the `Settings` model.

For local Compose startup, use `docker compose --env-file backend/.env up --build -d`.
The CLI flag supplies Compose's `${POSTGRES_*}` interpolation, while the API's
service-level `env_file` supplies its process environment. Using the same file keeps
both services aligned. Existing volumes retain their original database credentials.
The test service deliberately retains separate defaults; follow the
[test-login override](../CONTRIBUTING.md#run-tests) when using a custom local database
login, and keep `careerhub_test` separate from application data.

In the tables, **required** means the settings model rejects a missing value. Conditional service credentials are needed when that service is selected, even where startup does not validate them. An empty string is shown as `""`.

## Database

| Variable | Default | Purpose |
|---|---|---|
| `POSTGRES_SERVER` | Required | `db` in Compose; provider hostname on a hosted deployment |
| `POSTGRES_USER` | Required | Database user |
| `POSTGRES_PASSWORD` | Required | Database password; never reuse the published local development default |
| `POSTGRES_DB` | Required | Database name; tests must use a separate disposable database |
| `POSTGRES_PORT` | `5432` | Database port |
| `DB_SSLMODE` | `""` | PostgreSQL TLS mode, appended when set; use the mode required by your provider |

Sync (`postgresql+psycopg`) and async (`postgresql+psycopg_async`) SQLAlchemy URIs are derived from these settings, with `connect_timeout=10`. They serve migrations/background work and request handlers respectively. The current URI construction interpolates credentials directly; URL-reserved characters require care and should be covered when revising connection handling.

## Redis and rate limiting

| Variable | Runtime default | Purpose |
|---|---|---|
| `REDIS_HOST` | Unset for direct readers | When absent, token revocation/task clients are disabled and the limiter uses memory. The Settings model separately defaults to `redis`; Compose explicitly injects `redis`. |
| `REDIS_PORT` | `6379` | Redis port |
| `REDIS_PASSWORD` | `""` | Authentication password; production Compose requires a nonempty value |
| `REDIS_SSL` | `false` | `true`, `1` or `yes` enables `rediss://` for the direct Redis clients |
| `REDIS_DB_TASKS` | `2` | Task-state logical database; use `0` for a single-database provider |
| `REDIS_DB_DENYLIST` | `1` | JWT revocation logical database; use `0` for a single-database provider |

The limiter uses Redis database `0`. Configure all Redis variables in the **process environment**. During an outage, rate limiting falls back to per-process memory and revocation fails open; see [Security](../SECURITY.md). A healthy API process does not prove these services are available.

## Authentication and runtime

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | Required | JWT signing key, validated to at least 32 characters; generate a unique random deployment value |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Access-token lifetime; refresh lifetime is seven days in code |
| `ADMIN_SECRET` | `""` | Admin endpoint secret; at least 32 characters if set, otherwise routes reject access |
| `PRODUCTION` | `false` | Hides Swagger/ReDoc, enables API HSTS and sets Secure on backend refresh cookies |
| `TESTING` | `false` | Direct environment flag: literal `true` disables route rate limits; use only for tests |
| `BASE_URL` | `http://localhost:8000` | Public API base for workflow callbacks; do not append `/api/v1` |
| `ALLOWED_ORIGINS` | `http://localhost:8501` | Comma-separated browser-origin allow-list, including scheme and port where applicable |
| `SENTRY_DSN` | `""` | Enables backend error reporting; default PII capture is disabled |

Keep `TESTING` unset/false in production. The password policy is implemented in request models, not configured through environment variables. `PROJECT_NAME`, `VERSION` and `API_V1_STR` are code defaults for application identity and routing; retain the release version and `/api/v1` prefix unless coordinating all clients and deployment checks.

## Language models

A nonempty `GROQ_API_KEY` selects Groq through `instructor`; otherwise the LLM client uses Ollama. Required models and provider access must be provisioned separately.

| Variable | Default | Purpose |
|---|---|---|
| `GROQ_API_KEY` | `""` | Groq credential; selects the hosted LLM path when present |
| `GROQ_LLM_MODEL` | `openai/gpt-oss-20b` | Groq model identifier |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Local Ollama endpoint |
| `OLLAMA_LLM_MODEL` | `llama3.2:3b` | Ollama chat model |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Ollama embedding model used by the legacy retrieval fallback |
| `ATS_MODEL_PATH` | `""` | Direct environment setting for a complete local sentence-transformers model; shared by ATS scoring and document embeddings |

The production backend image sets `ATS_MODEL_PATH=/app/models/all-MiniLM-L6-v2` and loads packaged model weights offline. When blank, local code loads `all-MiniLM-L6-v2` by name. `/health/warm` includes semantic inference health; a healthy vector connection alone does not establish model readiness. Semantic scoring can degrade to the keyword path when model inference is unavailable.

## Vector storage

| Variable | Default | Purpose |
|---|---|---|
| `VECTOR_BACKEND` | `chroma` | Only `chroma` or `qdrant` is valid; another value prevents startup |
| `CHROMA_PERSIST_DIR` | `/app/chroma_data` | Local persistent storage, mounted as a named volume in Compose |
| `QDRANT_URL` | `""` | Cluster URL required to use Qdrant |
| `QDRANT_API_KEY` | `""` | Qdrant credential where authentication is enabled |
| `QDRANT_COLLECTION` | `careerhub` | Shared collection; application operations filter by authenticated user |

Changing the backend or collection does not migrate existing vectors. PostgreSQL records and vector chunks have separate lifecycles; see the deletion limitations in [Security](../SECURITY.md).

The [Keep Warm workflow](../.github/workflows/keepwarm.yml) configures daily cleanup at 03:00 UTC through `/api/v1/admin/lifecycle/run`, using `ADMIN_SECRET` from the `free-prod` GitHub Environment. The six-hour warm schedule is separate. Monitor cleanup authentication and results; the current cleanup covers relational rows, not vector chunks.

## Optional workflow orchestration

| Variable | Default | Purpose |
|---|---|---|
| `N8N_WEBHOOK_URL` | `""` | n8n trigger URL |
| `N8N_WEBHOOK_SECRET` | `""` | Shared secret for workflow requests and callbacks |

`N8N_ENABLED` becomes true when both values are present. Otherwise letter generation uses a local background task. Configure `BASE_URL` for callbacks when enabling n8n. A deployment restart can interrupt in-process work; the stuck-job reaper marks old processing records failed.

## Frontend and local services

| Variable | Default | Purpose |
|---|---|---|
| `API_URL` | `http://api:8000/api/v1` | Frontend process environment: complete API prefix, including `/api/v1` |
| `STREAMLIT_SERVER_RUN_ON_SAVE` | Set to `true` by local Compose | Development reload behavior |
| `STREAMLIT_SERVER_FILE_WATCHER_TYPE` | Set to `poll` by local Compose | Bind-mount file watching |

On a direct host run, set `API_URL=http://localhost:8000/api/v1`; the Docker service name `api` resolves inside the Compose network. Use the hosted backend URL on Streamlit Community Cloud. Local Compose publishes PostgreSQL, Redis, Ollama, API, frontend and Nginx on loopback only, so they are not exposed to the local network by default. Production Nginx ingress is configured separately.

## Operational check

After configuration changes, check `/health`, then inspect every dependency in `/health/warm`. The warm endpoint reports `down` and exception class names in JSON while still returning HTTP 200; details remain in restricted server logs. Verify a real sign-in and one application workflow as well. Never print a populated Compose config or environment dump into shared logs while troubleshooting secrets.

Computed fields (`SQLALCHEMY_DATABASE_URI`, `SQLALCHEMY_ASYNC_DATABASE_URI`, `USE_GROQ`, `N8N_ENABLED`, `CORS_ORIGINS`) are derived from the settings above; do not set them independently.
