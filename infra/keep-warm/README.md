# Keep-warm monitoring

[Deployment and recovery](../../DEPLOYMENT.md) · [Workflow](../../.github/workflows/keepwarm.yml) · [Readiness checker](../../.github/scripts/readiness.py)

The optional Cloudflare worker source and Wrangler configuration were retired on
2026-11-15. They duplicated the readiness checker with weaker checks: missing API
dependencies and frontend redirects could pass, and a sleeping Streamlit app was
never distinguished from a running application.

Keep Warm now has one maintained probe implementation,
[readiness.py](../../.github/scripts/readiness.py), shared with deployment checks.
[keepwarm.yml](../../.github/workflows/keepwarm.yml) schedules warming and the separate
daily document cleanup. Its schedule runs from the repository's default branch;
changes on another branch take effect only after the approved merge.

An independent scheduler can execute the same Python checker from a reviewed
checkout. Reuse that implementation and its exit status instead of copying its
HTTP or dependency rules. Keep authenticated cleanup separate and avoid enabling
two cleanup schedules.

Retiring local source does not inspect or remove a deployed Cloudflare worker.
No Cloudflare deployment status was verified during this change. If one was
previously deployed, inspect its triggers and retire or migrate it through the
usual authorized account workflow. Scheduled traffic cannot guarantee uptime or
recover a suspended provider account.
