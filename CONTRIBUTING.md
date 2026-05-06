# Contributing to AI Career Hub

Thank you for your interest. This is a personal portfolio project, but external contributions are welcome under the following guidelines.

---

## Branch Strategy

```
main       <- production-only, protected, never commit directly
develop    <- integration branch, base for all feature PRs
feature/*  <- new features
fix/*      <- bug fixes
chore/*    <- maintenance (deps, docs, config)
security/* <- security hardening
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
- No AI-generated verbosity — write like a senior engineer wrote it

---

## Running Locally

### Prerequisites
- Docker + Docker Compose
- Python 3.11+

### Start the stack
```bash
cp backend/.env.example backend/.env  # fill in values
docker compose up --build
```

- API: http://localhost:8000
- Frontend: http://localhost:8501
- API docs: http://localhost:8000/docs (dev only)

### Run tests
```bash
docker compose run --rm backend pytest backend/tests/ -v
```

Tests run against a real PostgreSQL container (defined in `docker-compose.yml`).

### Run linter
```bash
ruff check backend/
ruff format --check backend/
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
- [ ] `ruff check backend/` passes with zero errors
- [ ] `ruff format --check backend/` passes
- [ ] New endpoints have corresponding tests in `backend/tests/`
- [ ] No secrets, credentials, or internal identifiers committed
- [ ] No AI-generated docstring padding or verbose inline comments

---

## Code Style

- **Python:** Ruff-enforced (see `backend/ruff.toml`). PEP 8 with line length 100.
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
