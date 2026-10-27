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

The API turns a resume and job posting into match feedback, reviewable cover-letter
drafts, interview preparation and a tracked application. FastAPI handles requests;
PostgreSQL stores user-owned records; Redis holds temporary task and session state;
the shared MiniLM encoder supports matching and document retrieval.

This directory is the Hugging Face Space's Docker build context. Keep the front matter:
the host reads it to select `Dockerfile` and port `8000`. The frontend is a separate
Streamlit application. Active hosting, configuration and recovery instructions live in
the [deployment guide](https://github.com/deeason7/ai-career-hub/blob/main/DEPLOYMENT.md).

## Develop and verify

Run these from the repository root:

```bash
make up           # local stack; configuration setup is in the root README
make test         # backend lint/tests, isolated careerhub_test database
make test-probes  # deployment-monitor tests; Python standard library only
make evals        # model-backed ATS checks against synthetic labeled pairs
```

`Dockerfile.dev` includes the existing test tools; `Dockerfile` builds the production
API and bundled embedding model. Never run the test fixtures against a development
or production database: they recreate the test schema.

## API contracts

| Endpoint | Purpose |
|---|---|
| `GET /health` | Process liveness; no dependency guarantee |
| `GET /health/warm` | Database, Redis, vector-store and semantic-inference checks; inspect the body even on HTTP 200 |
| `/api/v1/*` | Authenticated application routes, with explicit public authentication/webhook exceptions |

The semantic readiness field is newer than released v4.4.3. Check
[project status](https://github.com/deeason7/ai-career-hub/blob/main/docs/PROJECT_STATUS.md)
before interpreting an older deployment's response.

- [API reference](https://github.com/deeason7/ai-career-hub/blob/main/docs/API.md)
- [Configuration](https://github.com/deeason7/ai-career-hub/blob/main/docs/CONFIGURATION.md)
- [Evaluation guide](evals/README.md)
