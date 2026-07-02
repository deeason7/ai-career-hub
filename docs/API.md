# API Reference

Complete reference for the AI Career Hub HTTP API.

For an interactive, always-current version, browse the auto-generated OpenAPI docs
at `/docs` (Swagger UI) when running locally. The raw schema is served at
`/api/v1/openapi.json`. In production the docs UI is disabled.

- [Base URL & versioning](#base-url--versioning)
- [Authentication](#authentication)
- [Conventions](#conventions)
- [Rate limits](#rate-limits)
- [Asynchronous jobs](#asynchronous-jobs)
- [Endpoints](#endpoints)
  - [Health & meta](#health--meta)
  - [Authentication](#authentication-auth)
  - [Resumes](#resumes-resumes)
  - [Cover letters](#cover-letters-cover-letters)
  - [AI tools](#ai-tools-ai)
  - [Analysis](#analysis-analysis)
  - [Agent](#agent-agent)
  - [Job tracker](#job-tracker-jobs)
  - [RAG](#rag-rag)
  - [Admin](#admin-admin)
  - [Webhooks](#webhooks-webhooksn8n)

---

## Base URL & versioning

All application endpoints are mounted under a versioned prefix:

```
https://careerhub.deeason.com.np/api/v1
http://localhost:8000/api/v1        # local Docker
```

Health and service-metadata endpoints (`GET /`, `GET /health`, and
`GET /health/warm`) live at the root, **outside** the `/api/v1` prefix, so that
load balancers and uptime checks do not depend on the API version.

The API is versioned in the URL path. Breaking changes are introduced under a new
prefix (`/api/v2`) rather than mutating `/api/v1`.

---

## Authentication

The API uses **JWT bearer tokens** for stateless request authentication, plus an
**HttpOnly refresh cookie** for silent token renewal.

| Token | Transport | Lifetime | Purpose |
|---|---|---|---|
| Access token | `Authorization: Bearer <jwt>` header | Short (minutes) | Authorises each API call |
| Refresh token | `refresh_token` HttpOnly cookie | Long (days) | Mints new access tokens |

**Flow:**

1. `POST /auth/login` with form credentials → returns an access token in the body
   and sets the refresh cookie.
2. Send the access token as `Authorization: Bearer <token>` on every protected
   request.
3. When the access token expires, call `POST /auth/refresh` (the browser sends the
   cookie automatically) to obtain a fresh access token.
4. `POST /auth/logout` revokes the current token (its JTI is added to a Redis
   denylist) and clears the refresh cookie.

Every authenticated request is checked against the revocation denylist and the
user's `is_active` flag, so a logged-out or deactivated token is rejected even
before it expires.

Two machine-to-machine endpoints use a **shared secret header** instead of JWT:

| Endpoint | Header |
|---|---|
| `POST /admin/lifecycle/run` | `X-Admin-Secret` |
| `PUT /webhooks/n8n/cover-letters/{id}/callback` | `X-Webhook-Secret` |

---

## Conventions

- **Request bodies** are JSON (`Content-Type: application/json`) unless noted.
  Resume upload uses `multipart/form-data`; login uses
  `application/x-www-form-urlencoded` (OAuth2 password form).
- **IDs** are UUIDs.
- **Timestamps** are ISO 8601 (UTC).
- **Errors** follow FastAPI's shape:

  ```json
  { "detail": "Human-readable message" }
  ```

  Validation errors (`422`) return the standard FastAPI list of field errors.

| Status | Meaning |
|---|---|
| `200 OK` | Success |
| `201 Created` | Resource created |
| `202 Accepted` | Async job queued — poll for the result (see below) |
| `204 No Content` | Success, no body |
| `401 Unauthorized` | Missing / invalid / revoked token |
| `403 Forbidden` | Inactive user, or bad admin/webhook secret |
| `404 Not Found` | Resource not found or not owned by the caller |
| `422 Unprocessable Entity` | Request body or query failed validation |
| `429 Too Many Requests` | Rate limit exceeded |
| `502 Bad Gateway` | Upstream LLM call failed |
| `503 Service Unavailable` | Backing service (LLM / queue) temporarily busy |

All data endpoints are **scoped to the authenticated user**. Requesting another
user's resource returns `404`, not `403`, so the API never confirms the existence
of resources you do not own.

---

## Rate limits

Limits are enforced per client by `slowapi` (Redis-backed in production). Exceeding
a limit returns `429`. Limits are disabled in the test suite (`TESTING=true`).

| Endpoint | Limit |
|---|---|
| `POST /auth/register` | 3 / min |
| `POST /auth/login` | 5 / min |
| `POST /auth/refresh` | 20 / min |
| `POST /cover-letters/generate` | 5 / min |
| `POST /cover-letters/{id}/refine` | 5 / min |
| `POST /ai/ats-score` | 20 / min |
| `POST /ai/skill-gap` | 20 / min |
| `POST /ai/interview-questions` | 20 / min |
| `POST /ai/fetch-job` | 10 / min |
| `POST /analysis/job-match` | 20 / min |
| `POST /agent/analyze` | 5 / min |

---

## Asynchronous jobs

LLM-heavy operations return **`202 Accepted`** immediately with a `task_id`, then
run in the background. Poll the matching `task/{task_id}` endpoint until `status`
is `completed` or `failed`.

```
POST /api/v1/agent/analyze            → 202 { "task_id": "...", "status": "pending" }
GET  /api/v1/agent/task/{task_id}     → 200 { "status": "running", "steps": [...] }
GET  /api/v1/agent/task/{task_id}     → 200 { "status": "completed", "result": {...} }
```

Task state is held in Redis with a 1-hour TTL. Polling endpoints return `404`
once a task has expired or never existed. The async operations are:

| Kick-off | Poll |
|---|---|
| `POST /cover-letters/generate` | `GET /cover-letters/task/{task_id}` |
| `POST /cover-letters/{id}/refine` | `GET /cover-letters/task/{task_id}` |
| `POST /analysis/job-match` | `GET /analysis/task/{task_id}` |
| `POST /agent/analyze` | `GET /agent/task/{task_id}` |

---

## Endpoints

### Health & meta

#### `GET /`
Service metadata. **No auth.**

```json
{ "service": "AI Career Hub", "version": "4.3.0", "status": "healthy", "docs": "/docs" }
```

#### `GET /health`
Liveness probe. **No auth.** Returns `{ "status": "ok" }`.

#### `GET /health/warm`
Deep warm-up probe. **No auth.** · Rate limit: 30/min. Touches Postgres (`SELECT 1`), Redis (`PING`), and the configured vector store with one cheap call each, then **always** returns `200` with per-dependency status — so a single degraded backend never makes the probe itself look down. An external scheduler hits it on a short interval to keep managed free-tier backends resident.

```json
{ "api": "ok", "db": "ok", "redis": "ok", "vector": { "backend": "qdrant", "status": "ok" }, "ts": 1751457600 }
```

`db` and `redis` are `ok` | `down` (`redis` is also `disabled` when unconfigured); `vector.status` is `ok` | `down`.

---

### Authentication (`/auth`)

#### `POST /auth/register`
Create a user account. **No auth.** · Rate limit: 3/min

**Body**
```json
{ "email": "you@example.com", "password": "at-least-12-chars", "full_name": "Jane Doe" }
```
Password policy: ≥ 12 chars, must include a digit and an uppercase letter or symbol.

**Returns** `201` · `UserRead` (`id`, `email`, `full_name`, `is_active`).

#### `POST /auth/login`
Exchange credentials for an access token. **No auth.** · Rate limit: 5/min

**Body** (`application/x-www-form-urlencoded`): `username` (the email), `password`.

**Returns** `200` · `{ "access_token": "...", "token_type": "bearer" }` and sets the
`refresh_token` HttpOnly cookie.

#### `POST /auth/refresh`
Mint a new access token from the refresh cookie. **No auth header** (uses cookie). · Rate limit: 20/min

**Returns** `200` · `{ "access_token": "...", "token_type": "bearer" }`.

#### `POST /auth/logout`
Revoke the current access token and clear the refresh cookie. **Auth required.**

**Returns** `204`.

#### `GET /auth/me`
Return the current user. **Auth required.**

**Returns** `200` · `UserRead`.

---

### Resumes (`/resumes`)

#### `POST /resumes/upload`
Upload and parse a resume (PDF / DOCX / TXT). **Auth required.**

**Body** (`multipart/form-data`): `name` (string, ≤ 100 chars), `file` (the document).

On upload the file is text-extracted, LLM-parsed into structured JSON, and embedded
into the user's vector collection. A 15-day TTL applies unless the resume is marked
permanent.

**Returns** `201` · `ResumeRead`.

#### `GET /resumes/`
List the caller's resumes. **Auth required.** → `200` · `list[ResumeRead]`.

#### `GET /resumes/{resume_id}`
Get one resume including its raw text. **Auth required.** → `200` · `ResumeReadWithText` · `404` if not found.

#### `PUT /resumes/{resume_id}/activate`
Mark a resume as the active one (used by default in generation). **Auth required.** → `200` · `ResumeRead`.

#### `DELETE /resumes/{resume_id}`
Delete a resume and its embeddings. **Auth required.** → `204`.

#### `GET /resumes/{resume_id}/analysis`
Return the stored structured analysis of a resume. **Auth required.** → `200`.

---

### Cover letters (`/cover-letters`)

#### `POST /cover-letters/generate`
Queue cover-letter generation. **Auth required.** · Rate limit: 5/min · **Async**

**Body** (`CoverLetterCreate`)
```json
{ "job_description": "…(50–10000 chars)…", "resume_id": "uuid (optional)" }
```
If `resume_id` is omitted, the active resume is used. The pipeline generates the
letter, runs an AI-as-a-Judge QA pass (honesty/tone), auto-regenerates if honesty
scores low, and auto-creates a "wishlist" tracker entry.

**Returns** `202` · `CoverLetterRead` with `task_id` and `status: "pending"`.

#### `GET /cover-letters/task/{task_id}`
Poll generation **or** refine status. **Auth required.** → `200` with `status` of
`pending` | `completed` | `failed`.

#### `GET /cover-letters/`
List the caller's cover letters. **Auth required.** → `200` · `list[CoverLetterRead]`.

#### `GET /cover-letters/{cover_letter_id}`
Get one cover letter, including QA scores. **Auth required.** → `200` · `CoverLetterRead` · `404`.

#### `GET /cover-letters/{cover_letter_id}/pdf`
Download the letter as a server-rendered PDF. **Auth required.** → `200` · `application/pdf`.

#### `POST /cover-letters/{cover_letter_id}/refine`
Queue a refinement, optionally branching from a specific prior version. **Auth required.** · Rate limit: 5/min · **Async**

**Body** (`CoverLetterRevisionCreate`)
```json
{ "command": "Make it more concise (3–1000 chars)", "base_version": 2 }
```
`base_version` (optional, ≥ 1) selects the revision to branch from; omit it to refine
the latest. An unknown `base_version` returns `404` ("Base revision not found.").

**Returns** `202` · `CoverLetterRevisionRead` (poll via `/cover-letters/task/{task_id}`).

#### `GET /cover-letters/{cover_letter_id}/revisions`
List the revision history (lineage). **Auth required.** → `200` · `list[CoverLetterRevisionRead]`.

#### `POST /cover-letters/{cover_letter_id}/revisions/{version_number}/activate`
Promote a revision to be the cover letter's active text. **Auth required.** → `200` · `CoverLetterRead`.

---

### AI tools (`/ai`)

All four accept a job description (and optional `resume_id`); the active resume is
used when `resume_id` is omitted. **Auth required.**

The shared body for `ats-score`, `skill-gap`, and `interview-questions` is:
```json
{ "job_description": "…(≤10000 chars)…", "resume_id": "uuid (optional)" }
```

#### `POST /ai/ats-score`
Hybrid ATS score (50% semantic + 30% keyword + 20% structure) with a section
breakdown. · Rate limit: 20/min → `200`.

#### `POST /ai/skill-gap`
Skill-gap analysis with recommendations. · Rate limit: 20/min → `200` · `502` if the LLM call fails.

#### `POST /ai/interview-questions`
Generate 5–15 tailored interview questions. · Rate limit: 20/min → `200` · `502` if the LLM call fails.

#### `POST /ai/fetch-job`
Scrape a job posting from a URL (LinkedIn / Greenhouse / Lever / Workday). · Rate limit: 10/min

**Body**
```json
{ "url": "https://… (http/https only, ≤2000 chars)" }
```
The URL is validated as an HTTP(S) URL (SSRF guard blocks `file://`, `ftp://`, and
internal addresses). → `200` · `422` for a malformed or disallowed URL.

---

### Analysis (`/analysis`)

#### `POST /analysis/job-match`
Combined ATS score + skill gap + interview questions in one async job. **Auth required.** · Rate limit: 20/min · **Async**

**Body** (`JobMatchRequest`)
```json
{ "resume_id": "uuid", "job_description": "…(≤10000 chars)…" }
```

**Returns** `202` with a `task_id` · `503` if the LLM is busy · `502` on failure.

#### `GET /analysis/task/{task_id}`
Poll the combined analysis. **Auth required.** → `200` with `status` and partial/full results.

---

### Agent (`/agent`)

#### `POST /agent/analyze`
Run the full 7-step LangGraph pipeline from a single job URL:
scrape → extract metadata → research company → ATS score → skill gap → cover letter
→ interview questions. **Auth required.** · Rate limit: 5/min · **Async**

**Body** (`AgentRequest`)
```json
{ "job_url": "https://… (≥10 chars)", "resume_id": "uuid" }
```

**Returns** `202` with a `task_id`. The final result reports an overall `status` of
`completed` | `partial` | `failed`, plus per-step timing and any captured errors.

#### `GET /agent/task/{task_id}`
Poll the agent run. **Auth required.** → `200` with `status` and accumulated `steps` ·
`503` if the task store is unavailable · `404` if the task is unknown/expired.

---

### Job tracker (`/jobs`)

> Mounted at `/jobs` (not `/tracker`).

#### `POST /jobs/`
Create an application entry. **Auth required.**

**Body** (`JobApplicationCreate`)
```json
{
  "company": "Acme",
  "role": "Backend Engineer",
  "job_url": "https://… (optional)",
  "status": "wishlist",
  "notes": "optional",
  "applied_at": "2026-06-15T00:00:00Z (optional)",
  "deadline": "2026-06-30 (optional)"
}
```
`status` defaults to `wishlist`. → `201` · `JobApplicationRead`.

#### `GET /jobs/`
List applications. **Auth required.** → `200` · `list[JobApplicationRead]`.

#### `GET /jobs/stats`
Aggregate counts by status for the dashboard. **Auth required.** → `200`.

#### `PATCH /jobs/{app_id}`
Partial update (any subset of fields). **Auth required.**

**Body** (`JobApplicationUpdate`) — all fields optional: `company`, `role`,
`job_url`, `status`, `notes`, `applied_at`, `deadline`.

→ `200` · `JobApplicationRead` · `404`.

#### `DELETE /jobs/{app_id}`
Delete an application. **Auth required.** → `204`.

---

### RAG (`/rag`)

#### `GET /rag/stats`
Embedding-collection stats for the caller (counts by source type). **Auth required.** → `200`.

#### `POST /rag/search`
Semantic search across the caller's indexed documents. **Auth required.**

**Body** (`RAGSearchRequest`)
```json
{ "query": "…(≤2000 chars)…", "top_k": 6, "source_types": ["resume", "cover_letter"] }
```
`top_k` is 1–20 (default 6); `source_types` is optional. → `200` · `list[RAGSearchResult]`.

#### `POST /rag/reindex`
Rebuild the caller's embeddings. **Auth required.** → `202`.

---

### Admin (`/admin`)

#### `POST /admin/lifecycle/run`
Trigger the document lifecycle cleanup (15-day TTL purge of expired resumes and
cover letters). **Not a user endpoint** — authenticated by the `X-Admin-Secret`
header, not JWT. → `200` · `403` if the secret is missing or wrong.

---

### Webhooks (`/webhooks/n8n`)

#### `PUT /webhooks/n8n/cover-letters/{cover_letter_id}/callback`
Callback used by the n8n orchestration path to deliver a generated cover letter
back to the API. Authenticated by the `X-Webhook-Secret` header (constant-time
compared). → `200` · `401` on a bad secret · `404` if the cover letter is unknown ·
`503` if the webhook path is not configured.
