# Security policy

AI Career Hub is a portfolio application that handles account details, resumes and generated application material. This document describes implemented controls and their limits; it is not a security certification.

## Reporting a vulnerability

Report vulnerabilities privately through [GitHub Security Advisories](https://github.com/deeason7/ai-career-hub/security/advisories/new) or the repository owner's GitHub profile contact. Include the affected version, reproduction steps and likely impact. Do not include live credentials or another person's resume in a public issue.

The latest release and current `main` branch are maintained. Older releases are not independently supported. This is a single-maintainer project: responses and fixes are best effort, with no contractual response SLA or bug bounty.

## Implemented controls

| Area | Current behavior |
|---|---|
| Account credentials | Passwords are bcrypt hashes. Registration requires at least 12 characters, a digit, and an uppercase character or symbol; the password cannot equal the account email. JWT signing keys must be at least 32 characters. |
| API authentication | HS256 access JWTs expire after 60 minutes by default. Refresh JWTs expire after seven days. Authentication checks token type, expiry, subject and token ID. |
| Refresh and logout | Refresh rotates both tokens and records revocation in Redis. Logout attempts to revoke the supplied refresh and access tokens. The frontend preserves the rotated refresh token for the next refresh. |
| Account isolation | Protected resource routes check the authenticated owner. Chroma uses per-user collections; Qdrant queries use a mandatory user filter in a shared collection. |
| Admin operations | Admin endpoints require a separate secret of at least 32 characters; an unset secret disables access. |
| API response headers | Middleware adds frame, content-type, referrer, cross-origin and permissions restrictions. The JSON API has a restrictive CSP; development documentation has a separate policy. `PRODUCTION=true` adds HSTS and disables Swagger/ReDoc. |
| URL import | The job fetcher permits HTTP(S), checks resolved addresses against private/reserved ranges and validates redirect targets before requesting them. |
| Input handling | Pydantic validates request schemas. Selected text fields are cleaned with `sanitize_text`; selected LLM paths strip role delimiters and instruction wrappers. These are partial defenses, not a guarantee against prompt injection. |
| Health diagnostics | `/health/warm` exposes dependency state and exception class names, with detailed failures in server logs. It returns HTTP 200 even for a degraded dependency, so monitors must inspect the JSON body. |
| Secrets and local services | Secret environment files and Streamlit secrets are excluded from source/build contexts. Local Compose binds published ports to `127.0.0.1`. Production Compose rejects an unset or empty Redis password. Published development/test credentials must never be reused in deployment. |

### Session storage and availability tradeoffs

The backend issues its refresh cookie as HttpOnly and SameSite=Lax, with Secure enabled when `PRODUCTION=true`. The Streamlit frontend receives that cookie through a server-side HTTP client and keeps it in server-side session state. It does **not** persist the refresh token in the browser.

The frontend's browser `auth_token` cookie contains the access token and is written through a JavaScript cookie component. It is **not HttpOnly** and is exposed to successful script injection. A new Streamlit session can restore only an unexpired browser access token; a refresh token does not survive a lost server-side session. API cookie flags do not protect this separate frontend cookie.

Redis revocation deliberately fails open when Redis is missing or unreachable. Previously revoked tokens can therefore remain usable until their JWT expiry, and refresh replay protection is reduced during an outage. Refresh checking and revocation are separate operations, so rotation is not an atomic single-use guarantee under concurrent requests. These are known design limitations.

### Rate limits

Limits apply to decorated routes, **not every authenticated route**. Limits are per client IP:

| Operation | Requests per minute |
|---|---:|
| Register / login / refresh | 3 / 5 / 20 |
| ATS score, skill gap, interview questions, match analysis | 20 |
| Cover-letter generate/refine and Quick Apply analysis | 5 |
| Job URL fetch | 10 |
| Warm health probe | 30 |

The limiter uses Redis when configured, with per-process memory fallback if Redis fails. `TESTING=true` bypasses these decorators and must never be enabled in a deployed application. Proxy address handling and network restrictions must match the actual hosting arrangement. Uploads, RAG operations and other undecorated routes do not have equivalent application quotas.

## Data handling

Account data, extracted resume text, generated letters and tracker records are stored in PostgreSQL; retrieval chunks and embeddings are stored in the selected vector service. Relevant text is sent to the configured LLM service. The hosted and local providers are described in [Deployment](DEPLOYMENT.md) and [Configuration](docs/CONFIGURATION.md).

The first resume is permanent unless explicitly deleted; later resumes and cover letters receive 15-day expiry timestamps, with a backend promotion helper but no exposed pin/unpin route. The [Keep Warm workflow](.github/workflows/keepwarm.yml) schedules lifecycle cleanup at 03:00 UTC daily by calling the secret-protected admin endpoint. Monitor its authenticated execution and deletion results; an expiry timestamp alone does not guarantee erasure.

The current lifecycle cleanup removes relational rows but does not remove their vector chunks. Explicit resume deletion requests cleanup of that resume's vectors on a best-effort basis; it cascades deletion of related letter records without removing their letter/job-description vectors. There is no dedicated cover-letter delete endpoint. Complete retention and deletion across both stores remains follow-up work; do not interpret the TTL as a guaranteed erasure deadline.

The application audit table hashes client IP addresses and records selected events such as authentication, resume upload and letter generation. This does not anonymize all operational data: hosting/access/error logs may contain IPs or diagnostic details, and audit records retain account identifiers. Sentry disables default PII capture, but that flag is not a universal log-redaction guarantee. Restrict log access and avoid adding document text, tokens or credentials to logs.

## Deployment and dependency boundaries

Hosted secrets belong in provider secret stores and GitHub Environments; the retained AWS deployment uses SSM Parameter Store. HTTPS terminates at the hosting edge or AWS Nginx. The API's headers and CORS settings do not automatically configure the separate Streamlit host. Configure frontend origins explicitly and keep dependency/model artifacts from trusted sources.

CI runs `pip-audit` against backend requirements with accepted-risk exceptions in [the pipeline](.github/workflows/pipeline.yml); the existing rationale is in [backend requirements](backend/requirements.txt). A green audit with exclusions is not a clean vulnerability report. Exceptions and the frontend dependency tree need review when updating packages; a source scan also cannot establish that credentials were never exposed elsewhere.

The [2026-10-28 dependency review](docs/DEPENDENCY_REVIEW.md) checked 177 package/version records from the 2026-10-27 Docker builds without exclusions. It found advisories affecting six backend packages and reproduced a JWT header-parsing failure on Python 3.11. PyJWT is now pinned to 2.15.0. On 2026-10-28, all 363 backend tests passed, including four malformed-header regressions covering token helpers and HTTP routes. The rebuilt production image also verified the installed JWT version, non-root execution and offline model scoring. This change remains unreleased; the remaining dependency findings and a complete audit are still release gates.

Before a wider release, prioritize complete cross-store deletion, durable server-managed browser sessions, atomic refresh revocation, route/resource quotas and dependency exception review. URL validation also leaves a DNS-resolution/request timing gap: redirects are checked, but destination addresses are not pinned for the outbound connection. Infrastructure egress controls remain necessary defense in depth.
