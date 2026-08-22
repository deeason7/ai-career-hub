"""Command-line entry point for the eval suites."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals import ats_sanity

SUITES = {ats_sanity.SUITE: ats_sanity.run}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m evals.runner",
        description="Run an evaluation suite and print its scorecard.",
    )
    parser.add_argument("--suite", choices=sorted(SUITES), default=ats_sanity.SUITE)
    parser.add_argument(
        "--json", type=Path, metavar="PATH", help="also write the scorecard as JSON"
    )
    parser.add_argument(
        "--no-fail",
        action="store_true",
        help="report but always exit 0 (for exploratory runs)",
    )
    args = parser.parse_args(argv)

    card = SUITES[args.suite]()
    print(card.to_markdown())

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(card.to_json(), encoding="utf-8")
        print(f"\nscorecard written to {args.json}", file=sys.stderr)

    if card.failures:
        names = ", ".join(r.name for r in card.failures)
        print(f"\nFAILED gating checks: {names}", file=sys.stderr)

    return 0 if (card.passed or args.no_fail) else 1


if __name__ == "__main__":
    raise SystemExit(main())
