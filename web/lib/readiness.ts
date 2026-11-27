export type ApiReadiness =
  | { status: "ready"; semantic: "ok" | "legacy-unverified" }
  | { status: "waking" | "degraded" | "misconfigured" };

const TIMEOUT_MS = 5_000;
const READY_CACHE_MS = 20_000;

function record(value: unknown): Record<string, unknown> | undefined {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : undefined;
}

function signalStatus(value: unknown) {
  return record(value)?.status ?? value;
}

export function isJson(response: Response) {
  return response.headers.get("content-type")?.split(";")[0].trim().toLowerCase() === "application/json";
}

async function inspectApi(origin: string, send: typeof fetch): Promise<ApiReadiness> {
  const signal = AbortSignal.timeout(TIMEOUT_MS);
  const read = async (path: string) => {
    const response = await send(origin + path, {
      cache: "no-store",
      redirect: "error",
      headers: { accept: "application/json" },
      signal,
    });
    if (!response.ok || !isJson(response)) return undefined;
    return record(await response.json().catch(() => undefined));
  };

  try {
    const health = await read("/health");
    if (health?.status !== "ok") return { status: "waking" };
  } catch {
    return { status: "waking" };
  }

  try {
    const warm = await read("/health/warm");
    if (warm?.api !== "ok" || ["db", "redis", "vector"].some((key) => signalStatus(warm[key]) !== "ok")) {
      return { status: "degraded" };
    }
    if (signalStatus(warm.semantic) === "ok") return { status: "ready", semantic: "ok" };
    if (!("semantic" in warm) && (await read("/"))?.version === "4.4.3") {
      return { status: "ready", semantic: "legacy-unverified" };
    }
  } catch {
    // A process answered the liveness probe, but its dependency check did not complete.
  }
  return { status: "degraded" };
}

export function createReadinessProbe(now = Date.now) {
  let recent: { origin: string; status: ApiReadiness; expires: number } | undefined;
  let pending: { origin: string; check: Promise<ApiReadiness> } | undefined;

  return {
    check(origin: string, send: typeof fetch) {
      if (recent?.origin === origin && recent.expires > now()) return Promise.resolve(recent.status);
      if (pending?.origin === origin) return pending.check;

      const check = inspectApi(origin, send).then((status) => {
        if (pending?.check === check) {
          pending = undefined;
          if (status.status === "ready") recent = { origin, status, expires: now() + READY_CACHE_MS };
        }
        return status;
      });
      pending = { origin, check };
      return check;
    },
    invalidate(origin: string) {
      if (recent?.origin === origin) recent = undefined;
      if (pending?.origin === origin) pending = undefined;
    },
  };
}
