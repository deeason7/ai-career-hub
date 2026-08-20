# Evals

Offline measurement of the scoring and generation paths. These are **not** unit tests.
A unit test asks whether the code does what it was written to do; an eval asks whether
the *system* — model included — still behaves the way the product promises. The two
fail for different reasons and are run at different times, so they live apart:
`tests/` runs on every PR, `evals/` runs on demand and reports a scorecard.

## Running

```bash
make evals                              # in Docker, against the labeled corpus
python -m evals.runner --suite ats-sanity --json scorecard.json   # from backend/
```

The runner prints a markdown scorecard and exits non-zero when a **gating** check
fails. `--no-fail` reports without the non-zero exit. The `Evals` GitHub workflow runs
the same command on dispatch and publishes the scorecard to the run summary.

## The corpus

`datasets/` holds four resumes and five job descriptions as plain text, plus
`ats_pairs.jsonl` labeling all twenty combinations:

| relation | meaning |
|---|---|
| `strong` | the resume is a real candidate for the job |
| `related` | same broad field, wrong role — the genuinely hard case |
| `weak` | different discipline, or out of domain entirely |

The resumes are written to be structurally comparable — every one has a summary,
skills, experience, education, projects and certifications section, and all clear the
scorer's 200-word floor. That is deliberate: structure is held constant so that a
difference in score is attributable to content rather than to formatting. One job
(`warehouse_associate`) is an out-of-domain control that every resume should score
poorly against.

Fixtures are written for this repository. Nothing here is a real person's resume.

## The ATS sanity suite

| check | asks | gating |
|---|---|:--:|
| `strong_vs_weak_separation` | does a strong match outrank the same resume's weak matches? | yes |
| `strong_vs_related_margin` | by how much does it beat a same-field, wrong-role posting? | no |
| `skill_monotonicity` | can adding a skill the JD asks for ever *lower* the score? | yes |
| `jd_order_invariance` | how far does the score move when the JD's lines are reordered? | no |
| `boilerplate_invariance` | does appending an EEO and benefits block move the score? | no |
| `semantic_channel_live` | did every pair score with the embedding model actually loaded? | yes |
| `score_bounds` | are sub-scores in range and does the composite match its weights? | yes |

**Gating vs advisory.** A gating check fails the run. An advisory check is measured
and printed but never fails it. The invariance checks start advisory on purpose: the
semantic channel is order-sensitive by design, so the honest threshold is one
calibrated from observed drift on a real run, not one guessed in advance. Promote them
once there is a baseline.

**Why `semantic_channel_live` matters more than it looks.** When the embedding model
cannot be loaded, `calculate_ats_score` catches the failure, zeroes the semantic score
and renormalises the remaining weights onto keyword and structure. The composite still
comes out looking plausible while half the intended signal is missing. Every other
number on the scorecard is meaningless if that happened, so the suite checks for it
explicitly rather than trusting the top-line score.

## Adding a suite

Write a module exposing `SUITE: str` and `run(...) -> Scorecard`, then register it in
`runner.SUITES`. Take the thing under evaluation as a parameter with a lazily-imported
default, the way `ats_sanity.run` accepts `score_fn` — that keeps the checks testable
without loading a model, and `tests/test_evals.py` uses it to prove each check fails on
the regression it is meant to catch.
