"""Properties the hybrid ATS scorer must hold, measured over the labeled corpus."""

from __future__ import annotations

import random
import re
from collections.abc import Callable, Sequence
from typing import Any

from evals.corpus import Pair, load_ats_pairs
from evals.scorecard import CheckResult, Scorecard

SUITE = "ats-sanity"

# Points a strong match must clear its own resume's best weak match by. A scorer
# that cannot do this is not ranking, it is guessing.
SEPARATION_MARGIN = 5.0
# Points a score may fall when a skill the JD asks for is ADDED to the resume.
MONOTONICITY_TOLERANCE = 0.5
# Points a score may move under an edit that changes presentation, not content.
INVARIANCE_TOLERANCE = 2.0
# Rounding slack when re-deriving the composite from its weighted parts.
COMPOSITE_TOLERANCE = 0.15
# Fixed so a rerun measures the model rather than a different shuffle.
SHUFFLE_SEED = 20260820
# Priority skills probed per pair in the monotonicity check.
MAX_SKILL_PROBES = 3
# Weight the composite gives the semantic channel when the model is healthy.
EXPECTED_SEMANTIC_WEIGHT = 0.50

BOILERPLATE_BLOCK = (
    "We are an equal opportunity employer. All qualified applicants will receive "
    "consideration for employment without regard to race, color, religion, sex, "
    "national origin, disability, or veteran status. We offer a competitive salary, "
    "comprehensive benefits, medical, dental and vision insurance, 401(k) matching, "
    "paid time off, parental leave, and tuition reimbursement. This is a drug-free "
    "workplace."
)

ScoreFn = Callable[[str, str], Any]


def _default_score_fn() -> ScoreFn:
    from app.services.ats_scorer import calculate_ats_score  # lazy — pulls in torch

    return calculate_ats_score


def _add_skill(resume_text: str, skill: str) -> str:
    """Append one skill to the resume's existing SKILLS line, or add a line if absent.

    Editing the existing line keeps the perturbation to a single variable: adding a
    section header instead would also move the structure component, and then a score
    change would not be attributable to the skill.
    """
    lines = resume_text.split("\n")
    for i, line in enumerate(lines):
        if re.fullmatch(r"\s*SKILLS\s*", line, flags=re.IGNORECASE) and i + 1 < len(lines):
            lines[i + 1] = f"{lines[i + 1].rstrip()}, {skill}"
            return "\n".join(lines)
    return f"{resume_text}\n{skill}"


def _shuffle_lines(text: str, seed: int) -> str:
    """Reorder a JD's non-empty lines — same content, different presentation."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    random.Random(seed).shuffle(lines)
    return "\n".join(lines)


def _group_by_resume(pairs: Sequence[Pair]) -> dict[str, list[Pair]]:
    grouped: dict[str, list[Pair]] = {}
    for pair in pairs:
        grouped.setdefault(pair.resume_id, []).append(pair)
    return grouped


def _margin_check(
    pairs: Sequence[Pair],
    base: dict[str, Any],
    better: str,
    worse: str,
    name: str,
    gating: bool,
) -> CheckResult:
    """Smallest gap, across resumes, between the worst `better` and best `worse` match."""
    margins: list[tuple[float, str]] = []
    for resume_id, group in _group_by_resume(pairs).items():
        highs = [base[p.label].score for p in group if p.relation == better]
        lows = [base[p.label].score for p in group if p.relation == worse]
        if not highs or not lows:
            continue
        margins.append((round(min(highs) - max(lows), 1), resume_id))

    if not margins:
        # Nothing to measure — report a bar of zero so the row cannot be misread
        # as a margin that came out at zero.
        return CheckResult(
            name=name,
            value=0.0,
            threshold=0.0,
            direction="min",
            unit="points",
            detail=f"not applicable: no resume pairs a {better} match with a {worse} one",
            gating=False,
        )

    margins.sort()
    worst_value, worst_resume = margins[0]
    return CheckResult(
        name=name,
        value=worst_value,
        threshold=SEPARATION_MARGIN,
        direction="min",
        unit="points",
        detail=(
            f"tightest gap between a {better} and a {worse} match is {worst_value:g} points "
            f"({worst_resume}); mean across resumes {sum(m for m, _ in margins) / len(margins):.1f}"
        ),
        samples=[f"{resume}: {value:g} points" for value, resume in margins[:3]],
        gating=gating,
    )


def _check_monotonicity(
    pairs: Sequence[Pair], base: dict[str, Any], score_fn: ScoreFn
) -> CheckResult:
    """Adding a skill the JD asks for must never lower the score."""
    from app.services.ats_scorer import PRIORITY_KEYWORDS

    worst_drop = 0.0
    samples: list[str] = []
    for pair in pairs:
        result = base[pair.label]
        probes = [k for k in result.missing_keywords if k in PRIORITY_KEYWORDS][:MAX_SKILL_PROBES]
        for skill in probes:
            after = score_fn(_add_skill(pair.resume_text, skill), pair.job_text)
            drop = round(result.score - after.score, 2)
            if drop > MONOTONICITY_TOLERANCE:
                samples.append(
                    f"{pair.label}: adding '{skill}' moved {result.score:g} -> {after.score:g}"
                )
            worst_drop = max(worst_drop, drop)

    return CheckResult(
        name="skill_monotonicity",
        value=worst_drop,
        threshold=MONOTONICITY_TOLERANCE,
        direction="max",
        unit="points",
        detail=(
            f"largest score drop caused by adding a required skill: {worst_drop:g} points "
            f"({len(samples)} regression{'s' if len(samples) != 1 else ''} over the corpus)"
        ),
        samples=samples,
    )


def _perturbation_check(
    pairs: Sequence[Pair],
    base: dict[str, Any],
    score_fn: ScoreFn,
    perturb: Callable[[Pair], str],
    name: str,
    description: str,
) -> CheckResult:
    """Largest score movement under a JD edit that preserves meaning."""
    worst = 0.0
    samples: list[str] = []
    for pair in pairs:
        before = base[pair.label].score
        after = score_fn(pair.resume_text, perturb(pair)).score
        delta = round(abs(before - after), 2)
        if delta > INVARIANCE_TOLERANCE:
            samples.append(f"{pair.label}: {before:g} -> {after:g} ({delta:g} points)")
        worst = max(worst, delta)

    return CheckResult(
        name=name,
        value=worst,
        threshold=INVARIANCE_TOLERANCE,
        direction="max",
        unit="points",
        detail=f"largest movement when {description}: {worst:g} points",
        samples=samples,
        # Advisory until the first full run supplies a measured baseline: the
        # semantic channel is order-sensitive by design, so the honest threshold
        # is one calibrated from observed drift, not one guessed up front.
        gating=False,
    )


def _check_semantic_channel(pairs: Sequence[Pair], base: dict[str, Any]) -> CheckResult:
    """The scorer renormalises its weights when the embedding model is unavailable.

    That degradation is deliberate and invisible: the composite still looks plausible
    while half the signal is gone. Any pair not carrying the full semantic weight means
    the run measured a crippled scorer, so the whole scorecard is suspect.
    """
    degraded = [
        p.label
        for p in pairs
        if base[p.label].breakdown.get("semantic_weight") != EXPECTED_SEMANTIC_WEIGHT
    ]
    return CheckResult(
        name="semantic_channel_live",
        value=float(len(degraded)),
        threshold=0.0,
        direction="max",
        unit="pairs",
        detail=(
            "every pair scored with the semantic channel at full weight"
            if not degraded
            else f"{len(degraded)} pair(s) fell back to keyword-only scoring — model not loaded"
        ),
        samples=degraded,
    )


def _check_bounds(pairs: Sequence[Pair], base: dict[str, Any]) -> CheckResult:
    """Sub-scores stay in range and the composite still equals its weighted parts."""
    violations: list[str] = []
    for pair in pairs:
        r = base[pair.label]
        for field_name in ("score", "semantic_score", "keyword_score", "structure_score"):
            value = getattr(r, field_name)
            if not 0.0 <= value <= 100.0:
                violations.append(f"{pair.label}: {field_name}={value:g} outside [0, 100]")

        b = r.breakdown
        expected = (
            r.semantic_score * b["semantic_weight"]
            + r.keyword_score * b["keyword_weight"]
            + r.structure_score * b["structure_weight"]
        )
        if abs(expected - r.score) > COMPOSITE_TOLERANCE:
            violations.append(f"{pair.label}: composite {r.score:g} != weighted {expected:.2f}")

    return CheckResult(
        name="score_bounds",
        value=float(len(violations)),
        threshold=0.0,
        direction="max",
        unit="violations",
        detail=(
            "all scores in range and consistent with their weights"
            if not violations
            else f"{len(violations)} arithmetic or range violation(s)"
        ),
        samples=violations,
    )


def run(pairs: Sequence[Pair] | None = None, score_fn: ScoreFn | None = None) -> Scorecard:
    """Score the corpus once, then measure every property off those results."""
    pairs = tuple(pairs) if pairs is not None else load_ats_pairs()
    score_fn = score_fn or _default_score_fn()

    base = {p.label: score_fn(p.resume_text, p.job_text) for p in pairs}

    results = [
        _margin_check(pairs, base, "strong", "weak", "strong_vs_weak_separation", gating=True),
        _margin_check(pairs, base, "strong", "related", "strong_vs_related_margin", gating=False),
        _check_monotonicity(pairs, base, score_fn),
        _perturbation_check(
            pairs,
            base,
            score_fn,
            lambda p: _shuffle_lines(p.job_text, SHUFFLE_SEED),
            "jd_order_invariance",
            "the JD's lines are reordered",
        ),
        _perturbation_check(
            pairs,
            base,
            score_fn,
            lambda p: f"{p.job_text}\n{BOILERPLATE_BLOCK}",
            "boilerplate_invariance",
            "an EEO and benefits block is appended to the JD",
        ),
        _check_semantic_channel(pairs, base),
        _check_bounds(pairs, base),
    ]

    model = next(iter(base.values())).breakdown.get("model", "unknown")
    return Scorecard(
        suite=SUITE,
        results=results,
        meta={"pairs": len(pairs), "model": model, "shuffle_seed": SHUFFLE_SEED},
    )
