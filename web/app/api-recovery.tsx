"use client";

import { useEffect, useState } from "react";
import { waitForApi } from "../lib/recovery";
import type { RecoveryState } from "../lib/recovery";

const copy: Record<RecoveryState, string> = {
  idle: "The API is unavailable. You can check its status again.",
  checking: "Checking the Career Hub API…",
  waking: "Waiting for the API to start. This can take a moment.",
  degraded: "The API is responding. Waiting for its services to be ready.",
  misconfigured: "Career Hub cannot reach its configured API. Contact the site owner.",
  "timed-out": "The API took too long to respond. Try again in a minute.",
};

export default function ApiRecovery({
  onReady,
  autoStart = true,
}: { onReady: () => void; autoStart?: boolean }) {
  const [attempt, setAttempt] = useState(autoStart ? 1 : 0);
  const [state, setState] = useState<RecoveryState>(autoStart ? "checking" : "idle");

  useEffect(() => {
    if (attempt === 0) return;
    const controller = new AbortController();
    void waitForApi(controller.signal, setState).then((ready) => {
      if (ready && !controller.signal.aborted) onReady();
    });
    return () => controller.abort();
  }, [attempt, onReady]);

  const active = state === "checking" || state === "waking" || state === "degraded";
  return (
    <div className="recovery">
      <p role="status">{copy[state]}</p>
      {active ? (
        <button type="button" className="secondary" onClick={() => { setAttempt(0); setState("idle"); }}>Stop waiting</button>
      ) : (
        <button type="button" className="secondary" onClick={() => setAttempt((value) => value + 1)}>Check again</button>
      )}
    </div>
  );
}
