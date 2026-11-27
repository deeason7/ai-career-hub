import type { ApiReadiness } from "./readiness.ts";

export type RecoveryState = "idle" | "checking" | "waking" | "degraded" | "misconfigured" | "timed-out";

function pause(ms: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const stop = () => {
      clearTimeout(timer);
      signal.removeEventListener("abort", stop);
      resolve();
    };
    const timer = setTimeout(stop, ms);
    signal.addEventListener("abort", stop, { once: true });
  });
}

export async function waitForApi(
  signal: AbortSignal,
  onStatus: (state: RecoveryState) => void,
  {
    send = fetch,
    budget = 90_000,
    firstDelay = 1_500,
  }: { send?: typeof fetch; budget?: number; firstDelay?: number } = {},
) {
  const deadline = AbortSignal.any([signal, AbortSignal.timeout(budget)]);
  let delay = firstDelay;
  onStatus("checking");
  while (!deadline.aborted) {
    let result: ApiReadiness | undefined;
    try {
      const response = await send("/api/readiness", { cache: "no-store", signal: deadline });
      result = await response.json();
      if (deadline.aborted) break;
      if (response.ok && result?.status === "ready") return true;
    } catch {
      if (deadline.aborted) break;
    }
    if (result?.status === "misconfigured") {
      onStatus("misconfigured");
      return false;
    }
    onStatus(result?.status === "degraded" ? "degraded" : "waking");
    await pause(delay + Math.random() * delay * 0.25, deadline);
    delay = Math.min(delay * 2, 8_000);
  }
  if (!signal.aborted) onStatus("timed-out");
  return false;
}
