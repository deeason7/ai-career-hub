# Hugging Face API recovery

The FastAPI deployment runs at `https://deeason-careerhub.hf.space`. The public Streamlit app and the Vercel frontend use the same backend. Recover the API first when both clients fail.

## Check the failure

1. Open the **Keep Warm** run and read the **API and datastores**, **Streamlit runtime**, and **Lifecycle cleanup** jobs separately. API checks report dependency flags, API version, elapsed time, sanitized HTTP status, and failure class. The current 4.4.3 build omits semantic readiness. The explicit compatibility mode records that as unverified for this version. A present failing MiniLM signal fails the gate.
2. Run the read-only check from the repo root if necessary. It may send more than one GET while the API is starting.

   ```sh
   python3 .github/scripts/readiness.py \
     --api-base https://deeason-careerhub.hf.space \
     --require-redis --report-version --allow-missing-semantic \
     --request-timeout 15 --retry-delay 15
   ```

3. Check the Space's runtime state and its deployment logs when the API cannot be reached. When the process responds but a dependency is degraded, use the dependency table below. Streamlit is a frontend fallback when its runtime and the shared API are healthy. [Hugging Face Space](https://huggingface.co/spaces/Deeason/careerhub) · [Keep Warm runs](https://github.com/deeason7/ai-career-hub/actions/workflows/keepwarm.yml)

| Symptom | Recovery |
| --- | --- |
| Space is sleeping | Open the public Space or send a normal request to the API. Allow the process to start, then repeat the API readiness check. Record time from the first cold request to ready. |
| Space is paused | Confirm that the pause was unintended. An owner can resume it in the hosting console. Verify the serving release and dependencies after it starts. |
| Space is building or stuck | Check build/runtime logs and allow a normal build to finish. If a rollout broke serving, use the last known-good reviewed backend revision through the deployment workflow. If an otherwise healthy build is stuck, an owner can restart it once and then recheck. |
| PostgreSQL or Redis is degraded | Check the provider's connectivity and quota indicators. Let the service recover before attempting data writes or session refresh. Verify all configured dependencies once available. |
| Qdrant or the semantic model is degraded | Check Qdrant availability and the released model's offline inference checks. Verify scoring with synthetic data after recovery. |
| AI generation alone is degraded | Check Groq status, usage or throttling. API and datastore readiness can pass during an LLM outage. Check for an existing task before submitting a second request. |
| Streamlit runtime is asleep | Verify the API separately. Use the Streamlit wake control and confirm a running viewer state and a healthy runtime response. |

## Cleanup and verification

Scheduled document cleanup runs separately at 03:00 UTC. Manual dispatch is read-only by default. Only an intentional run on `main` with `run-cleanup` enabled can issue the authenticated production cleanup request. The script reports the status, numeric counts or a safe failure class and sends a single POST. If it times out, check the backend's cleanup logs before starting another run.

During the first week after rollout, record cold-start recovery time and any failed auth or duplicate submissions using synthetic accounts. Verify the schedule is still active. Use the next natural sleep to measure recovery without pausing the live Space for a test. Keep the API configured on the Vercel preview isolated from production data during write tests. [Hugging Face lifecycle](https://huggingface.co/docs/hub/spaces-overview#lifecycle-management) · [GitHub schedules](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)
