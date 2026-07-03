# Keep-warm worker (Cloudflare)

Laptop-free scheduler for the free-tier stack. One deep-warm call keeps
Neon + Upstash + Qdrant resident; the frontend is probed too; and the daily
document-lifecycle cleanup runs from the same worker. Alerts fire only when a
dependency reports `down` or a service is unreachable.

Free tier: 100k requests/day, no repo-activity expiry (unlike a GitHub Action),
independent of your laptop.

## What it does

| Cron (UTC) | Action |
|---|---|
| `0 */6 * * *` | `GET {API_BASE}/health/warm` (warms DB + Redis + vector) + `HEAD {FRONTEND_URL}`; alert on any `down`/5xx/unreachable |
| `0 3 * * *` | `POST {API_BASE}/api/v1/admin/lifecycle/run` with `X-Admin-Secret` (15-day TTL cleanup) |

Groq is never pinged (no idle pause; saves tokens).

## Deploy

```bash
# from this folder
npm install -g wrangler          # or use: npx wrangler ...
wrangler login

# 1. Edit wrangler.toml → set API_BASE (HF Space) and FRONTEND_URL (Streamlit app).
# 2. Set the secrets:
wrangler secret put ADMIN_SECRET   # paste the SAME value as the backend's ADMIN_SECRET
wrangler secret put ALERT_WEBHOOK  # optional: a Discord webhook URL (skip to disable alerts)

# 3. Ship it
wrangler deploy
```

## Test without waiting for the cron

```bash
# local dry-run of the scheduled handler
wrangler dev --test-scheduled
# then in another shell, fire each trigger:
curl "http://localhost:8787/__scheduled?cron=0+*/6+*+*+*"   # warm
curl "http://localhost:8787/__scheduled?cron=0+3+*+*+*"     # cleanup

# once deployed, an on-demand warm is just a GET to the worker URL:
curl https://careerhub-keepwarm.<your-subdomain>.workers.dev
```

## Notes

- Add **UptimeRobot** (free, 5-min HTTP checks on the Space + Streamlit URLs) as a
  redundant second scheduler — it also gives you an uptime dashboard.
- A free Qdrant cluster that gets force-suspended can't be *un-paused* by a ping;
  the alert tells you within minutes so you can resume it with one console click.
- Times are UTC. Shift the crons if you want the cleanup at a specific local hour.
