import assert from "node:assert/strict";
import test from "node:test";
import { handleApi } from "../lib/api-proxy.ts";
import { createReadinessProbe } from "../lib/readiness.ts";
import { waitForApi } from "../lib/recovery.ts";
import type { RecoveryState } from "../lib/recovery.ts";

const healthy = {
  api: "ok",
  db: { status: "ok" },
  redis: { status: "ok" },
  vector: { status: "ok" },
  semantic: { status: "ok" },
};
const origin = "https://backend.example";

function fakeHealth(warm: Record<string, unknown>, version = "4.4.3"): typeof fetch {
  return async (target, request) => {
    const path = new URL(String(target)).pathname;
    assert.equal(request?.redirect, "error");
    assert.equal(new Headers(request?.headers).has("cookie"), false);
    assert.equal(new Headers(request?.headers).has("authorization"), false);
    if (path === "/health") return Response.json({ status: "ok" });
    if (path === "/health/warm") return Response.json(warm);
    assert.equal(path, "/");
    return Response.json({ version });
  };
}

test("HTML, redirects and timeouts cannot establish process readiness", async () => {
  for (const send of [
    async () => new Response("<html>Starting the Space</html>", { status: 200 }),
    async () => Response.redirect("https://example.net/", 302),
    async () => { throw new DOMException("expired", "TimeoutError"); },
  ]) {
    assert.deepEqual(await createReadinessProbe().check(origin, send), { status: "waking" });
  }
});

test("reachable process reports degraded Redis, PostgreSQL, Qdrant or MiniLM", async () => {
  for (const name of ["db", "redis", "vector", "semantic"]) {
    const send = fakeHealth({ ...healthy, [name]: { status: "down", detail: "private provider data" } });
    assert.deepEqual(await createReadinessProbe().check(origin, send), { status: "degraded" });
  }
  const redisDisabled = fakeHealth({ ...healthy, redis: { status: "disabled" } });
  assert.deepEqual(await createReadinessProbe().check(origin, redisDisabled), { status: "degraded" });
});

test("only the known legacy release can omit semantic readiness", async () => {
  const { semantic: _missing, ...dependencies } = healthy;
  const check = createReadinessProbe();
  assert.deepEqual(await check.check(origin, fakeHealth(dependencies)), {
    status: "ready", semantic: "legacy-unverified",
  });
  assert.deepEqual(await check.check("https://different.example", fakeHealth(dependencies, "4.4.4")), {
    status: "degraded",
  });
});

test("parallel checks share a request and success expires and can be invalidated", async () => {
  let time = 0;
  let calls = 0;
  const check = createReadinessProbe(() => time);
  const send: typeof fetch = (url, request) => {
    calls++;
    return fakeHealth(healthy)(url, request);
  };

  const first = check.check(origin, send);
  assert.equal(first, check.check(origin, send));
  assert.deepEqual(await first, { status: "ready", semantic: "ok" });
  await check.check(origin, send);
  assert.equal(calls, 2);

  check.invalidate(origin);
  await check.check(origin, send);
  assert.equal(calls, 4);
  time = 20_001;
  await check.check(origin, send);
  assert.equal(calls, 6);
});

test("readiness route reports missing configuration without using a fallback API", async () => {
  const request = new Request("https://web.example/api/readiness");
  const result = await handleApi(request, ["readiness"], { VERCEL: "1" }, async () => {
    assert.fail("misconfigured route should not contact an upstream");
  });
  assert.equal(result.status, 503);
  assert.equal(result.headers.get("retry-after"), "5");
  assert.deepEqual(await result.json(), { status: "misconfigured" });
});

test("client waits through cold and degraded states using only readiness reads", async () => {
  const states: RecoveryState[] = [];
  const responses = [
    new Response("<html>Waking up</html>", { status: 503 }),
    Response.json({ status: "degraded" }, { status: 503 }),
    Response.json({ status: "ready", semantic: "ok" }),
  ];
  const result = await waitForApi(new AbortController().signal, (state) => states.push(state), {
    budget: 500, firstDelay: 1,
    send: async (target, request) => {
      assert.equal(target, "/api/readiness");
      assert.equal(request?.method ?? "GET", "GET");
      return responses.shift()!;
    },
  });
  assert.equal(result, true);
  assert.deepEqual(states, ["checking", "waking", "degraded"]);
  assert.equal(responses.length, 0);
});

test("client stops on cancellation, an invalid origin, or expiry", async () => {
  const controller = new AbortController();
  const states: RecoveryState[] = [];
  const result = await waitForApi(controller.signal, (state) => states.push(state), {
    send: async () => { controller.abort(); throw new DOMException("cancelled", "AbortError"); },
  });
  assert.equal(result, false);
  assert.deepEqual(states, ["checking"]);
  states.length = 0;

  const invalid = await waitForApi(new AbortController().signal, (state) => states.push(state), {
    send: async () => Response.json({ status: "misconfigured" }, { status: 503 }),
  });
  assert.equal(invalid, false);
  assert.deepEqual(states, ["checking", "misconfigured"]);
  states.length = 0;

  const expired = await waitForApi(new AbortController().signal, (state) => states.push(state), {
    budget: 20, firstDelay: 1_000,
    send: async () => Response.json({ status: "waking" }, { status: 503 }),
  });
  assert.equal(expired, false);
  assert.deepEqual(states, ["checking", "waking", "timed-out"]);
});
