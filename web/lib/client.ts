export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

let refreshing: Promise<boolean> | undefined;

async function refreshSession() {
  if (!refreshing) {
    const refresh = async () => {
      // A different tab can finish refreshing while this tab waits for the lock.
      const session = await send("session/me");
      if (session.ok) return true;
      if (session.status !== 401) throw await toError(session);
      const response = await send("session/refresh", { method: "POST" });
      if (response.status === 401) return false;
      if (!response.ok) throw await toError(response);
      return true;
    };
    refreshing = (
      typeof navigator !== "undefined" && navigator.locks
        ? navigator.locks.request("careerhub-session-refresh", refresh)
        : refresh()
    ).finally(() => { refreshing = undefined; });
  }
  return refreshing;
}

async function toError(response: Response): Promise<ApiError> {
  const payload = await response.json().catch(() => undefined);
  return new ApiError(response.status, payload?.message ?? "Career Hub is temporarily unavailable.");
}

async function send(path: string, init?: RequestInit) {
  try {
    return await fetch("/api/" + path, { ...init, cache: "no-store" });
  } catch {
    throw new ApiError(503, "The connection was interrupted. Check your connection and try again.");
  }
}

export async function api<T>(path: string, init?: RequestInit, allowRefresh = true): Promise<T> {
  let response = await send(path, init);
  if (response.status === 401 && allowRefresh && await refreshSession()) {
    response = await send(path, init);
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return undefined as T;
  return response.json();
}
