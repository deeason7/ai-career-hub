type Environment = Readonly<Record<string, string | undefined>>;

const ACCESS_COOKIE = "careerhub_access";
const REFRESH_COOKIE = "careerhub_refresh";
const REQUEST_TIMEOUT_MS = 12_000;
const UUID = /^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$/i;
const JWT = /^[\w-]+\.[\w-]+\.[\w-]+$/;

type Route = {
  upstream: string;
  method: string;
  kind?: "login" | "refresh" | "logout";
  bodyType?: string;
  query?: string;
};

function matchRoute(request: Request, path: string[]): Route | undefined {
  const method = request.method;
  if (path.length === 2 && path[0] === "session") {
    if (path[1] === "me" && method === "GET") return { upstream: "/auth/me", method };
    if (method !== "POST") return;
    if (path[1] === "login") {
      return { upstream: "/auth/login", method, kind: "login", bodyType: "application/x-www-form-urlencoded" };
    }
    if (path[1] === "refresh" || path[1] === "logout") {
      return { upstream: "/auth/" + path[1], method, kind: path[1] };
    }
  }

  if (path[0] !== "jobs") return;
  if (path.length === 1 && method === "GET") {
    const incoming = new URL(request.url).searchParams;
    const query = new URLSearchParams();
    for (const key of ["skip", "limit", "status_filter"]) {
      const value = incoming.get(key);
      if (value !== null) query.set(key, value);
    }
    return { upstream: "/jobs/", method, query: query.size ? "?" + query : "" };
  }
  if (path.length === 1 && method === "POST") {
    return { upstream: "/jobs/", method, bodyType: "application/json" };
  }
  if (path.length === 2 && UUID.test(path[1]) && (method === "PATCH" || method === "DELETE")) {
    return {
      upstream: "/jobs/" + path[1],
      method,
      bodyType: method === "PATCH" ? "application/json" : undefined,
    };
  }
}

function apiOrigin(value: string | undefined, hosted: boolean): string | undefined {
  if (!value) return;
  try {
    const url = new URL(value);
    const loopback = ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname);
    const supported = url.protocol === "https:" || (!hosted && loopback && url.protocol === "http:");
    if (supported && url.pathname === "/" && !url.search && !url.hash && !url.username && !url.password) {
      return url.origin;
    }
  } catch {
    return;
  }
}

function webOrigin(request: Request, env: Environment) {
  if (env.CAREER_HUB_WEB_ORIGIN) return apiOrigin(env.CAREER_HUB_WEB_ORIGIN, Boolean(env.VERCEL));
  if (env.VERCEL && env.VERCEL_URL) return apiOrigin("https://" + env.VERCEL_URL, true);
  if (!env.VERCEL) return new URL(request.url).origin;
}

function readCookie(request: Request, name: string): string | undefined {
  const pairs = request.headers.get("cookie")?.split(";") ?? [];
  const token = pairs.map((pair) => pair.trim()).find((pair) => pair.startsWith(name + "="))?.slice(name.length + 1);
  return token && JWT.test(token) ? token : undefined;
}

function sessionCookie(name: string, value: string, maxAge: number, secure: boolean) {
  const path = name === REFRESH_COOKIE ? "/api/session" : "/api";
  return name + "=" + value + "; Path=" + path + "; Max-Age=" + maxAge
    + "; HttpOnly; SameSite=Lax" + (secure ? "; Secure" : "");
}

function accessLifetime(token: string): number {
  try {
    const data = JSON.parse(Buffer.from(token.split(".")[1], "base64url").toString());
    const lifetime = data.exp - Math.floor(Date.now() / 1000);
    if (Number.isFinite(lifetime)) return Math.max(0, Math.min(Math.floor(lifetime), 86_400));
  } catch {
    // FastAPI authenticates every use of this token. The local value only caps cookie age.
  }
  return 3600;
}

function issuedRefresh(headers: Headers) {
  const header = headers.getSetCookie().find((value) => value.startsWith("refresh_token="));
  const [, token] = /^refresh_token=([\w.-]+)(?:;|$)/.exec(header ?? "") ?? [];
  if (!token || !JWT.test(token)) return;
  const maxAge = Number(/(?:^|;\s*)Max-Age=(\d+)(?:;|$)/i.exec(header ?? "")?.[1]);
  return { token, maxAge: Number.isFinite(maxAge) ? Math.min(maxAge, 604_800) : 604_800 };
}

function fail(headers: Headers, status: number, error: string, message: string) {
  return Response.json({ error, message }, { status, headers });
}

function upstreamFailure(upstream: Response, headers: Headers) {
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter && /^\d{1,4}$/.test(retryAfter)) headers.set("retry-after", retryAfter);
  const messages: Record<number, [string, string]> = {
    400: ["invalid_request", "Check the information you entered."],
    401: ["unauthorized", "Sign in to continue."],
    403: ["forbidden", "This account cannot perform that action."],
    404: ["not_found", "This application could not be found."],
    409: ["conflict", "This change conflicts with an existing record."],
    422: ["invalid_request", "Check the information you entered."],
    429: ["rate_limited", "Too many requests. Wait a moment and try again."],
  };
  const message = messages[upstream.status];
  if (message) return fail(headers, upstream.status, message[0], message[1]);
  return fail(headers, 503, "api_unavailable", "The Career Hub API is temporarily unavailable. Try again shortly.");
}

export async function handleApi(
  request: Request,
  path: string[],
  env: Environment = process.env,
  send: typeof fetch = fetch,
): Promise<Response> {
  const headers = new Headers({
    "cache-control": "private, no-store",
    "x-request-id": crypto.randomUUID(),
  });
  const route = matchRoute(request, path);
  if (!route) return fail(headers, 404, "not_found", "This endpoint could not be found.");

  const origin = webOrigin(request, env);
  if (route.method !== "GET" && (!origin || request.headers.get("origin") !== origin)) {
    return fail(headers, 403, "invalid_origin", "This action must be made from the Career Hub website.");
  }

  const access = readCookie(request, ACCESS_COOKIE);
  const refresh = readCookie(request, REFRESH_COOKIE);
  const secure = Boolean(env.VERCEL) || Boolean(origin?.startsWith("https:"));
  if (route.kind !== "login" && route.kind !== "logout" && (route.kind === "refresh" ? !refresh : !access)) {
    return fail(headers, 401, "unauthorized", "Sign in to continue.");
  }

  if (route.kind === "logout" && !access && !refresh) {
    clearSession(headers, secure);
    return new Response(null, { status: 204, headers });
  }

  const upstreamOrigin = apiOrigin(env.CAREER_HUB_API_ORIGIN, Boolean(env.VERCEL));
  if (!upstreamOrigin) {
    return fail(headers, 503, "api_unavailable", "The Career Hub API is unavailable.");
  }

  const outgoing = new Headers({ accept: "application/json", "x-request-id": headers.get("x-request-id")! });
  if (access && route.kind !== "login" && route.kind !== "refresh") outgoing.set("authorization", "Bearer " + access);
  if (refresh && (route.kind === "refresh" || route.kind === "logout")) outgoing.set("cookie", "refresh_token=" + refresh);

  let body: string | undefined;
  if (route.bodyType) {
    const contentType = request.headers.get("content-type")?.split(";")[0].trim().toLowerCase();
    if (contentType !== route.bodyType) return fail(headers, 415, "invalid_request", "This request has an unsupported format.");
    outgoing.set("content-type", route.bodyType);
    body = await request.text();
  }

  try {
    const upstream = await send(upstreamOrigin + "/api/v1" + route.upstream + (route.query ?? ""), {
      method: route.method,
      headers: outgoing,
      body,
      redirect: "error",
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
    if (route.kind === "refresh" && upstream.status === 401) clearSession(headers, secure);
    if (!upstream.ok) return upstreamFailure(upstream, headers);

    if (route.kind === "logout") {
      clearSession(headers, secure);
      return new Response(null, { status: 204, headers });
    }
    if (upstream.status === 204) return new Response(null, { status: 204, headers });

    const payload = await upstream.json();
    if (route.kind === "login" || route.kind === "refresh") {
      const token = payload?.access_token;
      const nextRefresh = issuedRefresh(upstream.headers);
      if (typeof token !== "string" || !JWT.test(token) || !nextRefresh) {
        return fail(headers, 502, "invalid_session", "The API could not establish a session.");
      }
      headers.append("set-cookie", sessionCookie(ACCESS_COOKIE, token, accessLifetime(token), secure));
      headers.append("set-cookie", sessionCookie(REFRESH_COOKIE, nextRefresh.token, nextRefresh.maxAge, secure));
      return Response.json({ ok: true }, { headers });
    }
    return Response.json(payload, { status: upstream.status, headers });
  } catch {
    return fail(headers, 503, "api_unavailable", "The Career Hub API is temporarily unavailable. Try again shortly.");
  }
}

function clearSession(headers: Headers, secure: boolean) {
  headers.append("set-cookie", sessionCookie(ACCESS_COOKIE, "", 0, secure));
  headers.append("set-cookie", sessionCookie(REFRESH_COOKIE, "", 0, secure));
}
