# Housekeeping checkpoint

**Reviewed:** 2026-10-26; verification completed 2026-10-27. **State:** source hygiene prepared; release verification pending.
Latest released version remains **v4.4.3**. Local recovery and housekeeping changes
have not been deployed. [Project status](PROJECT_STATUS.md) records the hosted evidence.

## What changed

| Area | Completed cleanup |
|---|---|
| Product presentation | Shorter product-first README, applicant journey diagram, outcome definitions and a documentation map |
| Current references | Correct hosting topology, async contracts, refresh/session behavior, scoring limits and retention limits |
| Historical material | CHANGELOG remains the release history; old AWS/context snapshots are kept as dated internal archives |
| Dependency hygiene | Removed unused frontend PDF/DOCX parsers; retained backend parsers and exercised/optional integrations |
| Security fixes | Retain rotated refresh tokens; expose exception classes rather than detailed public health errors; localhost-only development ports; require production Redis password and load it in deploy/rollback/boot paths |
| Source/build hygiene | Consistent secret/cache exclusions, one Ruff pin, broader hooks, redundant migration placeholder removed |
| Documentation maintenance | Local-link/heading and five-file release-version checks; bounded README release summary and release preflight validation |
| Branch inventory | Three confirmed merged GitHub branches deleted; nine stale local tracking refs pruned; open dependency work preserved |

## Keep, remove and defer

| Decision | Reason |
|---|---|
| Remove frontend `PyPDF2`, `python-docx` | Frontend forwards uploads and downloads API-rendered PDFs; it imports neither package |
| Keep backend document parsers | Resume extraction uses them |
| Keep migrations | They are upgrade history, not clutter |
| Keep AWS, n8n, Ollama, Chroma and legacy FAISS paths | Optional supported paths have implementation references; deleting them needs a separately scoped compatibility decision |
| Keep speculative dependency removals out of this pass | Direct-import absence alone does not prove a package is unnecessary to an installed runtime |
| Preserve open Dependabot branches | Their PRs are unmerged; bulk deletion or merging would discard pending work or introduce untested changes |
| Archive old internal plans/context | Preserve decisions and dated measurements without presenting old work as the current queue |

## Verification and release gates

Local verification on 2026-10-27 passed **118 targeted checks**: 65 backend, 24
frontend with mocked Streamlit, and 29 stdlib maintenance checks. They do not replace
the unavailable integration checks below.

| Gate | Status |
|---|---|
| Source lint/format | Passed for backend, frontend and maintenance scripts |
| Documentation links and versions | 27 Markdown files checked; all five current release markers agree at v4.4.3 |
| Targeted regression checks | 118 passed; backend tests use host doubles where applicable, frontend tests mock Streamlit |
| Compose and retained scripts | Config validation passed for localhost bindings and required Redis password; rollback passed with stubbed AWS/Docker commands; shell syntax valid. No real container execution |
| Secret history review | 416 commits scanned; two findings were historical development/test defaults; the current source scan flags one existing local test database default. No confirmed production credential exposure in these scans |
| Branch deletion verification | GitHub API independently confirms deletion of the three reviewed heads; `main`, `develop` and all eight open dependency branches remain |
| Full PostgreSQL-backed suite and Docker build | Pending: Docker socket access is denied to the agent; isolated terminal verification is prepared |
| Fresh packaged-model build and current real-model eval | Pending: not established by unit mocks or August evaluation results |
| Interactive hosted-browser journey | Pending; frontend runtime and live API journey were separately verified |
| New deployment/version and post-deploy smoke | Pending; this checkpoint is local and unreleased |
| Fresh complete dependency audit | Pending; CI's existing accepted-risk exclusions remain documented |

The earlier hosted check restored the sleeping Streamlit runtime and exercised the
API through login, upload, analysis, saved-letter generation/refinement, PDF and
tracking. It did not test the forthcoming image or establish continuous uptime.

## Known issues carried forward

The most important product gap is the separation between transient Quick Apply drafts
and saved letters with QA, revisions, PDF and tracker integration. Refinement also
lacks an explicit failure state. SQL expiration does not fully clean derived vectors,
and letter/job-description indexing shares an overwrite-prone source ID.

Security work remains: browser-readable access tokens, fail-open and non-atomic
revocation, uneven route quotas, dependency exceptions and the outbound URL
resolution/request gap. See [Security](../SECURITY.md) for precise behavior. The
cleanup reduces specific risks; it does not establish a fully secure product.

## Next checkpoint

Review the [product-led refactoring plan](REFACTORING_PLAN.md), complete the remaining
release gates, then select the first implementation slice: Quick Apply into the saved
application workflow. No new feature architecture or schema change is included in
this housekeeping pass.
