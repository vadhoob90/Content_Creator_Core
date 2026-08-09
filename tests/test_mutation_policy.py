from datetime import date
from pathlib import Path

from content_creator.mutation_policy import plan_mutation_scope, validate_waivers


def test_changed_critical_module_selects_only_its_mutants():
    plan = plan_mutation_scope(["src/content_creator/quality.py"], "none")

    assert plan.required is True
    assert plan.patterns == ("content_creator.quality.*",)


def test_patch_production_change_selects_regression_risk_set():
    plan = plan_mutation_scope(["src/content_creator/coordinator.py"], "patch")

    assert plan.required is True
    assert set(plan.patterns) == {
        "content_creator.quality.*",
        "content_creator.versioned_artifacts.*",
    }


def test_minor_change_selects_full_set_even_for_documentation():
    plan = plan_mutation_scope(["README.md"], "minor")

    assert plan.required is True
    assert len(plan.patterns) == 2


def test_documentation_only_change_does_not_require_mutation_run():
    plan = plan_mutation_scope(["docs/core/README.md"], "none")

    assert plan.required is False
    assert plan.patterns == ()


def test_waiver_validation_accepts_complete_current_decision(tmp_path: Path):
    waivers = tmp_path / "waivers.yaml"
    waivers.write_text(
        """schema_version: 1
decisions:
  - mutant: content_creator.quality.example__mutmut_1
    classification: equivalent
    rationale: Both branches deliberately return the same public value.
    owner: '@maintainer'
    expires: 2027-01-01
    follow_up: https://github.com/example/project/issues/1
""",
        encoding="utf-8",
    )

    assert validate_waivers(waivers, today=date(2026, 8, 9)) == []


def test_waiver_validation_rejects_expired_and_incomplete_decisions(tmp_path: Path):
    waivers = tmp_path / "waivers.yaml"
    waivers.write_text(
        """schema_version: 1
decisions:
  - mutant: example
    classification: ignored
    rationale: ''
    owner: '@maintainer'
    expires: 2025-01-01
    follow_up: issue-1
""",
        encoding="utf-8",
    )

    errors = validate_waivers(waivers, today=date(2026, 8, 9))

    assert any("classification is invalid" in error for error in errors)
    assert any("expired" in error for error in errors)
    assert any("rationale must be non-empty" in error for error in errors)
