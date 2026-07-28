import json

import pytest

from content_creator.perspective_assessment import (
    DIMENSIONS,
    create_blind_comparison,
    record_blind_comparison,
)


def test_blind_comparison_records_author_preference_and_reveals_mapping(project):
    run_dir = project / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "final.md").write_text(
        "Content Creator candidate.",
        encoding="utf-8",
    )
    baseline = project / "ordinary-chat.md"
    baseline.write_text("Ordinary chat baseline.", encoding="utf-8")

    packet = create_blind_comparison(project, "run-1", baseline)
    template_path = project / packet["assessment_template"]
    assessment = json.loads(template_path.read_text(encoding="utf-8"))
    assessment["preferred_option"] = "A"
    assessment["comments"] = "Option A required less revision."
    for label in ("A", "B"):
        assessment["revision_effort"][label] = 1 if label == "A" else 3
        for dimension in DIMENSIONS:
            assessment["scores"][label][dimension] = 9 if label == "A" else 7
    completed = project / "completed-assessment.json"
    completed.write_text(json.dumps(assessment), encoding="utf-8")

    result = record_blind_comparison(
        project,
        "run-1",
        completed,
    )

    assert result["preferred_system"] in {
        "candidate",
        "ordinary_chat_baseline",
    }
    assert set(result["revealed_mapping"]) == {
        "candidate",
        "ordinary_chat_baseline",
    }
    assert (run_dir / "blind-comparison" / "assessment-result.json").exists()


def test_blind_comparison_rejects_incomplete_scores(project):
    run_dir = project / "runs" / "run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "final.md").write_text("Candidate.", encoding="utf-8")
    baseline = project / "baseline.md"
    baseline.write_text("Baseline.", encoding="utf-8")
    packet = create_blind_comparison(project, "run-1", baseline)
    assessment = json.loads(
        (project / packet["assessment_template"]).read_text(encoding="utf-8")
    )
    assessment["preferred_option"] = "tie"
    completed = project / "incomplete.json"
    completed.write_text(json.dumps(assessment), encoding="utf-8")

    with pytest.raises(ValueError, match="scored from 1 to 10"):
        record_blind_comparison(project, "run-1", completed)
