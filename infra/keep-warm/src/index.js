// Keep-warm + daily maintenance for the AI Career Hub free-tier stack.
//
// Free-tier providers (Neon, Qdrant, HF Spaces, Streamlit) suspend when idle,
// so a scheduled ping keeps them resident and the first real visitor avoids a
// cold start. Two cron triggers are declared in wrangler.toml — a 6-hour warm
// and a daily lifecycle cleanup. The same worker doubles as the app's cron.

const CLEANUP_CRON = "0 3 * * *";
const TIMEOUT_MS = 20000;

export default {
  async scheduled(event, env, ctx) {
    const job = event.cron === CLEANUP_CRON ? runCleanup(env) : runWarm(env);
    ctx.waitUntil(job);
  },

  // Manual on-demand warm (handy for testing, or as a secondary UptimeRobot hit).
  // Cleanup is intentionally NOT reachable here — it only runs on the cron, which
  // is the only place the admin secret is used.
  async fetch(_request, env) {
    return Response.json(await runWarm(env));
  },
};

async function runWarm(env) {
  const problems = [];

  // One cheap call warms Postgres, Redis and the vector store at once.
  try {
    const res = await fetchWithTimeout(`${env.API_BASE}/health/warm`);
    if (!res.ok) {
      problems.push(`/health/warm returned HTTP ${res.status}`);
    } else {
      const body = await res.json();
      const deps = { db: body.db, redis: body.redis, vector: body.vector?.status };
      for (const [name, state] of Object.entries(deps)) {
        // "disabled" = that dependency isn't configured on this deploy, not a fault.
        if (state && state !== "ok" && state !== "disabled") {
          problems.push(`${name} is "${state}"`);
        }
      }
    }
  } catch (err) {
    problems.push(`/health/warm unreachable: ${err.message}`);
  }

  // Keep the Streamlit frontend resident. Any response means the edge took the
  // hit; only a 5xx or a network error is worth an alert (a 3xx/4xx still
  // counts as traffic). redirect: "manual" — Streamlit's edge sends cookie-less
  // clients in a redirect loop, so following would throw and false-alarm.
  try {
    const res = await fetchWithTimeout(env.FRONTEND_URL, { method: "HEAD", redirect: "manual" });
    if (res.status >= 500) problems.push(`frontend returned HTTP ${res.status}`);
  } catch (err) {
    problems.push(`frontend unreachable: ${err.message}`);
  }

  if (problems.length) await alert(env, `keep-warm:\n- ${problems.join("\n- ")}`);
  return { ok: problems.length === 0, problems, ts: Date.now() };
}

async function runCleanup(env) {
  try {
    const res = await fetchWithTimeout(`${env.API_BASE}/api/v1/admin/lifecycle/run`, {
      method: "POST",
      headers: { "X-Admin-Secret": env.ADMIN_SECRET },
    });
    if (!res.ok) {
      await alert(env, `lifecycle cleanup failed: HTTP ${res.status}`);
      return { ok: false, status: res.status };
    }
    return { ok: true };
  } catch (err) {
    await alert(env, `lifecycle cleanup unreachable: ${err.message}`);
    return { ok: false, error: err.message };
  }
}

async function alert(env, message) {
  if (!env.ALERT_WEBHOOK) return; // alerting is optional — omit the secret to disable
  try {
    await fetchWithTimeout(env.ALERT_WEBHOOK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      // Discord-shaped payload; adjust `content` if you point ALERT_WEBHOOK elsewhere.
      body: JSON.stringify({ content: `⚠️ AI Career Hub — ${message}` }),
    });
  } catch {
    // A failed alert must never throw out of the scheduled handler.
  }
}

async function fetchWithTimeout(url, options = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}
