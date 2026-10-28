# Contributing to AI Career Hub

[Project home](README.md) · [Documentation](docs/README.md) · [Refactoring plan](docs/REFACTORING_PLAN.md)

Build changes around a completed applicant task. This guide covers local setup,
verification, and the branch/review conventions for this portfolio project.

---

## Branch Strategy

```
main       <- production-only, protected, never commit directly
develop    <- integration branch, base for all feature PRs
feature/*  <- new features
fix/*      <- bug fixes
chore/*    <- maintenance (deps, docs, config)
security/* <- security hardening
docs/*     <- documentation-only changes
```

**Flow:**
```
feature/my-feature -> develop (PR + CI must pass) -> main (PR + CI + Deploy)
```

- Never push directly to `main` or `develop`
- Force-push is disabled on protected branches
- All merges to `main` go through CI (lint, test, build)

---

## Commit Conventions

Use [Conventional Commits](https://www.conventionalcommits.org/):

```
type(scope): short description
```

**Types:** `feat`, `fix`, `chore`, `refactor`, `test`, `docs`, `perf`, `security`

**Examples:**
```
feat(api): add POST /cover-letters/{id}/refine endpoint
fix(auth): correct token expiry calculation
chore(deps): bump fastapi 0.111 -> 0.136
security: add prompt injection sanitization to cover letter service
test: add tests for lifecycle cleanup service
```

**Rules:**
- Subject line ≤ 72 characters
- Imperative mood ("add", not "added")
- No period at end of subject line
- Write like a senior engineer: concise, imperative, no filler.

---

## Running Locally

### Prerequisites

- Docker with Compose and a running engine.
- Python 3.11+ for host-side maintenance commands; application containers use 3.11.
- A Groq API key, or enough local resources to run the configured Ollama models.

### Configure your development stack

From the repository root, copy the template if you do not already have a local file:

```bash
cp backend/.env.example backend/.env
```

Edit these values in `backend/.env`:

| Setting | Local value |
|---|---|
| `POSTGRES_SERVER` | `db`, the Compose service name |
| `POSTGRES_USER`, `POSTGRES_DB` | Choose local names, for example `careerhub_local` and `careerhub` |
| `POSTGRES_PASSWORD` | A unique local value; hexadecimal avoids the current database URL's reserved-character limitation |
| `SECRET_KEY` | A separate random signing key, at least 32 characters |
| `GROQ_API_KEY` | Your key for hosted generation; leave blank to select Ollama |
| `PRODUCTION`, `TESTING` | Keep both `false` for ordinary local use |

Generate independent values for the database password and signing key:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Start with the same environment file used for Compose interpolation:

```bash
docker compose --env-file backend/.env config --quiet
docker compose --env-file backend/.env up --build -d
```

The API's service-level `env_file` populates its container. The CLI `--env-file`
also supplies the database service's `${POSTGRES_*}` values. These are separate
steps; omitting the CLI flag can leave the database and API using different
credentials. See [Docker's interpolation guide](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/)
and the project's [configuration reference](docs/CONFIGURATION.md).

Existing database volumes keep the credentials used at initialization. Editing an
environment file does not change those credentials; use the matching local settings
or deliberately migrate the database. Keep populated environment files out of Git.

### Choose the model provider

A nonempty Groq key selects hosted generation. For local Ollama, leave the key blank
and pull both the chat model and the legacy retrieval embedding model:

```bash
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama pull nomic-embed-text
```

The first image build and model downloads need internet access. MiniLM is downloaded
on first use in development; the production Dockerfile packages it during the build.

### Open the workspace

- [Frontend](http://localhost:8501)
- [API liveness](http://localhost:8000/health)
- [Development API docs](http://localhost:8000/docs)

Use the [sample application walkthrough](README.md#try-your-first-application) to
exercise the workflow. Stop containers with `docker compose down`; named data
volumes are retained.

### Run tests

Frontend, maintenance, documentation and scoring checks:

```bash
make test-frontend  # tests in the frontend image
make test-probes    # stdlib readiness, documentation and release checks
make docs-check     # local links, anchors and current release versions
make evals          # real-model scoring checks; first run may download MiniLM
```

The backend test service uses a separate `careerhub_test` database and recreates its
schema. **Never point tests at application data or a hosted database.** With the
custom database credentials from the setup above, override only the test login:

```bash
docker compose --env-file backend/.env \
  -f docker-compose.yml -f - run --rm --build test <<'YAML'
services:
  test:
    environment:
      POSTGRES_USER: ${POSTGRES_USER:?Set your local database user}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?Set your local database password}
YAML
```

This keeps the test service's `db` host, `careerhub_test` database, test signing key,
and mocked provider configuration. [Compose merges the override](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/)
by environment-variable name. If your existing local stack uses the published
Compose development defaults, `make test` remains the shorthand.

`TESTING=true` is set in the test service and CI to disable route rate limits.
Keep it false in the normal application. Eight live-LLM tests are expected failures
without provider credentials; the regression suite uses mocks for external generation.

### Troubleshooting

| Symptom | First check |
|---|---|
| Cannot connect to Docker | Start the engine and check `docker info` |
| Database password authentication fails | Use `--env-file backend/.env`; verify credentials match the existing volume |
| Port already in use | Check other services using 5432, 6379, 8000, 8501, 11434, or 80 |
| Ollama reports a missing model | Run the two model pulls above and inspect `docker compose logs --tail=80 ollama` |
| API is live but a feature fails | Inspect `/health/warm` and `docker compose logs --tail=80 api`; liveness alone does not establish dependency readiness |
| Hosted demo displays a sleep page | Follow [deployment recovery](DEPLOYMENT.md#readiness-and-incident-recovery) |

### Run linter
```bash
ruff check backend/ frontend/
ruff format --check backend/ frontend/
```

All commits must pass ruff lint and format checks. The pre-commit hook enforces this automatically:
```bash
pip install -r backend/requirements.dev.txt
pre-commit install
```

---

## Pull Request Checklist

Before opening a PR to `develop`:

- [ ] Branch name follows `feature/*`, `fix/*`, `chore/*`, or `security/*` convention
- [ ] All commits follow conventional commit format
- [ ] `ruff check backend/ frontend/` passes with zero errors
- [ ] `ruff format --check backend/ frontend/` passes
- [ ] Appropriate backend/frontend regression tests pass; use the documented test-login override for a custom local database
- [ ] `make test-probes` and `make docs-check` pass
- [ ] Product/API/configuration docs reflect changed behavior; historical changelog remains dated
- [ ] No secrets, credentials, or internal identifiers committed
- [ ] No padding comments. Only write comments that explain non-obvious logic.
- [ ] Test passwords must satisfy the registration policy: min 12 characters, 1 digit, 1 uppercase or symbol

---

## Code Style

- **Python:** Ruff-enforced (see `backend/ruff.toml` and `frontend/ruff.toml`). PEP 8 with line length 100.
- **Imports:** Sorted by ruff. Lazy imports inside functions where noted (torch/LangChain).
- **Type hints:** Required on all public function signatures.
- **Docstrings:** One-line summary only. No verbose parameter lists.
- **Comments:** Only for non-obvious logic. Not for explaining what the code does.

---

## What Is In Scope

- Backend (FastAPI, SQLModel, services)
- Frontend (Streamlit pages and components)
- Infrastructure scripts (non-sensitive)
- Tests

## What Is Out of Scope

- Changes to AWS infrastructure configuration
- Changes to secrets management approach
- Replacing or removing the cost-optimization sleep/wake schedule
