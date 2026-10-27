# Refactoring plan: complete the application journey

[Product brief](PRODUCT.md) · [Cleanup checkpoint](CHECKPOINT.md) · [Current evidence](PROJECT_STATUS.md)

The product helps a candidate decide whether a role fits, prepare application
material they can review, and follow up on applications. The next phase should
make those three outcomes work as one journey. This is a plan after the housekeeping
checkpoint; the features below are not represented as shipped.

## Product narrative

| Outcome | What the product does today | Next improvement |
|---|---|---|
| Decide where to apply | Compares a resume with a posting, explains fit signals and skill gaps | Keep the source posting and evidence attached to the application |
| Prepare an application | Generates a letter; the saved-letter path adds QA, revisions and PDF export | Bring Quick Apply into that same saved and reviewable workflow |
| Follow through | Tracks application status, notes and deadlines | Carry the reviewed application into the tracker without re-entry |

The portfolio story should follow this sequence. Technology explains **how** the
outcome was delivered; it does not substitute for evidence that the outcome improved.

## 0. Close the housekeeping and release gates

Finish the [checkpoint gates](CHECKPOINT.md#verification-and-release-gates) before
starting the next feature branch. Preserve the current release number until a tested
release is deliberately cut. Full database tests, a fresh image/model build, current
real-model evaluation and interactive hosted-browser checks remain required.

Acceptance: one navigable documentation set, clean feature branch, reconciled branch
inventory, explicit security limitations, passing available checks and a dated list
of unrun checks. No AWS restoration or broad dependency upgrade is part of cleanup.

## 1. Connect Quick Apply to a saved application

**User value:** a candidate can return to the application, review its claims, revise
it and track it without copying a transient draft into a different tool.

Extract a shared application service from the saved-letter route. Have Quick Apply
call that service and return stable letter/application identifiers. Reuse the existing
QA, revision, PDF and tracker services rather than constructing a second implementation.
Keep job URL, extracted posting and fit results associated with the saved application.
Decide any required schema/migration separately, with a rollback and data migration plan.

Acceptance:

- URL or pasted posting → selected resume → fit review → saved draft → QA → revision
  → PDF → tracker is a single navigable journey.
- Refreshing/reopening the page retrieves the saved work.
- Retrying a submission does not create duplicate letters or tracker entries.
- Partial analysis is visible and cannot masquerade as a completed application.
- Ownership checks cover every linked record and cross-user lookup.

Measure successful journey completion, manual copying steps and median preparation
time using the same scripted tasks before and after the change.

## 2. Make waiting, failure and recovery understandable

**User value:** candidates know whether work is running, finished or needs a retry,
and do not mistake old content for a newly refined letter.

Introduce an explicit refinement lifecycle with persisted failure information. Align
client polling around a documented status contract while preserving compatibility
where necessary. Define timeouts, interruption handling, retry and idempotency before
choosing a durable worker system; a new queue dependency is not automatically required.

Acceptance: generation/refinement success, provider limits, process interruption,
expired task state and retry all produce bounded, actionable UI states. A placeholder
revision cannot be activated as a successful new result. Terminal failures survive
reload, and a retry produces at most one intended revision.

Measure failed/stuck run frequency, recovery success and time to a useful error message.

## 3. Complete privacy and document lifecycle behavior

**User value:** deleting or expiring an application removes its associated personal
material consistently and retrieval cannot resurrect stale document text.

Create a deletion service covering relational records and vectors, with retryable
cleanup records if one store is unavailable. Give resume, letter and job-description
chunks distinct source identities. Address the existing shared-source-ID overwrite
in letter/job-description indexing. Preserve tracker history deliberately when a
letter is removed, with clear UI wording about what remains.

Acceptance: explicit deletion and scheduled expiry remove all intended source chunks;
vector outage/retry is recoverable; repeated cleanup is safe; reindex does not recreate
deleted content; one user's deletion never affects another user's collection. Verify
the authenticated daily cleanup schedule and its reported results.

Measure cross-store deletion completeness and retry recovery using seeded fixtures.
These are controlled test results, not a claim about all provider backups or logs.

## 4. Strengthen sessions and reproducible delivery

**User value:** users retain an understandable session and the demo behaves consistently
across rebuilds, outages and releases.

Review server-managed browser sessions, atomic refresh rotation and the intentional
Redis fail-open policy as explicit design choices. Review route quotas, upload/resource
limits and outbound URL controls. Inventory current backend audit exceptions and pin
frontend dependencies against a tested Python/Streamlit baseline. Remove further
optional packages only after an import inventory, clean image build and exercised
fallback path demonstrate they are unused.

Acceptance: threat-focused tests for ownership, replay, logout, outage and URL handling;
a reproducible image with offline model loading; dependency audit results including
accepted exceptions; actual frontend runtime and semantic inference checked after deploy.
Independent monitoring can follow if GitHub scheduling proves insufficient.

## 5. Gather evidence for three résumé bullets

Run a small, consented usability study or a clearly labeled controlled benchmark.
Use representative resume/posting pairs, the same task boundaries for the manual
baseline and product flow, and record sample size, failures and observation dates.
Avoid storing real resumes in analytics or public fixtures. Model QA scores are not
independent evidence of factual accuracy; human review must label unsupported claims.

| X: accomplishment | Y: evidence to collect | Z: method to explain |
|---|---|---|
| Helped candidates prioritize relevant roles | Fit-review completion and time; evaluation quality on a labeled corpus | Explainable semantic, keyword and section analysis linked to a saved posting |
| Reduced application preparation effort | Median end-to-end preparation time versus a manual baseline; completion rate and unsupported-claim rate | Unified drafting, claim review, revision and export |
| Improved application follow-through | Percentage of completed drafts linked to tracker records; duplicate and missing-record counts | Persistent application IDs and a direct draft-to-tracker handoff |

Use measured results in the final XYZ bullets only after collecting them. A truthful
current description may state demonstrated scope (one tested API journey, seven
agent steps, a 20-pair synthetic scoring corpus), but these counts are not user
adoption, hours saved, hiring improvements or revenue. See [Product](PRODUCT.md) for
three present-tense portfolio statements and [Status](PROJECT_STATUS.md) for dated evidence.

## Scope boundaries

Keep FastAPI, Streamlit, the shared encoder, existing deployment options and migration
history during this sequence. A visual refresh should improve the completed workflow
and accessibility after its states are coherent. A framework rewrite, model fine-tune,
new cloud stack or broad package upgrade requires its own measured problem and plan.
