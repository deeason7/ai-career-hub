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

## Verified corrected workflow

Two manual runs used the identical fix commit `e20d0c7` on
`chore/housekeeping-checkpoint`, with `run-cleanup=false`. They ran November 16 UTC
(November 15 in America/Chicago):

| Run | Observed result |
|---|---|
| [43783949619](https://github.com/deeason7/ai-career-hub/actions/runs/43783949619) | 67 tests passed. API/DB/Redis/Qdrant passed. Frontend correctly failed after three viewer responses reporting asleep, although HTTP was 200. |
| Normal viewer recovery | Same-site session plus CSRF-protected resume returned 204. Viewer then reported status 5 and runtime health returned `200 ok`. No application release or document cleanup occurred. |
| [43784385225](https://github.com/deeason7/ai-career-hub/actions/runs/43784385225) | 67 tests passed without skips. Live API, Neon, Upstash, Qdrant and frontend runtime passed on the first attempt. Cleanup was skipped. Semantic readiness was explicitly unverified on v4.4.3. |

The successful runner used Ubuntu 24.04 image `20261111.370.1`, Python 3.11.18 and
OpenSSL 3.0.13. Local Python 3.11.16 passed 55 tests; its separate 12-method socket
suite was unavailable under local sandbox binding restrictions and passed on the
runner. Lint/format, documentation links and five release markers passed. Application
runtime code and dependencies were unchanged; no database/Docker suite was repeated.

The checker intentionally reports a sleeping app as unavailable; it does not promise
to prevent Community Cloud sleep or automatically invoke provider recovery controls.
The ordinary viewer wake restored this sample. Both scheduled activation and any
long-term hosting/availability change require the normal authorized review path.

Readiness checks do not prove browser login, generation/QA, vector retrieval quality,
complete document deletion, or continuous uptime. Sleeping/suspended providers may
require account-console or viewer recovery. Missing v4.4.3 semantic telemetry remains
an explicitly reported limitation until the corresponding backend is deployed.
