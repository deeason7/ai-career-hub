# Keepalive diagnosis and verification

[Deployment guide](../DEPLOYMENT.md) · [Workflow](../.github/workflows/keepwarm.yml) · [Checker](../.github/scripts/readiness.py)

## Diagnosis, 2026-11-15

Career Hub had multiple failure classes. A healthy hosting edge did not establish
a healthy application, and a failed scheduled run did not identify a single recurring
application defect. The scheduled workflow still used default-branch commit
`695a753`; the stronger checker existed only on the housekeeping branch.

| Evidence | What it establishes |
|---|---|
| [Successful November 15 run](https://github.com/deeason7/ai-career-hub/actions/runs/43720641697) | API, Neon, Upstash and Qdrant reported healthy. Frontend HTTP 303 passed the old `<500` check; frontend runtime was unverified. |
| October 26 recovery | Streamlit viewer status was 12 (asleep) while the outer page returned 200 and scheduled checks remained green. Normal provider wake restored status 5 and runtime `200 ok`. Repository inactivity was not the cause. |
| [Failed September 29 run](https://github.com/deeason7/ai-career-hub/actions/runs/36525306460) | First two samples contained Hugging Face's 500 error page; the third was actual API JSON with Redis down/ConnectionError and healthy DB/vector. The API failure also skipped frontend probing. |
| [Failed July 25 run](https://github.com/deeason7/ai-career-hub/actions/runs/30136396348) | Provider error pages and cleanup HTTP 500. A provider control plane reporting RUNNING did not establish serving readiness. |
| July cleanup defect, fixed in `aa1e4b5` | Expired parent documents caused non-null child FK errors during deletion. PostgreSQL reproduction and cascade regressions belong to that earlier application fix. |

The old cookie-less redirect-following check exhausted redirects. Stopping redirect
following removed that false alarm but introduced false greens by accepting 3xx/4xx.
The duplicate Cloudflare worker also returned healthy for API `{}` plus frontend 303;
that false green was reproduced directly with its JavaScript implementation.

Career Hub has no WebSocket keepalive probe. HTTP 101 is a protocol upgrade, not
success for these HTTP health endpoints. Curl's process exit code and HTTP response
code are separate signals; neither should be appended to the other. The corrected
checker uses structured HTTP responses and typed transport errors instead of shell
status parsing. Unexpected upgrades fail. See [curl's status and exit documentation](https://curl.se/docs/manpage.html).

The failed September run used Ubuntu 24.04; the sampled successful November run used
Ubuntu 26.04. There is no evidence that a runner transition caused Career Hub's
failure. The runner label is now pinned to Ubuntu 24.04 to avoid unplanned major OS
changes, and the workflow records Python/OpenSSL versions. Image patch updates still occur.

## Health contract

- API HTTP status must be 200 and its JSON must report `api=ok`, DB/vector `ok`,
  and Redis `ok` or explicitly `disabled`. Missing signals fail.
- Semantic inference must be `ok`. Only scheduled warming can permit an absent
  signal from independently confirmed v4.4.3, with an explicit warning. Newer releases
  cannot use that exception. Deployment and live-smoke validation remain strict.
- Community Cloud must report viewer status 5 and runtime HTTP `200 ok` at
  `/~/+/_stcore/health`. Cookie-aware bounded redirects preserve provider sessions.
  Local Streamlit uses `/_stcore/health`.
- Every required surface is checked even when another fails. Failed services retry
  up to three times, 30 seconds apart. Healthy services are retained. Workflow steps
  impose total execution limits in addition to request timeouts.
- Oversized, incomplete, malformed and unexpected responses fail. Logs contain safe
  status/error labels, never raw provider bodies, redirect URLs or cookies.

The [duplicate worker was retired](../infra/keep-warm/README.md), leaving one readiness
implementation shared by scheduled checks and release validation. Its historical
configuration does not establish whether a remote worker exists; any deployed copy
would require a separate authorized retirement.

## Reproduce and verify

From the repository root:

```bash
make test-probes
make docs-check
python3 .github/scripts/readiness.py \
  --api-base https://deeason-careerhub.hf.space \
  --frontend-url https://deeason-career.streamlit.app \
  --allow-missing-semantic
```

The regression suite covers success, every dependency failure, legacy compatibility,
asleep/error wrappers, cookie redirects, loops, HTTP 401/403/404/429/5xx, unexpected 101,
timeouts, disconnections, truncated/oversized bodies, bounded retries and redaction.
HTTP-byte tests run without listeners; loopback-server tests exercise actual sockets.
`CAREERHUB_REQUIRE_NETWORK_TESTS=1` makes inability to bind those sockets a failure
in the workflow. Restricted local environments report that suite as unavailable.

Use a manual **Keep Warm** dispatch against the reviewed branch to run the exact
workflow without cleanup. Do not select `run-cleanup` for read-only verification.
Inspect the API dependency labels and frontend result separately. Daily cleanup keeps
its existing UTC schedule; explicit cleanup uses `free-prod` and a single authenticated
POST, rejects redirects and validates returned counts without printing response bodies.

Scheduled runs execute the default branch. Publishing a feature branch or passing a
manual run does not activate its schedule. Activation requires the normal authorized
review/merge path; application deployment and release gates remain separate.

Readiness checks do not prove browser login, generation/QA, vector retrieval quality,
complete document deletion, or continuous uptime. Sleeping/suspended providers may
require account-console or viewer recovery. Missing v4.4.3 semantic telemetry remains
an explicitly reported limitation until the corresponding backend is deployed.
