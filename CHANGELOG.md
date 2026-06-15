# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Targeting **v4.2.0** — async analysis, resilience under rate limits, and refine branching.

### Added
- Async job-match analysis: `POST /api/v1/analysis/job-match` returns `202` with a task id, and `GET /api/v1/analysis/task/{task_id}` polls status with live per-step progress. State is held in a Redis task store with one hash field per step, so parallel workers never clobber a shared blob.
- Async agentic analysis: `POST /api/v1/agent/analyze` returns `202`, and `GET /api/v1/agent/task/{task_id}` streams a live step checklist. The seven-step pipeline runs as a background task; the UI renders from polled state and survives navigating away mid-run.
- Refine a cover letter from any past revision via an optional `base_version`; revision lineage is tracked through a self-referencing parent link (migration `011`).
- `LLMRateLimitedError` plus an `on_busy` callback that surfaces a "model busy — retrying" status in the UI.
- Resume parse failures persist a `parse_failed` marker that surfaces an honest warning instead of an empty analysis.

### Changed
- `POST /api/v1/agent/analyze` is now rate-limited to 5/min and runs on an async session.
- The job-match fan-out is serialised to fit the provider token-per-minute budget (parallel calls would trip the limiter).
- ATS keyword extraction strips EEO/benefits boilerplate, applies a tech-term whitelist (`ai`, `ml`, `ci`…), and de-duplicates phrase n-grams, so matched and missing keywords read like real skills rather than posting noise.
- `call_structured` backs off on provider `429`s with capped exponential retry, honouring the server `Retry-After`.

### Fixed
- The session no longer drops on reload or in a duplicate tab — a bounded wait-for-hydration gate restores the cookie-bridged session before concluding logged-out.

## [4.1.0] - 2026-06-05

Agentic pipeline, RAG, and a release-hardening sweep.

### Added
- Agentic analysis pipeline (LangGraph): one job URL drives scrape → company research → ATS score → skill-gap → cover letter → interview questions in a single run (`POST /api/v1/agent/analyze`).
- Retrieval-augmented generation (ChromaDB): persistent per-user vector collections; resumes auto-embed on upload, cover letters and job descriptions are indexed after generation, with a FAISS fallback (`/api/v1/rag/stats` · `/search` · `/reindex`).

### Changed
- Content-Security-Policy scoped so the strict `default-src 'none'` no longer breaks the API docs in development.

### Security
- Prompt-injection guard broadened: role labels matched at any line start, LLaMA 3 chat-template tokens, and "ignore previous instructions" override phrases — on both the local and n8n dispatch paths.
- Constant-time secret comparison (`hmac.compare_digest`) for the admin and n8n webhook shared secrets.
- SSRF hardening on job-URL import: resolve and validate the target host IP, reject private/loopback/link-local/metadata ranges, and re-validate every redirect hop.

### Fixed
- Stuck-generation reaper: a `started_at` timestamp plus a watchdog that fails cover letters orphaned in `processing` by a restart or instance sleep.
- Refinement version numbers are assigned under a row lock; the generation poll returns `404` for an unknown or expired task; a job-description minimum length is enforced.
- Frontend: access-token refresh on `401` to prevent silent logouts, dashboard cold-start handling with honest error states, and login/register timeouts.
- Widened the `alembic_version` column so a fresh-from-empty migration run succeeds.

## [4.0.2] - 2026-06-02

Code cleanup and security hardening.

### Security
- Password minimum raised from 8 to 12 characters.
- Three new security headers: `X-Permitted-Cross-Domain-Policies`, `Cross-Origin-Resource-Policy`, `Cross-Origin-Opener-Policy`.
- Audit log expanded: `auth.register` and `auth.login.failed` events are now captured (brute-force detection).
- Prompt-injection regex expanded to cover LLaMA 2 / Mixtral delimiters: `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`, `<|im_end|>`.

### Added
- New test files: `test_security_headers.py`, `test_password_policy.py`.

### Changed
- Consolidated comments and multi-line docstrings to concise one-line summaries across seven backend files.

## [4.0.1] - 2026-05-31

Authentication fix and branch sync.

### Fixed
- `verify_token` tuple unpack in `deps.py` (a production `AttributeError`).
- Seven frontend bugs: cookie `TypeError` crash, sidebar visible to guests, logout token revocation, PDF N+1 requests, a 502 crash, the register hint, and a stray component banner.

### Changed
- Synced `develop` with `main` (it had fallen five commits behind after v4.0.0).

## [4.0.0] - 2026-05-20

OWASP hardening, auto-tracker, the refinement system, and a modular frontend.

### Added
- 15-day document lifecycle with expiry badges and nightly cleanup.
- Application tracker auto-populated from cover-letter generation via LLM metadata extraction.
- Cover-letter refinement: targeted edit commands, full revision history, one-click rollback.
- Streamlit frontend refactored from a 1,235-line monolith into a modular `pages/` architecture, with toast notifications and a shared `components.py` layer.

### Security
- OWASP A03/A07/A09 hardening: prompt-injection sanitisation, rate limiting, and audit logging with SHA-256 IP hashing.
- SSRF protection on the job-URL import endpoint.
- Dependency scanning via `pip-audit` in CI.

## [3.0.0] - 2026-04-13

Structured output and orchestration.

### Added
- Structured LLM output via `instructor` + Pydantic v2 (typed, validated contracts).
- AI-as-a-Judge QA layer — honesty/tone scoring with auto-regeneration (up to 2× retries).
- n8n Cloud workflow orchestration — event-driven webhooks with graceful fallback to local `BackgroundTasks`.
- Automated CD: GitHub Actions → ECR → EC2 via SSM.

## [2.6.0] - 2026-04-11

Business-hours scheduling and CI.

### Added
- EventBridge Scheduler: start 9 AM / stop 6 PM ET, Mon–Fri.
- Pre-commit hooks: ruff lint + format plus file hygiene.
- CI: ruff check + format + pytest in GitHub Actions.

## [2.5.0] - 2026-04-11

Performance and reliability.

### Changed
- Lambda EC2 + RDS status checks parallelised (~400 ms versus ~1.3 s).
- gzip compression on nginx for JS/CSS/JSON.
- Streamlit starts on `service_started` for an earlier warm-up.

### Added
- Wake page: DNS poll with a manual button fallback.

## [2.0.0] - 2026-04-11

AWS production deployment.

### Changed
- Migrated from Render/Supabase to AWS EC2 + RDS.
- Replaced Celery with FastAPI `BackgroundTasks`.

### Added
- Secrets managed via AWS SSM Parameter Store.
- Wake-on-Visit infrastructure (Route 53 failover → CloudFront → Lambda).

### Security
- Hardened IAM — least-privilege policies, MFA, IMDSv2.

[Unreleased]: https://github.com/deeason7/ai-career-hub/compare/v4.1.0...develop
[4.1.0]: https://github.com/deeason7/ai-career-hub/releases/tag/v4.1.0
[4.0.0]: https://github.com/deeason7/ai-career-hub/releases/tag/v4.0.0
[3.0.0]: https://github.com/deeason7/ai-career-hub/releases/tag/v3.0.0
[2.6.0]: https://github.com/deeason7/ai-career-hub/releases/tag/v2.6.0
[2.5.0]: https://github.com/deeason7/ai-career-hub/releases/tag/v2.5.0
