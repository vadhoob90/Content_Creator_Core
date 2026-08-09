import json
import runpy
from datetime import date
from pathlib import Path

from content_creator.mutation_policy import plan_mutation_scope, validate_waivers

ROOT = Path(__file__).resolve().parents[1]
MUTATION_SCRIPT = runpy.run_path(str(ROOT / "scripts" / "mutation_policy.py"))


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


def test_mutation_policy_script_writes_plan_and_github_outputs(tmp_path: Path, capsys):
    changed = tmp_path / "changed.txt"
    changed.write_text("src/content_creator/coordinator.py\n", encoding="utf-8")
    output = tmp_path / "github-output.txt"

    result = MUTATION_SCRIPT["main"](
        [
            "--impact",
            "patch",
            "--changed-files",
            str(changed),
            "--waivers",
            str(ROOT / ".github" / "mutation-waivers.yaml"),
            "--github-output",
            str(output),
        ]
    )

    report = json.loads(capsys.readouterr().out)
    assert result == 0
    assert report["required"] is True
    assert "content_creator.quality.*" in report["patterns"]
    assert "required=true" in output.read_text(encoding="utf-8")


def test_mutation_policy_script_reads_release_impact_from_event(tmp_path: Path, capsys):
    event = tmp_path / "event.json"
    event.write_text(
        json.dumps({"pull_request": {"labels": [{"name": "release:minor"}]}}),
        encoding="utf-8",
    )

    result = MUTATION_SCRIPT["main"](
        [
            "--event",
            str(event),
            "--waivers",
            str(ROOT / ".github" / "mutation-waivers.yaml"),
        ]
    )

    assert result == 0
    assert json.loads(capsys.readouterr().out)["impact"] == "minor"


def test_mutation_policy_script_rejects_invalid_waiver_file(tmp_path: Path, capsys):
    waivers = tmp_path / "waivers.yaml"
    waivers.write_text("schema_version: 2\ndecisions: []\n", encoding="utf-8")

    result = MUTATION_SCRIPT["main"](["--waivers", str(waivers)])

    assert result == 1
    assert "schema_version must be 1" in capsys.readouterr().out
