# Scoring evaluations

[Project home](../../README.md) · [Product measurements](../../docs/PRODUCT.md#measuring-user-value) · [Verified status](../../docs/PROJECT_STATUS.md)

**Does the match score still behave sensibly when the real model runs?**

This suite checks the ATS scoring path against 20 synthetic résumé/job pairs.
Unit tests catch implementation regressions; these evaluations exercise the model's
ranking and consistency. Generation-quality and human-judge calibration suites
remain planned work.

**Latest recorded result: 7/7 gates passed on 2026-10-28**, using the production
`linux/amd64` image with networking disabled. See [measured baseline](#measured-baseline)
for the scores and [measurement limits](#measurement-limits) for their scope.

## Running

```bash
make evals                              # in Docker, against the labeled corpus
python -m evals.runner --suite ats-sanity --json scorecard.json   # from backend/
```

The runner prints a markdown scorecard and exits non-zero when a **gating** check
fails. `--no-fail` reports without the non-zero exit. The `Evals` GitHub workflow runs
the same command on dispatch, fails on gating regressions by default, and publishes
the scorecard to the run summary. Turn off `fail_on_regression` explicitly for a
measurement-only run.

### Verify the packaged production model

From the repository root:

```bash
docker build --platform linux/amd64 -t careerhub-api:eval ./backend
docker run --rm --platform linux/amd64 --network none \
  -e HF_HUB_OFFLINE=1 -e TRANSFORMERS_OFFLINE=1 \
  careerhub-api:eval python -m evals.runner
```

The build downloads dependencies and model weights; the evaluation container then
runs without network access. This verifies the saved model artifact instead of
relying on the developer's cache or an on-demand runtime download. It does not test
hosted availability or a real applicant's preparation time.

## The corpus

`datasets/` holds four resumes and five job descriptions as plain text, plus
`ats_pairs.jsonl` labeling all twenty combinations:

| relation | meaning |
|---|---|
| `strong` | the synthetic resume closely matches the posting's requirements |
| `related` | same broad field, wrong role |
| `weak` | different discipline, or out of domain entirely |

The resumes are written to be structurally comparable — every one has a summary,
skills, experience, education, projects and certifications section, and all exceed
200 words. Length currently affects recommendations, not the numeric structure score.
Structure is held constant so that a
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
| `boilerplate_invariance` | does appending an EEO and benefits block move the score? | 0 pts | yes |
| `semantic_channel_live` | did every pair score with the embedding model actually loaded? | 0 pairs | yes |
| `score_bounds` | are sub-scores in range and does the composite match its weights? | 0 | yes |

**Gating vs advisory.** A gating check fails the run. An advisory check is measured
and printed but never fails it — for a property worth watching that the system is not
yet expected to hold.

## Measured baseline

Originally recorded **2026-08-21**, then reproduced on **2026-10-27** and **2026-10-28**
using fresh production `linux/amd64` images with networking disabled. The latest run
used commit `0f164b7`, including the PyJWT 2.15.0 update. All seven gates passed
over the same twenty pairs with the packaged `all-MiniLM-L6-v2` model. These are
controlled offline results, not deployed availability or a hiring prediction.

| check | measured | bar | |
|---|---|---|:--:|
| `strong_vs_weak_separation` | 34.2 points | >= 5 | pass |
| `strong_vs_related_margin` | 29.6 points | >= 15 | pass |
| `skill_monotonicity` | 0 points | <= 0.5 | pass |
| `jd_order_invariance` | 3.1 points | <= 5 | pass |
| `boilerplate_invariance` | 0 points | 0 | pass |
| `semantic_channel_live` | 0 pairs | 0 | pass |
| `score_bounds` | 0 violations | 0 | pass |

Both invariance checks overshot the two points they were first guessed at, which is why
they shipped advisory rather than gating. They then went different ways.

`jd_order_invariance` was calibrated and promoted. The semantic channel reads word order,
so movement there is the model working as intended; five points absorbs ordinary drift
without letting a real regression through.

`boilerplate_invariance` was not calibrated — it was fixed. The check asserts a promise
the product already makes, and on the first run the scorer missed it by 3.5 points.
`_strip_boilerplate` drops EEO and benefits text before keyword matching and produced zero drift
in this corpus: across all twenty pairs the keyword channel moved 0.00 points.
But `_score_semantic` was handed the raw posting, so the whole 3.5 points came from the
channel carrying half the composite — a candidate's score moved with the length of an
employer's legal boilerplate. Both channels now score the stripped posting, the measured
movement is exactly zero, and the check gates at zero. Widening the bar to five would
have turned the scorecard green while leaving the defect in place.

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

## Measurement limits

- Four synthetic resumes are a small controlled corpus, not a representative sample
  of job seekers. The thresholds were calibrated on this same corpus.
- Identical resume structure isolates content relevance but leaves the structure
  component untested. Add controlled missing-section examples before reporting
  structure quality.
- Passing these checks does not establish compatibility with an employer's ATS,
  factual accuracy of generated letters, hiring success, or time saved.
- Preserve the scorecard, date, corpus revision and model/runtime configuration when
  comparing a new run. Product outcomes need a separate task-completion study.
