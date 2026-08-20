"""Small statistics helpers — kept dependency-free so evals run without the ML stack."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def agreement_rate(a: Sequence[object], b: Sequence[object]) -> float:
    """Fraction of positions where two label sequences agree."""
    if len(a) != len(b):
        raise ValueError(f"label sequences differ in length: {len(a)} vs {len(b)}")
    if not a:
        return 0.0
    return sum(1 for x, y in zip(a, b, strict=True) if x == y) / len(a)


def cohen_kappa(a: Sequence[object], b: Sequence[object]) -> float:
    """Chance-corrected agreement between two raters over the same items.

    Raw agreement flatters any rater on a skewed label set — two raters who both
    always answer "pass" agree 100% of the time while measuring nothing. Kappa
    subtracts the agreement you would expect from their marginal rates alone.
    """
    if len(a) != len(b):
        raise ValueError(f"label sequences differ in length: {len(a)} vs {len(b)}")
    if not a:
        return 0.0

    observed = agreement_rate(a, b)
    n = len(a)
    counts_a, counts_b = Counter(a), Counter(b)
    expected = sum(
        (counts_a[label] / n) * (counts_b[label] / n) for label in counts_a.keys() | counts_b.keys()
    )

    if expected == 1.0:
        # Both raters used exactly one label for everything: agreement is total but
        # carries no information, so kappa is undefined. Report the honest 0.
        return 0.0
    return (observed - expected) / (1 - expected)
