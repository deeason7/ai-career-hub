# Keep-warm worker — optional Cloudflare scheduler

[Deployment and recovery](../../DEPLOYMENT.md) · [Worker source](src/index.js) · [Schedule and URLs](wrangler.toml)

This worker can schedule API warming and daily document cleanup independently of
GitHub Actions. The project's default scheduler is
[keepwarm.yml](../../.github/workflows/keepwarm.yml); no Cloudflare deployment was
verified in the current checkpoint.

## What the current worker checks

| Trigger, UTC | Behavior |
|---|---|
| `0 */6 * * *` | Fetch `/health/warm`; check returned DB, Redis and vector states; send a `HEAD` request to the frontend |
| `0 3 * * *` | Call `/api/v1/admin/lifecycle/run` using `X-Admin-Secret` |
| HTTP request to the worker | Run the warm check and return its JSON result; never trigger cleanup |

Requests have a 20-second timeout. `ALERT_WEBHOOK`, when set, receives a
Discord-shaped message for detected problems. API dependencies reporting `ok` or
`disabled` are accepted; missing dependency fields are ignored. Frontend 5xx and
network failures are reported, while 3xx/4xx are accepted. Inspect the worker's
`ok` and `problems` JSON fields; the HTTP handler itself can return 200 on failure.

**This is a weaker probe than the current Python readiness checker.** It does not
inspect the semantic inference field or Streamlit's running state and runtime health.
A sleeping frontend's outer page can therefore pass. Before adopting this worker as
a replacement, bring its checks into parity with
[readiness.py](../../.github/scripts/readiness.py) and verify both healthy and failed
responses. Scheduled traffic does not guarantee uptime or recover a suspended account.

The worker does not call a generation endpoint, so it does not intentionally consume
LLM generation tokens. The warm API may perform local embedding inference. Daily
cleanup currently removes eligible SQL rows; it does not complete vector deletion.

## Configure an optional deployment

Use Wrangler with access to your Cloudflare account. From this directory:

```bash
npx wrangler login
```

1. Set `API_BASE` and `FRONTEND_URL` in `wrangler.toml` for the intended deployment.
2. Review the two UTC schedules and the probe limitations above.
3. Store secrets, then deploy when that environment is ready:

```bash
npx wrangler secret put ADMIN_SECRET
npx wrangler secret put ALERT_WEBHOOK  # optional; omit to disable alerts
npx wrangler deploy
```

`ADMIN_SECRET` must match the backend value. Avoid running duplicate cleanup
schedulers accidentally. Provider plans, quotas and suspension policies should be
checked in the provider account when provisioning; this guide makes no free-tier or
alert-delivery-time guarantee.

## Exercise each trigger

```bash
npx wrangler dev --test-scheduled
```

In another terminal:

```bash
curl 'http://localhost:8787/__scheduled?cron=0+*/6+*+*+*'
curl 'http://localhost:8787/__scheduled?cron=0+3+*+*+*'
```

**These execute the handler and can call the configured services.** Point the local
worker at an isolated API and use test secrets before exercising cleanup; local
Wrangler execution is not a no-op dry run. Check runtime logs, the warm JSON result,
the cleanup response, and alert delivery separately.

Once deliberately deployed, requesting its worker URL performs a warm check:

```bash
curl 'https://careerhub-keepwarm.<your-subdomain>.workers.dev'
```
