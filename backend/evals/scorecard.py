"""Scorecard types shared by every eval suite."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

Direction = Literal["min", "max"]

MAX_SAMPLES = 3


@dataclass(frozen=True)
class CheckResult:
    """One measured property of the system under evaluation."""

    name: str
    value: float
    threshold: float
    direction: Direction
    unit: str
    detail: str
    samples: list[str] = field(default_factory=list)
    # Advisory checks are measured and reported but never fail the suite. Use them
    # for properties worth watching that the system is not yet expected to hold.
    gating: bool = True

    def __post_init__(self) -> None:
        # A typo'd direction would silently invert a check's meaning, which is the
        # worst failure a test harness can have — refuse to construct one.
        if self.direction not in ("min", "max"):
            raise ValueError(f"direction must be 'min' or 'max', got {self.direction!r}")

    @property
    def passed(self) -> bool:
        if self.direction == "min":
            return self.value >= self.threshold
        return self.value <= self.threshold

    @property
    def bar(self) -> str:
        return f"{'>=' if self.direction == 'min' else '<='} {self.threshold:g} {self.unit}"


@dataclass
class Scorecard:
    """The result of one eval suite run."""

    suite: str
    results: list[CheckResult]
    meta: dict = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(r.passed for r in self.results if r.gating)

    @property
    def failures(self) -> list[CheckResult]:
        return [r for r in self.results if r.gating and not r.passed]

    def to_dict(self) -> dict:
        return {
            "suite": self.suite,
            "passed": self.passed,
            "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "meta": self.meta,
            "checks": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "gating": r.gating,
                    "value": r.value,
                    "threshold": r.threshold,
                    "direction": r.direction,
                    "unit": r.unit,
                    "detail": r.detail,
                    "samples": r.samples[:MAX_SAMPLES],
                }
                for r in self.results
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_markdown(self) -> str:
        verdict = "PASS" if self.passed else "FAIL"
        lines = [
            f"### {self.suite} — {verdict}",
            "",
            "| | check | measured | bar |",
            "|---|---|---|---|",
        ]
        for r in self.results:
            if not r.gating:
                mark = "·"
            elif r.passed:
                mark = "✓"
            else:
                mark = "✗"
            lines.append(f"| {mark} | {r.name} | {r.value:g} {r.unit} | {r.bar} |")

        lines.append("")
        for r in self.results:
            lines.append(f"- **{r.name}** — {r.detail}")
            for sample in r.samples[:MAX_SAMPLES]:
                lines.append(f"  - {sample}")

        if self.meta:
            lines += [
                "",
                "<sub>" + " · ".join(f"{k}: {v}" for k, v in self.meta.items()) + "</sub>",
            ]
        return "\n".join(lines)
