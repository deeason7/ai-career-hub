# Dependency review

**Last reviewed: 2026-10-29.** The package inventory below remains the dated
2026-10-28 baseline; subsequent fixes have their own verification scope.

[Security](../SECURITY.md) · [Checkpoint](CHECKPOINT.md) · [Refactoring plan](REFACTORING_PLAN.md)

**Release gate: open.** The remaining dependency findings need remediation and a
fresh audit before release. The first narrow fix updates PyJWT to **2.15.0**. Its
full backend suite and rebuilt production image passed on 2026-10-28, including the
HTTP rejection regressions and offline model evaluation.

The next update pins **LangGraph 1.2.14 and langgraph-sdk 0.4.6**. Four existing
graph regression tests passed locally on Python 3.11. Full backend, task/HTTP and
production-image verification for this pair remain pending.

## What was checked

The successful Docker installation logs from 2026-10-27 identify **166 backend** and
**35 frontend** package/version records, or **177 distinct records** after accounting
for shared packages. Each was queried against the [PyPI release API](https://docs.pypi.org/api/json/)
on 2026-10-28, with no advisory exclusions and no failed queries. The CPU PyTorch
wheel `2.12.0+cpu` was checked against advisories for its base version, `2.12.0`.

The baseline returned **28 advisory groups across six backend packages**, merging
records with shared advisory aliases. Different advisory IDs can still describe
overlapping issues; this is not a count of independently exploitable vulnerabilities.
No advisories were returned for the 35 recorded frontend packages.

This is a dated review of installation records, not a complete installed-image scan.
It excludes preinstalled base-image packages, operating-system libraries, development
tools and GitHub Actions. It also does not establish the versions currently deployed.
The 2026-10-28 rebuild verifies the updated PyJWT pin but does not refresh this advisory
inventory. Other dependency ranges also resolved new versions, so the rebuilt
environment still needs a complete audit. An empty advisory response is not proof
of security.

GitHub separately reported **30 default-branch alerts** during publication:
4 critical, 10 high, 14 moderate and 2 low. Those repository alerts have not been
exported and reconciled individually. Their count must not be compared directly with
this container-log inventory or presented as a measured reduction.

## Findings and disposition

| Package in the tested build | Findings | Application context and next action |
|---|---|---|
| PyJWT 2.13.0 | 15 advisory groups, including [uncaught header recursion](https://github.com/advisories/GHSA-8wjv-2p76-3863) | Pin updated to 2.15.0. The full backend suite, including new helper/HTTP rejection tests and existing login/refresh/logout coverage, passed on 2026-10-28. The production image confirms the installed version; the fix remains unreleased. |
| langgraph-sdk 0.4.2 | [Resource authorization decorators ignore action filters](https://github.com/advisories/GHSA-fvww-7h3r-vfhp), high | Application code uses in-process `StateGraph`, not the SDK's server authorization decorators. Updated to 0.4.6 with LangGraph 1.2.14 after the October 29 review found a second advisory affecting the originally proposed 0.4.4 candidate. Local graph tests pass; container/task checks remain pending. |
| sentence-transformers 3.0.1 | [Local-model trust bypass](https://github.com/advisories/GHSA-jhr6-gm9c-rqjv), critical | The image loads a bundled model directory. No request accepts a model path, but model artifacts remain part of the trust boundary. Review the 5.6.0 fix together with Transformers; preserve offline loading and scoring behavior. |
| transformers 4.57.6 | Six advisory groups involving model loading, conversion, training and artifact writes | Several affected functions are outside this application's usage. The build does save model/tokenizer artifacts, so review [artifact path validation](https://github.com/advisories/GHSA-xrqw-3rrv-vx5w) as well. Sentence Transformers 3.0.1 requires Transformers below 5; a coordinated upgrade is needed to evaluate the 5.x fixes. |
| chromadb 1.5.9 | Four advisory groups: server code injection and cross-tenant authorization | The application uses an embedded `PersistentClient`; the documented hosted configuration uses Qdrant. No Chroma HTTP server is configured by this repository. The [server injection advisory](https://github.com/advisories/GHSA-f4j7-r4q5-qw2c) has no listed fix in the queried feed. Record this deployment constraint explicitly; per-user collection names alone are not an authorization defense for an exposed Chroma server. |
| torch 2.12.0+cpu | [`torch.jit.script` memory corruption](https://github.com/advisories/GHSA-rrmf-rvhw-rf47) | No application call to `torch.jit.script` was found. Review the listed 2.13.0 fix with the encoder upgrade, keeping the CPU-only wheel and validating the packaged model. |

These usage assessments come from the current source and configuration. They are
not evidence that every transitive library path is unreachable, and they do not add
new accepted-risk exceptions.

## JWT regression and verification

On **Python 3.11**, the production Python minor version, a deeply nested unsigned
header raises `RecursionError` through both existing verification helpers with
PyJWT 2.13.0. Their error handlers catch JWT errors, so that exception escapes the
normal invalid-credential result. PyJWT 2.15.0 converts it into a handled decode error.
This matches the [published header-parsing advisory](https://github.com/advisories/GHSA-8wjv-2p76-3863).

The focused comparison used the exact token-helper function bodies, isolated test
settings and official wheels verified against PyPI SHA-256 digests. With 2.15.0,
**8/8 local checks passed**: valid access and refresh tokens, token-type separation,
expiry, malformed input and nested-header rejection in both helpers. With 2.13.0,
the two nested-header cases raised `RecursionError`. The same input did not reproduce
the failure on the local Python 3.14 interpreter, which is why matching Python 3.11
matters. These checks did not exercise HTTP routes or PostgreSQL.

[Token parsing regressions](../backend/tests/test_token_parsing.py) cover both helpers
and require HTTP 401 from the profile and refresh routes. All four passed in the
PostgreSQL-backed Docker run at commit `0f164b7` on **2026-10-28**: **363 passed,
8 expected live-provider failures** overall. The production `linux/amd64` image
verified PyJWT 2.15.0 and non-root execution, then passed **7/7 scoring gates across
20 pairs** with networking disabled. Verification and disposable-resource cleanup
both exited zero. The unchanged frontend retains its 63-test result from 2026-10-27.
These results validate the narrow update; CI and hosted-release checks remain separate.

## LangGraph follow-up — 2026-10-29

A fresh check found [unencoded identifiers in remote streaming requests](https://github.com/langchain-ai/langgraph/security/advisories/GHSA-3fx2-cqw9-xr3c).
It affects SDK versions 0.4.0–0.4.5 and LangGraph's `RemoteGraph` integration when
paired with an affected SDK. An application must pass attacker-controlled thread
or assistant identifiers to that streaming client for the described path redirection
to occur. This additional advisory was not in the earlier inventory response; the
baseline's 28-group count has not been silently revised.

The requirements now pin SDK **0.4.6** and LangGraph **1.2.14**. The SDK fixes both
the action-filter and streaming-path issues; the LangGraph patch raises its SDK
minimum to the fixed version. Their published requirements remain compatible with
the existing LangChain Core 1.4.8 and checkpoint 4.1.1 pins. No new package or audit
exception was added. Application source uses local `StateGraph`, with no SDK auth
decorators or `RemoteGraph` calls found; this is a source usage assessment, not proof
that every transitive path is unreachable.

On macOS/Python **3.11.16**, the four existing `TestAgentGraph` cases passed with
the actual updated libraries: graph compilation, the seven-step workflow, early
termination on scrape failure and resilience to progress-callback errors. The
isolated environment used 42 official wheels checked against PyPI SHA-256 digests,
retaining the other versions from the October 28 build. External tools were mocked
as in the existing tests. Database fixtures and endpoint tests were not run.

These four checks overlap the full suite; they do not increase its 455-test historical
total. The October 28 Docker success predates these two pins. A fresh full backend
run must cover task submission/polling and verify both installed versions in the
production image before this follow-up is considered container-verified.

## Audit coverage that still needs work

The current pipeline audits backend requirements with **27 exclusions**. Only six
exclusion identifiers match active advisory aliases in this recorded baseline; the
other 21 need review against a fresh resolution before removal. Existing exceptions
do not cover all the current findings. Frontend packages are not audited by CI.

Before closing this gate:

1. Complete container/task verification of the LangGraph pair, then review the
   encoder/Transformers/PyTorch upgrades together. Rerun all seven scoring gates on
   the same 20-pair corpus and compare the scores.
2. Audit the resolved backend and frontend environments with findings visible before
   applying any reviewed exceptions. Check base-image and OS packages separately.
3. Replace stale exception claims with advisory-specific rationale, deployment
   conditions, review dates and an owner decision for each unresolved finding.
4. Reconcile the repository's default-branch alerts and verify deployed versions after
   an authorized release. Preserve the eight open dependency PRs until reviewed.

The JWT and LangGraph changes do not close the wider dependency or deployment gates.
