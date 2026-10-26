# Project status and evidence

Reviewed 2026-10-26. Last released version: **v4.4.3** (2026-08-22).

AI Career Hub helps job seekers turn an existing resume and job posting into a
reviewable application package: match feedback, a grounded cover-letter draft,
skill recommendations, interview questions and an application record. Its business
value is reducing repeated preparation work while making generated claims easier
to review. Time saved and hiring outcomes have not yet been measured.

## Current delivery stage

The core product, Streamlit redesign, managed-provider deployment and ATS evaluation
harness have shipped. This is a maintenance and reliability stage, followed by
completion of the evaluation work; the old frontend phases are complete.

| Area | Recorded state | Remaining proof |
|---|---|---|
| Hosted API | v4.4.3; API and managed-data probes responded; registration, login and resume parsing succeeded on 2026-10-26 | Complete the browser user journey |
| Frontend | Restored from sleep on 2026-10-26: viewer wake returned 204, runtime reports `RUNNING`, runtime health returns `200 ok`, and the application iframe shell returns 200 | Complete the browser journey; runtime availability is verified, rendered interactions are not |
| Monitoring | Keep Warm remains active; its old frontend check accepted the sleeping host page | New readiness checks must detect sleep/error pages and unavailable semantic scoring |
| Semantic ATS | Live synthetic probe on 2026-10-26: composite 72.8, semantic 78.8, weights 0.5/0.3/0.2; the August fallback was not reproduced | Build and verify the proposed explicit model bundle; deploy the new readiness field |
| LLM generation | Live 2026-10-26 sample: 1,672-character letter, QA honesty/tone 10/10; refinement produced 899 characters, QA 10/8; PDF export and automatic tracker update passed | Browser interaction and human judge calibration; these model verdicts are not independently validated accuracy |
| AWS | Hibernated reference deployment; custom domain is parked | Billing reconciliation and resource restoration before any re-arm |

The outage was a sleeping Streamlit runtime hidden by an overly permissive monitor;
GitHub schedule inactivity was not the cause. Deployment recovery changes under
review are not evidence of a new production release. See [deployment instructions](../DEPLOYMENT.md) and
[architecture](ARCHITECTURE.md) for the active topology.

## Verification on 2026-10-26

The deployed v4.4.3 API passed a synthetic journey: registration, login, resume
upload/parsing, full ATS scoring, asynchronous generation, refinement, PDF export,
automatic tracking and status update. Test documents and the tracker entry were
deleted afterward; the empty synthetic account remains. This verifies the API
journey separately from the untested browser interactions and unreleased source.

- **63 backend checks passed** for pure scoring/eval/runtime/sanitization behavior.
- **21 frontend checks passed** with Streamlit mocked for display and session behavior.
- **13 readiness-monitor checks passed**.
- Full PostgreSQL/Docker integration tests, a fresh real-model eval run, and an
  interactive browser journey were not run. Docker Desktop could not start in this
  environment. Mocked tests do not establish hosted behavior.
- The live API still serves v4.4.3, whose health response lacks the new semantic-model
  probe. The packaged-model improvement, stronger monitor and frontend changes are local and
  require the release process before they can be verified in production.

## Measured engineering results

| Result | Measurement | Method and limit |
|---|---|---|
| Removed irrelevant ATS score variation | Maximum movement from employer boilerplate fell **3.5 → 0 points** across **20 labeled pairs**, 2026-08-21 | Strip boilerplate before both semantic and keyword scoring; synthetic offline corpus, not hiring outcomes |
| Added repeatable scoring quality gates | **7 gating checks**; minimum strong/weak separation **34.2 points**, strong/related **29.6 points**, 2026-08-21 | Real MiniLM model; four synthetic resumes × five job descriptions; small in-repository corpus, not an independent test set |
| Reduced a backend image's footprint | **3.38 GB → 662 MB (about 80%)**, recorded 2026-06-05 | CPU-only PyTorch removed unused CUDA packages; historical build, not the current image size or a measured startup-time gain |
| Established regression coverage | Last recorded complete backend run: **340 passed, 8 expected failures**, 2026-08-21 | Docker and real PostgreSQL; this historical count does not establish that today's edited tree passes |

The scoring corpus, thresholds and reproduction command are documented in
[the evaluation guide](../backend/evals/README.md). Run `make evals` to produce a
new scorecard; keep its model, corpus, date and runtime with any reported result.

## Resume bullets supported by the record

- Eliminated up to **3.5 points of irrelevant ATS score variation across 20 labeled
  resume/job pairs** by applying employer-boilerplate filtering consistently to
  semantic and keyword scoring.
- Reduced a backend container's size by **about 80% (3.38 GB to 662 MB)** by replacing
  unused CUDA dependencies with CPU-only PyTorch for the inference workload.
- Built a reproducible ATS evaluation suite with **7 quality gates over 20 labeled
  pairs** by testing ranking separation, skill monotonicity, presentation invariance
  and semantic-model availability.

These describe engineering accomplishments. Do not convert them into claims about
users served, hours saved, acceptance rates, revenue, uptime, or cloud savings
without collecting the corresponding evidence.

## Ready-to-show criteria

- The public URL renders the application and completes login, resume upload,
  job match, cover-letter generation/refinement, PDF export and tracker updates.
- A failed dependency produces an actionable message rather than a misleading
  success or an endless loading state.
- The deployed image passes a model-backed semantic probe and the live smoke;
  CI and the offline evaluation suite pass on the release commit.
- Health monitoring detects application failures separately from provider landing
  pages; document cleanup remains operational.
- Release version, change log and user-facing documentation agree, and the
  demonstration uses synthetic data that can be safely shared.

## Next evaluation work

Add structure-varying resumes to exercise the scorer's structure component, then
calibrate the cover-letter judge against approximately 30 independently human-labeled
letters. Report agreement and Cohen's kappa only after collecting those labels.
Groundedness evaluation and retrieval-quality experiments follow that baseline.
For product impact, measure completion time and task success for a fixed application
workflow against a manual baseline, with a stated sample size and median/p95 latency.
