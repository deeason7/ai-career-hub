# Housekeeping checkpoint

**Reviewed:** 2026-10-29. **State:** the JWT checkpoint is container-verified; the LangGraph follow-up has local graph checks only. Dependency remediation and release verification remain open.
Latest released version remains **v4.4.3**. Local recovery and housekeeping changes
have not been deployed. [Project status](PROJECT_STATUS.md) records the hosted evidence.

The [dependency review](DEPENDENCY_REVIEW.md) led to a PyJWT 2.15.0 update. The full
backend suite, four new token-parsing regressions and rebuilt production image passed
on 2026-10-28 at commit `0f164b7`. The image also passed all seven offline scoring gates.
The subsequent LangGraph 1.2.14 / SDK 0.4.6 update passes four local graph tests;
its full backend/task and production-image verification is still pending.

## What changed

| Area | Completed cleanup |
|---|---|
| Product presentation | Shorter product-first README, applicant journey diagram, outcome definitions and a documentation map |
| Current references | Correct hosting topology, async contracts, refresh/session behavior, scoring limits and retention limits |
| Historical material | CHANGELOG remains the release history; old AWS/context snapshots are kept as dated internal archives |
| Dependency hygiene | Removed unused frontend PDF/DOCX parsers; retained backend parsers and exercised/optional integrations |
| Security fixes | Reject deeply nested JWT headers with PyJWT 2.15.0; retain rotated refresh tokens; redact public health errors; bind development ports to localhost; require and consistently load the production Redis password |
| Source/build hygiene | Consistent secret/cache exclusions, one Ruff pin, broader hooks, redundant migration placeholder removed |
| Documentation maintenance | Local-link/heading and five-file release-version checks; bounded README release summary and release preflight validation |
| Branch inventory | Three confirmed merged GitHub branches and one redundant local recovery branch deleted; nine stale tracking refs pruned; open dependency work preserved |

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

The latest passing suites total **455 checks**: 363 in the PostgreSQL-backed backend
Docker suite and 29 stdlib maintenance checks on 2026-10-28, plus 63 frontend Docker
checks on 2026-10-27. The backend rerun includes all four new JWT regressions; the
unchanged frontend was skipped. Eight live-LLM tests remain expected failures without
provider credentials. Earlier runs and isolated helper checks are not counted again.
These dated results predate the LangGraph follow-up; its four local tests overlap
the backend suite and are not added to the total.

| Gate | Status |
|---|---|
| Source lint/format | Passed for backend, frontend and maintenance scripts |
| Documentation links and versions | 28 Markdown files checked; all five current release markers agree at v4.4.3 |
| Maintenance regression checks | 29 passed; readiness, documentation and release preflight |
| Compose and retained scripts | Config validation passed for localhost bindings and required Redis password; rollback passed with stubbed AWS/Docker commands; shell syntax valid. AWS/production Redis startup remains unexercised |
| Secret history review | 416 commits scanned; two findings were historical development/test defaults; the current source scan flags one existing local test database default. No confirmed production credential exposure in these scans |
| Branch deletion verification | GitHub API independently confirms deletion of the three reviewed heads; `main`, `develop` and all eight open dependency branches remain |
| Full PostgreSQL-backed Docker suite | 363 passed, 8 expected failures on 2026-10-28; includes malformed access/refresh headers and HTTP 401 responses from profile/refresh routes |
| LangGraph follow-up, 2026-10-29 | Four existing local graph tests passed with LangGraph 1.2.14 and SDK 0.4.6; full backend/task and image verification pending |
| Full frontend Docker suite | 63 passed on 2026-10-27 after isolating the API configuration test from Python’s import cache; real framework imports, mocked session/network interactions |
| Packaged-model build and real-model eval, before the LangGraph update | Production `linux/amd64` image rebuilt on 2026-10-28; PyJWT 2.15.0 and non-root serving verified; all seven scoring gates passed on 20 pairs with the container network disabled |
| Interactive hosted-browser journey | Pending; frontend runtime and live API journey were separately verified |
| New deployment/version and post-deploy smoke | Pending; this checkpoint is unreleased |
| Dependency review and remediation | 177 package/version records from the earlier build checked on 2026-10-28; findings in six backend packages. The PyJWT update is container-verified; a complete audit and remaining remediation are pending |

The earlier hosted check restored the sleeping Streamlit runtime and exercised the
API through login, upload, analysis, saved-letter generation/refinement, PDF and
tracking. The new image was verified separately in Docker; hosted behavior after
deploy and continuous uptime remain unverified. The terminal script exited zero and
removed its disposable test containers, network and volumes.

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
