"""Tests for the eval harness itself — the checks must be able to fail, not just pass."""

import re

import pytest

from app.services.ats_scorer import ATSResult
from evals import ats_sanity
from evals.corpus import RELATIONS, Pair, load_ats_pairs
from evals.metrics import agreement_rate, cohen_kappa, mean
from evals.scorecard import CheckResult, Scorecard

# --- Stub scorer -------------------------------------------------------------
# The real scorer needs an 80 MB sentence-transformers model. These tests drive
# the checks with a stub whose numbers we choose, which is the only way to prove
# a check fires on a regression rather than merely passing on healthy data.

RESUME_TMPL = "SUMMARY\nmarker {rid}\n\nSKILLS\npython, sql\n\nEXPERIENCE\n- shipped things\n"
JOB_TMPL = "Job posting {jid}\n- requirement one\n- requirement two\n"

TARGETS = {
    ("a", "1"): 70.0,  # strong
    ("a", "2"): 40.0,  # weak
    ("b", "2"): 68.0,  # strong
    ("b", "1"): 42.0,  # weak
}


def _result(target: float, *, missing=("docker",), semantic_weight=0.50) -> ATSResult:
    """Build an ATSResult whose composite is exactly `target` and internally consistent.

    `semantic_weight=0.0` reproduces the real degraded state: when the embedding
    model fails to load the scorer zeroes the semantic score and renormalises onto
    keyword and structure alone.
    """
    keyword_weight = 0.30 if semantic_weight else 0.80
    if semantic_weight:
        semantic = (target - 50.0 * keyword_weight - 50.0 * 0.20) / semantic_weight
    else:
        semantic = 0.0
        target = 50.0 * keyword_weight + 50.0 * 0.20
    return ATSResult(
        score=round(target, 1),
        semantic_score=round(semantic, 1),
        keyword_score=50.0,
        structure_score=50.0,
        matched_keywords=[],
        missing_keywords=list(missing),
        recommendations=[],
        section_scores={},
        breakdown={
            "semantic_weight": semantic_weight,
            "keyword_weight": keyword_weight,
            "structure_weight": 0.20,
            "model": "stub",
        },
    )


def _ids(resume_text: str, job_text: str) -> tuple[str, str]:
    rid = re.search(r"marker (\w+)", resume_text).group(1)
    jid = re.search(r"Job posting (\w+)", job_text).group(1)
    return rid, jid


def _pairs() -> list[Pair]:
    return [
        Pair(
            resume_id=rid,
            job_id=jid,
            relation="strong" if TARGETS[(rid, jid)] > 50 else "weak",
            note="",
            resume_text=RESUME_TMPL.format(rid=rid),
            job_text=JOB_TMPL.format(jid=jid),
        )
        for rid, jid in TARGETS
    ]


def _related_scenario(related_score: float):
    """One resume scored against a strong, a related and a weak posting.

    The default corpus above has no `related` pairs, so the margin check falls into
    its not-applicable branch there and cannot be driven to fail.
    """
    targets = {("a", "1"): 70.0, ("a", "3"): related_score, ("a", "2"): 40.0}
    relations = {"1": "strong", "3": "related", "2": "weak"}
    pairs = [
        Pair(
            resume_id=rid,
            job_id=jid,
            relation=relations[jid],
            note="",
            resume_text=RESUME_TMPL.format(rid=rid),
            job_text=JOB_TMPL.format(jid=jid),
        )
        for rid, jid in targets
    ]

    def score_fn(resume_text: str, job_text: str) -> ATSResult:
        return _result(targets[_ids(resume_text, job_text)])

    return pairs, score_fn


def _scorer(
    *, resume_penalty=0.0, jd_penalty=0.0, invert=False, semantic_weight=0.50, broken=False
):
    """A stub scorer with dials for each failure mode a check is meant to catch."""

    def score_fn(resume_text: str, job_text: str) -> ATSResult:
        rid, jid = _ids(resume_text, job_text)
        target = TARGETS[(rid, jid)]
        if invert:
            target = 110.0 - target  # turns strong matches into weak ones and back
        if resume_text != RESUME_TMPL.format(rid=rid):
            target -= resume_penalty
        if job_text != JOB_TMPL.format(jid=jid):
            target -= jd_penalty
        result = _result(target, semantic_weight=semantic_weight)
        if broken:
            result = ATSResult(**{**result.__dict__, "score": result.score + 25.0})
        return result

    return score_fn


# --- Corpus ------------------------------------------------------------------


def test_corpus_loads_and_resolves_every_fixture():
    pairs = load_ats_pairs()
    assert len(pairs) >= 12
    for pair in pairs:
        assert pair.relation in RELATIONS
        assert pair.resume_text.strip()
        assert pair.job_text.strip()


def test_corpus_covers_every_resume_with_a_strong_and_a_weak_pair():
    by_resume = {}
    for pair in load_ats_pairs():
        by_resume.setdefault(pair.resume_id, set()).add(pair.relation)
    assert by_resume, "corpus is empty"
    for resume_id, relations in by_resume.items():
        assert {"strong", "weak"} <= relations, f"{resume_id} cannot be separation-tested"


def test_corpus_is_cached():
    assert load_ats_pairs() is load_ats_pairs()


# --- Metrics -----------------------------------------------------------------


def test_mean_of_empty_is_zero():
    assert mean([]) == 0.0


def test_perfect_agreement_is_kappa_one():
    labels = ["pass", "fail", "pass", "fail"]
    assert agreement_rate(labels, labels) == 1.0
    assert cohen_kappa(labels, labels) == pytest.approx(1.0)


def test_kappa_discounts_chance_agreement():
    # Raw agreement is 50% here, but both raters split their labels evenly, so
    # half of that is what chance alone would produce — kappa lands near zero.
    a = ["pass", "pass", "fail", "fail"]
    b = ["pass", "fail", "pass", "fail"]
    assert agreement_rate(a, b) == 0.5
    assert cohen_kappa(a, b) == pytest.approx(0.0, abs=1e-9)


def test_kappa_is_zero_when_a_rater_never_varies():
    a = ["pass"] * 5
    assert agreement_rate(a, a) == 1.0
    assert cohen_kappa(a, a) == 0.0


def test_kappa_known_value():
    # 20 items: 8 pass/pass, 7 fail/fail, 3 pass/fail, 2 fail/pass.
    a = ["pass"] * 8 + ["fail"] * 7 + ["pass"] * 3 + ["fail"] * 2
    b = ["pass"] * 8 + ["fail"] * 7 + ["fail"] * 3 + ["pass"] * 2
    # observed .75; expected .5*.55 + .5*.45 = .5 -> (.75-.5)/(1-.5)
    assert cohen_kappa(a, b) == pytest.approx(0.5)


def test_metrics_reject_mismatched_lengths():
    with pytest.raises(ValueError, match="differ in length"):
        cohen_kappa(["a"], ["a", "b"])


# --- Scorecard ---------------------------------------------------------------


def test_direction_min_passes_at_or_above_threshold():
    at = CheckResult("x", 5.0, 5.0, "min", "points", "")
    below = CheckResult("x", 4.9, 5.0, "min", "points", "")
    assert at.passed and not below.passed


def test_direction_max_passes_at_or_below_threshold():
    at = CheckResult("x", 2.0, 2.0, "max", "points", "")
    above = CheckResult("x", 2.1, 2.0, "max", "points", "")
    assert at.passed and not above.passed


def test_bad_direction_is_rejected_at_construction():
    with pytest.raises(ValueError, match="direction"):
        CheckResult("x", 1.0, 1.0, "minimum", "points", "")


def test_advisory_failures_do_not_fail_the_scorecard():
    card = Scorecard(
        suite="s",
        results=[
            CheckResult("gate", 10.0, 5.0, "min", "points", ""),
            CheckResult("advisory", 0.0, 5.0, "min", "points", "", gating=False),
        ],
    )
    assert card.passed
    assert card.failures == []


def test_gating_failure_fails_the_scorecard():
    card = Scorecard(suite="s", results=[CheckResult("gate", 1.0, 5.0, "min", "points", "")])
    assert not card.passed
    assert [r.name for r in card.failures] == ["gate"]


def test_scorecard_renders_markdown_and_json():
    card = Scorecard(
        suite="demo",
        results=[CheckResult("gate", 9.0, 5.0, "min", "points", "fine", samples=["one"])],
        meta={"pairs": 4},
    )
    md = card.to_markdown()
    assert "demo — PASS" in md and "gate" in md and "one" in md
    assert card.to_dict()["checks"][0]["passed"] is True


# --- Perturbation helpers ----------------------------------------------------


def test_add_skill_extends_the_existing_skills_line():
    resume = RESUME_TMPL.format(rid="a")
    out = ats_sanity._add_skill(resume, "docker")
    assert "python, sql, docker" in out
    assert out.count("SKILLS") == 1, "must not introduce a second section header"


def test_add_skill_falls_back_when_no_skills_section():
    out = ats_sanity._add_skill("EXPERIENCE\n- did things", "docker")
    assert out.endswith("docker")


def test_shuffle_preserves_content_and_is_deterministic():
    job = JOB_TMPL.format(jid="1")
    once = ats_sanity._shuffle_lines(job, ats_sanity.SHUFFLE_SEED)
    twice = ats_sanity._shuffle_lines(job, ats_sanity.SHUFFLE_SEED)
    assert once == twice
    assert sorted(once.split("\n")) == sorted(ln for ln in job.split("\n") if ln.strip())


# --- The suite ---------------------------------------------------------------


def _by_name(card: Scorecard) -> dict[str, CheckResult]:
    return {r.name: r for r in card.results}


def test_healthy_scorer_passes_every_gating_check():
    card = ats_sanity.run(_pairs(), _scorer())
    assert card.passed, [r.name for r in card.failures]
    assert card.meta["pairs"] == 4


def test_separation_fails_when_ranking_inverts():
    card = ats_sanity.run(_pairs(), _scorer(invert=True))
    assert not card.passed
    assert "strong_vs_weak_separation" in [r.name for r in card.failures]


def test_monotonicity_fails_when_adding_a_required_skill_lowers_the_score():
    card = ats_sanity.run(_pairs(), _scorer(resume_penalty=3.0))
    check = _by_name(card)["skill_monotonicity"]
    assert not check.passed
    assert check.value == pytest.approx(3.0)
    assert any("docker" in s for s in check.samples)


def test_semantic_channel_check_catches_the_keyword_only_fallback():
    card = ats_sanity.run(_pairs(), _scorer(semantic_weight=0.0))
    check = _by_name(card)["semantic_channel_live"]
    assert not check.passed
    assert check.value == 4.0
    assert not card.passed


def test_bounds_check_catches_a_composite_that_stopped_matching_its_parts():
    card = ats_sanity.run(_pairs(), _scorer(broken=True))
    check = _by_name(card)["score_bounds"]
    assert not check.passed
    assert "composite" in check.samples[0]


def test_related_margin_passes_when_the_wrong_role_stays_well_behind():
    pairs, score_fn = _related_scenario(50.0)
    check = _by_name(ats_sanity.run(pairs, score_fn))["strong_vs_related_margin"]
    assert check.gating
    assert check.value == pytest.approx(20.0)
    assert check.passed


def test_related_margin_fails_when_a_wrong_role_scores_almost_as_well():
    pairs, score_fn = _related_scenario(62.0)
    card = ats_sanity.run(pairs, score_fn)
    check = _by_name(card)["strong_vs_related_margin"]
    assert check.value == pytest.approx(8.0)
    assert not check.passed
    assert not card.passed


def test_order_invariance_tolerates_drift_inside_the_calibrated_bar():
    card = ats_sanity.run(_pairs(), _scorer(jd_penalty=3.0))
    order = _by_name(card)["jd_order_invariance"]
    assert order.value == pytest.approx(3.0)
    assert order.passed
    assert card.passed


def test_order_invariance_fails_once_drift_clears_the_bar():
    card = ats_sanity.run(_pairs(), _scorer(jd_penalty=10.0))
    order = _by_name(card)["jd_order_invariance"]
    boilerplate = _by_name(card)["boilerplate_invariance"]
    assert order.value == pytest.approx(10.0)
    assert order.gating
    assert not order.passed
    assert not card.passed
    # Boilerplate drift is real, but it traces to a known gap in the scorer rather
    # than to model noise, so it is reported without failing the run until that gap
    # closes. Widening the bar to swallow it would hide the defect it found.
    assert boilerplate.value == pytest.approx(10.0)
    assert not boilerplate.gating
