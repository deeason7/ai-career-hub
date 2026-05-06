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

### Input Validation
- All user-submitted text sanitized before persistence and LLM prompt injection
- `AnyHttpUrl` validation on job URL fields (blocks SSRF vectors)

### API Security
- `/docs` and `/redoc` disabled in production
- CORS policy scoped to the application domain

---

## Known Limitations

- Streamlit requires `unsafe-inline` in the Content Security Policy. This is a known constraint of the Streamlit framework and cannot be removed without replacing the frontend.
- This is a single-developer portfolio project. There is no security team or bug bounty program.
