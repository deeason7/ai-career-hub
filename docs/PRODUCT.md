# Product brief

[Documentation](README.md) / Product

**AI Career Hub is a job-application workspace for candidates who want to turn
existing experience into a relevant, reviewable application and keep track of it.**

## The problem it addresses

Preparing for each role repeats several tasks: understand the posting, compare it
with a résumé, decide what to emphasize, draft a letter, prepare for questions, and
update a separate tracker. Context gets copied between tools, and a generic AI draft
can introduce claims the candidate cannot defend.

The product brings these tasks into one workspace. Its intended value is less
repeated preparation, clearer feedback, more reviewable drafts, and better visibility
of the next application step. Actual time saved and hiring outcomes remain unmeasured.

## Who it serves

The current product serves individual job seekers preparing applications from an
existing résumé. It is useful for exploring related roles and adapting material
without starting from a blank page. The current scoring corpus concentrates on
technical roles; its evaluation does not establish equal performance across every
profession, résumé format, or language.

Employers' selection decisions and application submission remain outside the
workspace. A match score describes the app's comparison, not the probability of an
interview or an actual employer ATS result.

## Three parts of the product story

| Outcome to support | Current capabilities | Evidence available |
|---|---|---|
| **Choose what to emphasize for a role** | Résumé parsing, semantic/keyword/structure feedback, skill gaps, and interview questions | Twenty labeled résumé/job pairs exercise scoring behavior; a deployed synthetic score used all three channels |
| **Prepare material you can review** | Résumé-context drafting, AI honesty/tone review on saved letters, targeted refinements, version history, and PDF export | Saved generation, QA results, refinement, and PDF export passed the 2026-10-26 API journey |
| **Keep the application moving** | Saved letter generation creates a wishlist entry; users manage status, deadline, and notes | Automatic tracking and an application status update passed that same journey |

These are demonstrated capabilities. They are the basis for testing business value,
not substitutes for measured reductions in effort or increases in completion.

## Current user journey

1. **Establish the source material.** Upload a résumé and choose it for the role.
2. **Understand the role.** Paste a job description into Job Match; review match
   components, skill gaps, and interview questions.
3. **Prepare and review.** Generate a saved cover letter, inspect the QA feedback,
   make targeted edits, and choose a revision to export.
4. **Follow through.** Review the automatically created tracker entry, submit the
   application through the employer's process, and update its status or deadline.

Quick Apply offers a second entry point: a public job URL triggers fetching,
metadata extraction, company research, scoring, gaps, drafting, and interview
questions. It currently returns an analysis result with a draft rather than a
saved cover-letter record. Its draft does not pass through the saved-letter QA,
revision, PDF, and auto-tracker flow. Unifying these paths is the clearest future
refactoring opportunity: one reviewable application record from either entry point.
Job sites that require login or block fetching may need a pasted description instead.

## Measuring user value

Measure the user's completed task, including review and correction. Model response
time alone leaves out the work required to make a draft usable.

| Metric | Definition | Baseline and acceptance rule |
|---|---|---|
| Application preparation time | Elapsed time from the same résumé/posting pair to an approved letter, exported PDF, and correct tracker record | Compare manual preparation with assisted preparation; include reading, edits, waits, and error recovery; report paired median time and sample size |
| Task completion rate | Completed application packages divided by all attempted tasks | Use the same checklist for both methods; count abandoned or failed attempts in the denominator |
| Review effort | Time spent correcting a draft and count of factual corrections | Have a reviewer check each claim against the source résumé; separate style edits from factual corrections |
| Unsupported-claim rate | Unsupported factual claims divided by reviewed factual claims | Human labels are required; the product's own QA score is not ground truth |
| Tracker completeness | Generated applications with the correct company, role, status, and linked letter divided by eligible saved generations | Check the actual stored record and include failed auto-tracking attempts |
| Service reliability | Successful user-task attempts divided by attempts over a stated period | Distinguish provider sleep, API failure, model failure, and invalid input; include dates and the monitoring coverage |

A first study can use synthetic résumés and postings so the evaluation does not
require applicants' private documents. Define the task checklist before running it,
rotate manual/assisted order to reduce practice effects, and record product version,
provider/model, trial count, failures, and reviewer decisions. Use a small pilot to
improve the protocol before quoting percentage gains. A later user study needs its
own participant consent and data-retention plan.

For paired completed tasks, the time-reduction calculation is
`(manual time − assisted time) / manual time × 100%`. Report completion rate beside
it so dropping failed assisted runs cannot make the result look faster. No target
percentage is claimed as an achieved result.

## Portfolio narrative

These three statements explain the product and the value it is designed to deliver:

- Built an AI job-application workspace that combines résumé-fit feedback,
  tailored cover letters, interview preparation, and application tracking using
  FastAPI, Streamlit, and Groq.
- Connected application drafting to follow-through by adding QA-reviewed saved
  letters, versioned refinements, PDF export, and automatic tracker creation,
  verified through a deployed synthetic application workflow.
- Made résumé-fit feedback more consistent by eliminating up to **3.5 points of
  irrelevant score variation across 20 labeled résumé/job pairs** through shared
  boilerplate filtering in semantic and keyword scoring.

The first two describe delivered capability and operational evidence; they do not
claim quantified user impact. The third includes a measured offline quality result.
For strict accomplishment–measurement–action résumé bullets, replace capability
scope with the preparation-time, completion, or review-effort results after the study.
Do not fill that measurement with an invented percentage or the product's own QA score.

## Priorities after the cleanup checkpoint

1. **One application record across entry points.** Connect Quick Apply to the saved
   drafting/review/tracker workflow with explicit transitions and visible failures.
2. **Trustworthy completion states.** Make interrupted generation and failed
   refinements distinguishable from usable drafts; preserve user work on retries.
3. **An evidence-led demonstration.** Use a repeatable synthetic task to show the
   complete experience and collect preparation/completion measurements.
4. **Calibrated feedback.** Extend structure coverage in scoring evaluations and
   compare the letter judge with independent human labels.

These are future changes, not work completed by documentation cleanup. The
[status page](PROJECT_STATUS.md) records the current release and verification limits;
[architecture decisions](adr/README.md) describe the constraints a refactor must preserve.
