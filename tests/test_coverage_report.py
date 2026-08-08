import json
import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
COVERAGE_REPORT = runpy.run_path(str(ROOT / "scripts" / "coverage_report.py"))
CoverageMeasure = COVERAGE_REPORT["CoverageMeasure"]


def test_coverage_harness_accepts_each_threshold_at_its_boundary():
    measure = CoverageMeasure(statements=88.0, branches=80.0)

    assert COVERAGE_REPORT["violations"](measure) == []


@pytest.mark.parametrize(
    ("measure", "expected"),
    [
        (CoverageMeasure(statements=87.99, branches=80.0), "statement coverage"),
        (CoverageMeasure(statements=88.0, branches=79.99), "branch coverage"),
    ],
)
def test_coverage_harness_rejects_each_threshold_independently(measure, expected):
    failures = COVERAGE_REPORT["violations"](measure)

    assert len(failures) == 1
    assert expected in failures[0]


def test_coverage_harness_reads_coverage_json(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "num_branches": 10,
                    "percent_statements_covered": 91.25,
                    "percent_branches_covered": 72.5,
                }
            }
        ),
        encoding="utf-8",
    )

    assert COVERAGE_REPORT["read_measure"](report) == CoverageMeasure(
        statements=91.25,
        branches=72.5,
    )


def test_coverage_harness_rejects_report_without_branch_measurement(tmp_path):
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "totals": {
                    "num_branches": 0,
                    "percent_statements_covered": 100.0,
                    "percent_branches_covered": 100.0,
                }
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="does not contain measured branches"):
        COVERAGE_REPORT["read_measure"](report)
