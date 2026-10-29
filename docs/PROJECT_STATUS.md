# Project status and evidence

[Documentation](README.md) / Status

**Last live verification: 2026-10-26 · Deployed API: v4.4.3 · New changes: unreleased**

The core job-application workspace, Streamlit redesign, and first ATS evaluation
suite have shipped. The current work establishes a clean documentation/security
checkpoint before further product refactoring. The
[product brief](PRODUCT.md) explains the user value; the
[refactoring plan](REFACTORING_PLAN.md) sets the next priorities.

## Deployed behavior verified on 2026-10-26

| Area | Evidence | What this establishes |
|---|---|---|
| Frontend availability | Streamlit was asleep; viewer wake returned 204, then runtime state was `RUNNING`, its health route returned `200 ok`, and the app shell returned 200 | The serving runtime recovered; browser interactions were not exercised |
| Account and résumé | Synthetic registration, login, upload, and structured parsing succeeded | The live account-to-résumé API path worked for one test account |
| Match feedback | Composite 72.8; semantic 78.8; weights 0.5/0.3/0.2 | All three scoring channels participated in this sample; August's semantic fallback was not reproduced |
| Saved application material | A 1,672-character letter was generated, then refined to 899 characters; export produced a valid PDF | Generation, refinement, and export completed through the saved-letter API path |
| Application tracking | Saved generation created a tracker entry; updating its status to `applied` succeeded | The saved-letter-to-tracker handoff worked for this sample |

The generated letter received model QA scores of 10/10 and its revision 10/8.
Those are the model's judgments, not independently established factual accuracy.
Synthetic documents and tracker records were deleted afterward; an empty smoke-test
account remains because the product has no account-deletion API.

The frontend outage was hidden by a monitor that accepted the provider's HTTP 200
sleep page. Keep Warm was still active, so GitHub schedule inactivity was not the
cause of this incident. Recovery instructions are in [DEPLOYMENT.md](../DEPLOYMENT.md).

## Released behavior and proposed improvements

The production API remains v4.4.3. Recovery changes prepared in the repository add
actual frontend-runtime checks, semantic-inference readiness, an explicit offline
model bundle, visible degraded scores, retryable session recovery, QA input
sanitization, and frontend CI. These changes require a release before they can be
verified as production behavior.

The current v4.4.3 `/health/warm` response has no semantic-model field. The new
readiness check intentionally rejects that missing signal until its matching
backend is deployed; a healthy vector store alone does not prove model inference.

AWS is a hibernated reference deployment and its custom domain is parked. Current
AWS billing has not been reconciled; retained DNS and snapshots may still cost money.

## Verification record

The updated backend and production image were verified on **2026-10-28** at commit
`0f164b7`, after the PyJWT update. The owner executed the isolated Docker script;
the saved logs and exit metadata confirm that both verification and cleanup exited
zero. The unchanged frontend retains its **2026-10-27** result.

| Check | Result | Limit |
|---|---|---|
| Full backend suite in Docker/PostgreSQL, 2026-10-28 | **363 passed, 8 expected failures** | Includes all four new JWT regressions; live-LLM cases remain expected failures without provider credentials |
| Full frontend suite in Docker, 2026-10-27 | **63 passed** | Real framework imports with mocked session/network behavior; no interactive browser journey |
| Maintenance-script suite, 2026-10-28 | **29 passed** | Readiness, docs drift and release preflight regression checks |
| Lint, formatting, documentation | Passed; **28 Markdown files**, five matching current version markers | Static checks do not prove hosted behavior |
| Production image build, 2026-10-28 | Passed, `linux/amd64`; installed PyJWT **2.15.0** verified | Candidate image remains local and unreleased |
| Bundled model inference, 2026-10-28 | Passed offline as the non-root serving user | Verifies packaged model loading rather than deployed-host behavior |
| Current model-backed scoring evaluation, 2026-10-28 | **7/7 gates passed, 20 pairs**, container network disabled | Synthetic corpus; model details and limits below |
| Interactive hosted-browser journey | Not run | Runtime/API smoke is separate evidence |
| Dependency review, 2026-10-28 | 177 package/version records queried; findings in six backend packages | Review of Docker installation logs, not a complete installed-image or deployed-environment audit |

The frontend's first full run exposed a smoke test that patched configuration after
Python had cached its imported module. The corrected test loads an isolated namespace
and covers both default and configured API URLs; the full rerun passed. Test containers,
network and disposable volumes were removed after verification.

The [cleanup checkpoint](CHECKPOINT.md) records scope and remaining release gates.
A local image and passing tests do not establish that unreleased code serves users.

The [dependency review](DEPENDENCY_REVIEW.md) reproduced a JWT parsing failure on
Python 3.11. The updated Docker suite confirms that PyJWT 2.15.0 rejects deeply
nested headers through both token helpers and returns HTTP 401 from the profile
and refresh routes. The production image separately verified the installed version
and non-root user. The latest suite totals are **455 passed**, with eight expected
failures; the eight focused helper checks overlap and are not added to that total.
Broader dependency remediation and the release gate remain open.

## Measured quality and operating results

| Result | Measurement | Method and limit |
|---|---|---|
| More consistent résumé-fit feedback | Employer-boilerplate movement fell **3.5 → 0 points across 20 labeled pairs**, 2026-08-21 | Filtering before both semantic and keyword scoring; synthetic offline corpus, not an employer acceptance result |
| Repeatable scoring evaluation | **7 gating checks**; strong/weak separation **34.2 points**, strong/related **29.6 points**, reproduced **2026-10-28** | Real MiniLM model; four synthetic résumés × five postings; not an independent test set |
| Smaller inference container | **3.38 GB → 662 MB (about 80%)**, 2026-06-05 | Historical CPU-only PyTorch build; current image size, startup improvement, and billing savings were not measured |

The [evaluation guide](../backend/evals/README.md) documents the corpus, thresholds,
and reproduction command. Preserve model, corpus, version, date, and sample size
with any reported measurement.

## What the evidence does not yet cover

- Preparation time saved, reduced review effort, user adoption, conversion, or hiring outcomes.
- Human calibration of the cover-letter judge and claim-level groundedness.
- The structure-scoring channel across varied résumé layouts; the current corpus
  deliberately holds structure constant.
- A saved application flow starting in Quick Apply. Its draft currently remains
  separate from saved-letter QA, revisions, export, and automatic tracking.
- Reliable persisted failure states for refinements; background failure can leave
  an old-text placeholder with no QA result.

The next product work should close these workflow and measurement gaps. The
[product measurement plan](PRODUCT.md#measuring-user-value) defines how to collect
business evidence without treating model scores or feature counts as user impact.
