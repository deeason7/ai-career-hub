# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| Latest on `main` | ✅ |
| Older releases | ❌ |

This is a portfolio project maintained by a single developer. Only the current production version receives security updates.

---

## Reporting a Vulnerability

If you discover a security vulnerability, **please do not open a public GitHub issue.**

Report it privately via one of:
- **GitHub:** Use [GitHub's private security advisory feature](https://github.com/deeason7/ai-career-hub/security/advisories/new)
- **Email:** Contact the repository owner via the email listed on their GitHub profile

Please include:
- A clear description of the vulnerability
- Steps to reproduce
- Potential impact
- Any suggested remediation (optional)

---

## Response SLA

| Severity | Initial Response | Resolution Target |
|----------|-----------------|-------------------|
| Critical | 48 hours | 7 days |
| High | 72 hours | 14 days |
| Medium/Low | 7 days | Best effort |

---

## Security Design

### Authentication
- JWT access tokens (60-minute expiry)
- Refresh tokens with `jti` UUID claims, blacklisted in Redis on logout
- `bcrypt` password hashing
- Minimum password length: 12 characters; requires at least 1 digit and 1 uppercase letter or symbol
- Password must not match the account email address

### Transport
- HTTPS enforced. HTTP → HTTPS redirect at the Nginx layer.
- HSTS enabled.

### Secrets Management
- All production secrets stored in AWS SSM Parameter Store
- No secrets committed to the repository
- CI/CD authenticates via OIDC (no long-lived AWS keys)

### Security Headers
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=()`
- `X-Permitted-Cross-Domain-Policies: none`
- `Cross-Origin-Resource-Policy: same-origin`
- `Cross-Origin-Opener-Policy: same-origin`
- `Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` (backend JSON API — no browser resources served)
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (production only)

### Rate Limiting
- Redis-backed rate limiting on all authenticated and auth endpoints
- `/auth/register`: 3 requests/minute per IP
- `/auth/login`: 5 requests/minute per IP (OWASP A07)
- `/auth/refresh`: 20 requests/minute per IP
- AI endpoints (`/ai/*`, `/analysis/*`): 20 requests/minute per IP
- `/cover-letters/generate`, `/cover-letters/{id}/refine`: 5 requests/minute per IP
- `/ai/fetch-job`: 10 requests/minute per IP (external scraping throttle)

### SSRF Mitigation
- Job URL import (`POST /ai/fetch-job`) accepts only `http`/`https` URLs via Pydantic's `AnyHttpUrl` field — a first-line scheme check
- Before fetching, the target host is resolved and every resolved IP is rejected if it is private, loopback, link-local (the `169.254.0.0/16` cloud-metadata range, e.g. `169.254.169.254`), multicast, reserved, or unspecified
- Redirects are not auto-followed — each hop is re-validated the same way, so a public URL cannot redirect into an internal address
- IMDSv2 is enforced at the EC2 instance level — even if a request reaches the metadata service, it requires a session token that is not accessible from inside the app containers

### Input Validation
- All user-submitted text sanitized before persistence and before entering any LLM prompt
- Job description inputs are stripped of prompt-injection tokens before LLM calls:
  - Fenced code blocks (` ``` `)
  - Role delimiters: `\nHuman:`, `\nAssistant:`, `\nSystem:`
  - ChatML tokens: `<|im_start|>`, `<|im_end|>`, `</s>`
  - LLaMA 2 / Mixtral instruction wrappers: `[INST]`, `[/INST]`, `<<SYS>>`, `<</SYS>>`
- `sanitize_text()` strips HTML tags, null bytes, and control characters from all user free-text fields before storage
- `AnyHttpUrl` validation on job URL fields enforces the http/https scheme (host/IP SSRF checks live in the fetcher — see SSRF Mitigation)

### Audit Logging (OWASP A09)
- Sensitive actions logged: `auth.register`, `auth.login`, `auth.login.failed`, `resume.upload`, `cover_letter.generate`
- `auth.login.failed` captures IP hash on every failed credential attempt — primary signal for brute-force detection
- Raw IP addresses are **never stored** — only SHA-256 hashes
- No PII (email, name, resume content) in audit metadata
- Audit log stored in `audit_logs` PostgreSQL table

### Dependency Scanning
- `pip-audit` runs on every CI build against `requirements.txt`

### API Security
- `/docs` and `/redoc` disabled in production
- CORS policy scoped to the application domain

---

## Known Limitations

- Streamlit requires `unsafe-inline` in the Content Security Policy. This is a known
  constraint of the Streamlit framework and cannot be removed without replacing the frontend.
- Two `pip-audit` vulnerability ignores are currently in effect (CVE-2026-41481,
  CVE-2026-1839). Both are transitive dependencies where the vulnerable code path
  is not used in this codebase. The rationale and mitigation notes are documented
  inline in `backend/requirements.txt`. Fixes require a major ecosystem upgrade
  currently blocked by a pinned dependency constraint.
- This is a single-developer portfolio project. There is no security team or bug bounty program.
