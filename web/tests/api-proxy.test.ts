import assert from "node:assert/strict";
import test from "node:test";
import { handleApi } from "../lib/api-proxy.ts";

const url = "https://career.example";
const env = {
  VERCEL: "1",
  CAREER_HUB_API_ORIGIN: "https://api.example",
  CAREER_HUB_WEB_ORIGIN: url,
};
const id = "1b1a1a8e-ad3b-41a9-a172-76308d82a3d1";
const access = "access.payload.signature";
const refresh = "refresh.payload.signature";
const unexpected: typeof fetch = async () => assert.fail("The request should not reach the API");

function write(path: string, init: RequestInit = {}) {
  return new Request(url + "/api/" + path, {
    ...init,
    method: init.method ?? "POST",
    headers: { origin: url, ...init.headers },
  });
}

test("login keeps tokens in host-scoped HttpOnly cookies", async () => {
  const response = await handleApi(write("session/login", {
    body: new URLSearchParams({ username: "example@example.test", password: "synthetic" }),
  }), ["session", "login"], env, async (target, outgoing) => {
    assert.equal(target, "https://api.example/api/v1/auth/login");
    assert.equal(outgoing?.method, "POST");
    assert.match(String(outgoing?.body), /username=example%40example.test/);
    return Response.json({ access_token: access }, {
      headers: { "set-cookie": "refresh_token=" + refresh + "; Max-Age=86400; Path=/api/v1/auth; HttpOnly" },
    });
  });
  assert.deepEqual(await response.json(), { ok: true });
  assert.equal(response.headers.get("cache-control"), "private, no-store");
  assert.equal(response.headers.getSetCookie().length, 2);
  assert.match(response.headers.getSetCookie()[0], /Path=\/api;.*HttpOnly; SameSite=Lax; Secure/);
  assert.match(response.headers.getSetCookie()[1], /Path=\/api\/session; Max-Age=86400;.*HttpOnly; SameSite=Lax; Secure/);
});

test("refresh forwards only the intended refresh cookie and preserves it on provider failure", async () => {
  const response = await handleApi(write("session/refresh", {
    headers: { cookie: "careerhub_refresh=" + refresh + "; analytics=hidden" },
  }), ["session", "refresh"], env, async (target, outgoing) => {
    assert.equal(target, "https://api.example/api/v1/auth/refresh");
    assert.equal(new Headers(outgoing?.headers).get("cookie"), "refresh_token=" + refresh);
    return new Response("<html>Starting Space</html>", { status: 503 });
  });
  assert.equal(response.status, 503);
  assert.equal(response.headers.getSetCookie().length, 0);
  assert.equal((await response.json()).error, "api_unavailable");
});

test("refresh clears cookies only for a FastAPI authentication rejection", async () => {
  function run(reply: Response) {
    return handleApi(write("session/refresh", {
      headers: { cookie: "careerhub_refresh=" + refresh },
    }), ["session", "refresh"], env, async () => reply);
  }

  const provider = await run(new Response("<html>Provider auth screen</html>", { status: 401 }));
  assert.equal(provider.status, 503);
  assert.deepEqual(provider.headers.getSetCookie(), []);

  const generic = await run(Response.json({ detail: "Hosting authentication required." }, { status: 401 }));
  assert.equal(generic.status, 503);
  assert.deepEqual(generic.headers.getSetCookie(), []);

  const expired = await run(Response.json({ detail: "Invalid or expired refresh token. Please log in again." }, { status: 401 }));
  assert.equal(expired.status, 401);
  assert.equal(expired.headers.getSetCookie().length, 2);
  assert(expired.headers.getSetCookie().every((cookie) => cookie.includes("Max-Age=0")));
});

test("logout revokes upstream then clears both cookies", async () => {
  const response = await handleApi(write("session/logout", {
    headers: { cookie: "careerhub_access=" + access + "; careerhub_refresh=" + refresh },
  }), ["session", "logout"], env, async (target, outgoing) => {
    const headers = new Headers(outgoing?.headers);
    assert.equal(target, "https://api.example/api/v1/auth/logout");
    assert.equal(headers.get("authorization"), "Bearer " + access);
    assert.equal(headers.get("cookie"), "refresh_token=" + refresh);
    return new Response(null, { status: 204 });
  });
  assert.equal(response.status, 204);
  assert(response.headers.getSetCookie().every((cookie) => cookie.includes("Max-Age=0")));
});

test("tracker updates preserve PATCH and use the server session", async () => {
  const response = await handleApi(write("jobs/" + id, {
    method: "PATCH",
    body: JSON.stringify({ status: "applied" }),
    headers: { "content-type": "application/json", cookie: "careerhub_access=" + access, authorization: "Bearer fake" },
  }), ["jobs", id], env, async (target, outgoing) => {
    assert.equal(target, "https://api.example/api/v1/jobs/" + id);
    assert.equal(outgoing?.method, "PATCH");
    assert.equal(outgoing?.redirect, "error");
    assert.equal(new Headers(outgoing?.headers).get("authorization"), "Bearer " + access);
    return Response.json({ id, status: "applied" });
  });
  assert.equal(response.status, 200);
  assert.equal((await response.json()).status, "applied");
});

test("tracker collection uses the API's canonical slash and forwards known query options only", async () => {
  const request = new Request(url + "/api/jobs?limit=25&ignore=other", { headers: { cookie: "careerhub_access=" + access } });
  const response = await handleApi(request, ["jobs"], env, async (target) => {
    assert.equal(target, "https://api.example/api/v1/jobs/?limit=25");
    return Response.json([]);
  });
  assert.equal(response.status, 200);
});

test("tracker forwards create and delete statuses", async () => {
  const cookie = "careerhub_access=" + access;
  const created = await handleApi(write("jobs", {
    body: JSON.stringify({ company: "Example", role: "Engineer" }),
    headers: { "content-type": "application/json", cookie },
  }), ["jobs"], env, async (target, outgoing) => {
    assert.equal(target, "https://api.example/api/v1/jobs/");
    assert.equal(outgoing?.method, "POST");
    return Response.json({ id }, { status: 201 });
  });
  assert.equal(created.status, 201);
  assert.deepEqual(await created.json(), { id });

  const deleted = await handleApi(write("jobs/" + id, {
    method: "DELETE", headers: { cookie },
  }), ["jobs", id], env, async (target, outgoing) => {
    assert.equal(target, "https://api.example/api/v1/jobs/" + id);
    assert.equal(outgoing?.method, "DELETE");
    return new Response(null, { status: 204 });
  });
  assert.equal(deleted.status, 204);
  assert.equal(await deleted.text(), "");
});

test("foreign-origin writes and unrelated upstream routes are rejected locally", async () => {
  const foreign = await handleApi(write("session/logout", { headers: { origin: "https://other.example" } }), ["session", "logout"], env, unexpected);
  const other = await handleApi(write("admin/lifecycle"), ["admin", "lifecycle"], env, unexpected);
  assert.equal(foreign.status, 403);
  assert.equal(other.status, 404);
});

test("missing production API configuration does not fall back to a live URL", async () => {
  const response = await handleApi(write("session/login"), ["session", "login"], {
    VERCEL: "1", CAREER_HUB_WEB_ORIGIN: url,
  }, unexpected);
  assert.equal(response.status, 503);
});
