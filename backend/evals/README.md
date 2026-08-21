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

| check | asks | bar | gating |
|---|---|---|:--:|
| `strong_vs_weak_separation` | does a strong match outrank the same resume's weak matches? | >= 5 pts | yes |
| `strong_vs_related_margin` | by how much does it beat a same-field, wrong-role posting? | >= 15 pts | yes |
| `skill_monotonicity` | can adding a skill the JD asks for ever *lower* the score? | <= 0.5 pts | yes |
| `jd_order_invariance` | how far does the score move when the JD's lines are reordered? | <= 5 pts | yes |
| `boilerplate_invariance` | does appending an EEO and benefits block move the score? | <= 2 pts | no |
| `semantic_channel_live` | did every pair score with the embedding model actually loaded? | 0 pairs | yes |
| `score_bounds` | are sub-scores in range and does the composite match its weights? | 0 | yes |

**Gating vs advisory.** A gating check fails the run. An advisory check is measured
and printed but never fails it — for a property worth watching that the system is not
yet expected to hold.

## Measured baseline

First run against `all-MiniLM-L6-v2` over the twenty pairs, reproduced identically on a
second run:

| check | measured | bar | |
|---|---|---|:--:|
| `strong_vs_weak_separation` | 34.2 points | >= 5 | pass |
| `strong_vs_related_margin` | 29.6 points | >= 15 | pass |
| `skill_monotonicity` | 0 points | <= 0.5 | pass |
| `jd_order_invariance` | 3.1 points | <= 5 | pass |
| `boilerplate_invariance` | 3.5 points | <= 2 | advisory |
| `semantic_channel_live` | 0 pairs | 0 | pass |
| `score_bounds` | 0 violations | 0 | pass |

Both invariance checks overshot the two points they were first guessed at, which is why
they shipped advisory instead of gating.

`jd_order_invariance` was calibrated from that measurement and promoted. The semantic
channel reads word order, so some movement is the model working as intended; five points
absorbs drift without letting a real regression through.

`boilerplate_invariance` was deliberately **not** calibrated. Its bar stays at two points
— where the product's promise is — and the check stays advisory while it misses it.
`_strip_boilerplate` drops EEO and benefits text before keyword matching and does its job
perfectly: measured across all twenty pairs, the keyword channel moves 0.00 points. But
`_score_semantic` receives the raw job description, so the entire 3.5 points comes from
the channel carrying half the composite. That is a defect to close, not a threshold to
widen — raising the bar to five would have turned the scorecard green by forgetting what
it found.

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
