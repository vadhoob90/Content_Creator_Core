#!/usr/bin/env python3
"""Enforce independent statement and branch coverage thresholds."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

STATEMENT_MINIMUM = 88.0
BRANCH_MINIMUM = 71.0


@dataclass(frozen=True)
class CoverageMeasure:
    """Represent the independently reported statement and branch percentages."""

    statements: float
    branches: float


def read_measure(path: Path) -> CoverageMeasure:
    """Read statement and branch percentages from a coverage.py JSON report."""
    report: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    totals = report.get("totals", {})
    if not totals.get("num_branches"):
        raise ValueError("coverage report does not contain measured branches")
    try:
        return CoverageMeasure(
            statements=float(totals["percent_statements_covered"]),
            branches=float(totals["percent_branches_covered"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("coverage report does not contain valid coverage totals") from error


def violations(
    measure: CoverageMeasure,
    statement_minimum: float = STATEMENT_MINIMUM,
    branch_minimum: float = BRANCH_MINIMUM,
) -> list[str]:
    """Return failures for each independently missed coverage threshold."""
    failures: list[str] = []
    if measure.statements < statement_minimum:
        failures.append(
            f"statement coverage {measure.statements:.2f}% is below {statement_minimum:.2f}%"
        )
    if measure.branches < branch_minimum:
        failures.append(f"branch coverage {measure.branches:.2f}% is below {branch_minimum:.2f}%")
    return failures


def main() -> int:
    """Render measured coverage and fail when either independent threshold is missed."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="coverage.py JSON report to inspect")
    parser.add_argument("--check", action="store_true", help="fail below either threshold")
    args = parser.parse_args()
    try:
        measure = read_measure(args.report)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        print(f"ERROR: {error}")
        return 1
    failures = violations(measure)
    for failure in failures:
        print(f"ERROR: {failure}")
    print(
        f"Coverage: statements {measure.statements:.2f}% "
        f"(minimum {STATEMENT_MINIMUM:.2f}%); branches {measure.branches:.2f}% "
        f"(minimum {BRANCH_MINIMUM:.2f}%)"
    )
    return 1 if args.check and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
