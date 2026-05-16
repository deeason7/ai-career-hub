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

### Transport
- HTTPS enforced. HTTP → HTTPS redirect at the Nginx layer.
- HSTS enabled.

### Secrets Management
- All production secrets stored in AWS SSM Parameter Store
- No secrets committed to the repository
- CI/CD authenticates via OIDC (no long-lived AWS keys)

### Rate Limiting
- Redis-backed rate limiting on all authenticated and auth endpoints
- `/auth/login`: 5 requests/minute per IP (OWASP A07)
- `/auth/register`: 3 requests/minute per IP

### Input Validation
- All user-submitted text sanitized before persistence and LLM prompt injection
- `_sanitize_jd_for_prompt()` strips prompt-injection tokens (fenced code blocks,
  role delimiters: `\nHuman:`, `\nAssistant:`, `\nSystem:`, `</s>`, `<|im_start|>`)
  from job description text before it enters any LLM call (OWASP A03)
- `sanitize_text()` strips HTML tags, null bytes, and control characters from all
  user free-text fields before storage
- `AnyHttpUrl` validation on job URL fields (blocks SSRF vectors)

### Audit Logging (OWASP A09)
- Sensitive actions logged: `auth.login`, `resume.upload`, `cover_letter.generate`
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

- Streamlit requires `unsafe-inline` in the Content Security Policy. This is a known constraint of the Streamlit framework and cannot be removed without replacing the frontend.
- This is a single-developer portfolio project. There is no security team or bug bounty program.
