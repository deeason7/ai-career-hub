---
title: AI Career Hub API
emoji: 🚀
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 8000
pinned: false
---

# AI Career Hub — API

**The services behind fit feedback, saved application material, and follow-through.**

FastAPI connects résumé parsing, hybrid match analysis, cover-letter generation,
AI review, revisions, PDF export, and application tracking. PostgreSQL stores
user-owned records; Redis holds temporary task/session state; one shared MiniLM
encoder supports matching and document retrieval.

[API contracts](https://github.com/deeason7/ai-career-hub/blob/main/docs/API.md) ·
[Local setup](https://github.com/deeason7/ai-career-hub/blob/main/CONTRIBUTING.md#running-locally) ·
[Deployment](https://github.com/deeason7/ai-career-hub/blob/main/DEPLOYMENT.md) ·
[Scoring evaluations](evals/README.md)

## Start in the right place

This directory is the Hugging Face Space's Docker build context. Keep its YAML
front matter: the host uses it to select Docker and port `8000`. Streamlit is a
separate application under `frontend/`. Repository links above target `main` so they
also work from the mirrored Space; for unreleased changes, consult this branch's docs.

Follow the root setup guide before starting containers. Run commands from the
repository root:

```bash
docker compose --env-file backend/.env up --build -d
make test-frontend
make test-probes
make docs-check
make evals
```

For backend tests, follow **Run tests** in the setup guide: `make test` assumes the
published Compose test credentials; a custom local database needs the documented
login override. Fixtures recreate `careerhub_test`, never application records.

## Find the implementation

| You are changing… | Start here |
|---|---|
| Routes, middleware, readiness | `app/main.py`, `app/api/v1/endpoints/` |
| Settings and database connections | `app/core/config.py`, `app/core/db.py` |
| Application records and revisions | `app/models/`, `migrations/` |
| Drafting and structured model output | `app/services/cover_letter.py`, `app/services/llm_client.py` |
| Fit feedback and retrieval | `app/services/ats_scorer.py`, `app/services/embedding_service.py` |
| Quick Apply and progress | `app/services/agent_graph.py`, `app/services/task_state.py` |
| Regression tests and scoring quality | `tests/`, `evals/` |

Quick Apply currently returns a transient draft. The saved-letter route owns its
QA, revisions, PDF, and tracker handoff; these are separate workflows today.

## Check health at the right level

| Endpoint | Meaning |
|---|---|
| `GET /health` | Process liveness |
| `GET /health/warm` | Database, Redis, vector-store, and semantic inference checks; inspect JSON even on HTTP 200 |
| `/api/v1/*` | Application routes; see the API reference for auth and task contracts |

Semantic readiness is newer than deployed v4.4.3. A missing semantic field in that
release is missing health evidence, not proof its model cannot score.

## Builds and verified baseline

`Dockerfile.dev` includes test tools. `Dockerfile` builds the production API,
saves MiniLM into an explicit directory, and checks offline inference as the
non-root serving user. On **2026-10-27**, the PostgreSQL-backed suite passed **359
checks** with eight expected live-LLM failures; the production image built and passed
all seven scoring gates across 20 pairs offline.

Those results describe the unreleased checkpoint. See
[project status](https://github.com/deeason7/ai-career-hub/blob/main/docs/PROJECT_STATUS.md)
for dated deployment evidence and remaining release checks.
