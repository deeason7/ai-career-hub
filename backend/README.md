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

FastAPI backend for AI Career Hub. This directory is also the build context for
the Hugging Face Space (Docker SDK): the Space builds `Dockerfile` and serves
the app on port `8000`. The front-matter above is what the Space reads — it is
ignored everywhere else.

- **Run it locally / on AWS:** see the repository root `README.md` and
  `DEPLOYMENT.md`.
- **Configuration:** `app/core/config.py` is env-driven. The managed-provider
  flags (`VECTOR_BACKEND`, `DB_SSLMODE`, `REDIS_SSL`, `QDRANT_*`) default to the
  AWS-safe values, so the same image runs on AWS (flags unset) and on the
  free-tier stack (flags set).

Health endpoints: `GET /health` (liveness) and `GET /health/warm` (deep probe
that touches Postgres, Redis and the vector store, always `200`).
