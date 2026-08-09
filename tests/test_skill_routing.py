from copy import deepcopy
from pathlib import Path

import pytest

from content_creator.skill_routing import (
    load_skill_routing_suite,
    score_skill_routing,
    validate_packaged_skills,
    validate_skill_routing_suite,
    write_skill_routing_report,
)
from content_creator.skill_routing_trials import (
    run_skill_routing_trials,
    skill_routing_result_path,
)


def test_committed_skill_routing_suite_and_packaged_skills_are_valid():
    root = Path(__file__).parents[1]
    suite = load_skill_routing_suite(root / "evals" / "skill-routing.yaml")

    assert validate_skill_routing_suite(suite) == []
    assert validate_packaged_skills(root, suite["instruction_word_budget"]) == []


def test_skill_routing_validation_rejects_duplicates_and_missing_coverage():
    suite = {
        "schema_version": "1.0",
        "instruction_word_budget": 100,
        "cases": [
            {
                "id": "duplicate",
                "category": "positive",
                "prompt": "Create content",
                "expected_activation": True,
                "expected_skill": "content-creator",
            },
            {
                "id": "duplicate",
                "category": "positive",
                "prompt": " create   CONTENT ",
                "expected_activation": False,
            },
        ],
    }

    errors = validate_skill_routing_suite(suite)

    assert "duplicate case id: duplicate" in errors
    assert "contradictory prompt: duplicate" in errors
    assert "missing categories: near-miss, negative" in errors
    assert "missing positive skill coverage: voice-builder" in errors


def test_skill_routing_scoring_reports_wrong_skill_and_false_activation():
    root = Path(__file__).parents[1]
    suite = load_skill_routing_suite(root / "evals" / "skill-routing.yaml")
    observations = []
    for case in suite["cases"]:
        observations.append(
            {
                "case": case["id"],
                "activated": case["expected_activation"],
                "skill": case.get("expected_skill"),
            }
        )
    changed = deepcopy(observations)
    changed[0]["skill"] = "voice-builder"
    negative_index = next(
        index for index, case in enumerate(suite["cases"]) if case["expected_activation"] is False
    )
    changed[negative_index]["activated"] = True
    changed[negative_index]["skill"] = "content-creator"

    report = score_skill_routing(suite, changed)

    assert report["passed"] == report["total"] - 2
    assert report["false_positives"] == 1
    assert report["false_negatives"] == 1
    assert report["precision"] < 1
    assert report["recall"] < 1


def test_skill_routing_scoring_requires_every_case():
    root = Path(__file__).parents[1]
    suite = load_skill_routing_suite(root / "evals" / "skill-routing.yaml")

    with pytest.raises(ValueError, match="Missing observed cases"):
        score_skill_routing(suite, [])


def test_skill_routing_suite_rejects_invalid_document_and_case_shapes(tmp_path):
    invalid_document = tmp_path / "invalid.yaml"
    invalid_document.write_text("- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a mapping"):
        load_skill_routing_suite(invalid_document)

    errors = validate_skill_routing_suite(
        {
            "schema_version": "2.0",
            "instruction_word_budget": True,
            "cases": [
                "not-a-mapping",
                {
                    "id": "",
                    "category": "unknown",
                    "prompt": "",
                    "expected_activation": "yes",
                },
                {
                    "id": "negative-with-skill",
                    "category": "negative",
                    "prompt": "Do not route",
                    "expected_activation": False,
                    "expected_skill": "content-creator",
                },
            ],
        }
    )

    assert "schema_version must be 1.0" in errors
    assert "instruction_word_budget must be a positive integer" in errors
    assert "case 0 must be a mapping" in errors
    assert "case 1 requires a non-empty id" in errors
    assert "case 1 requires a non-empty prompt" in errors
    assert "case 1 has invalid category" in errors
    assert "case 1 requires boolean expected_activation" in errors
    assert "case negative-with-skill must omit expected_skill" in errors


def test_skill_routing_suite_requires_cases_and_detects_identical_prompts():
    assert validate_skill_routing_suite(
        {"schema_version": "1.0", "instruction_word_budget": 1, "cases": []}
    ) == ["cases must be a non-empty list"]
    suite = {
        "schema_version": "1.0",
        "instruction_word_budget": 10,
        "cases": [
            {
                "id": "one",
                "category": "positive",
                "prompt": "same",
                "expected_activation": True,
                "expected_skill": "content-creator",
            },
            {
                "id": "two",
                "category": "positive",
                "prompt": " SAME ",
                "expected_activation": True,
                "expected_skill": "content-creator",
            },
        ],
    }
    assert "duplicate prompt: two" in validate_skill_routing_suite(suite)


def test_packaged_skill_validation_reports_missing_invalid_and_oversized_files(tmp_path):
    assert "content-creator is missing SKILL.md" in validate_packaged_skills(tmp_path, 10)
    for skill in ("content-creator", "voice-builder"):
        development = tmp_path / ".agents" / "skills" / skill
        packaged = tmp_path / "src/content_creator/resources/skills" / skill
        (development / "agents").mkdir(parents=True)
        (packaged / "agents").mkdir(parents=True)
        (development / "SKILL.md").write_text("not frontmatter " * 20, encoding="utf-8")
        (packaged / "SKILL.md").write_text("different", encoding="utf-8")
        (development / "agents/openai.yaml").write_text("agent: true", encoding="utf-8")
        (packaged / "agents/openai.yaml").write_text("agent: true", encoding="utf-8")

    errors = validate_packaged_skills(tmp_path, 10)

    assert "content-creator packaged copy differs: SKILL.md" in errors
    assert "content-creator requires YAML frontmatter" in errors
    assert "content-creator frontmatter name must match its directory" in errors
    assert "content-creator requires a frontmatter description" in errors
    assert "content-creator exceeds the 10-word instruction budget" in errors


def test_skill_routing_scoring_rejects_invalid_observations_and_writes_report(tmp_path):
    root = Path(__file__).parents[1]
    suite = load_skill_routing_suite(root / "evals" / "skill-routing.yaml")
    with pytest.raises(ValueError, match="case id must be a string"):
        score_skill_routing(suite, [{"case": None}])
    with pytest.raises(ValueError, match="Unknown observed case"):
        score_skill_routing(suite, [{"case": "unknown"}])
    case_id = suite["cases"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate observed case"):
        score_skill_routing(suite, [{"case": case_id}, {"case": case_id}])

    output = tmp_path / "reports" / "routing.json"
    write_skill_routing_report(output, {"valid": True})
    assert output.read_text(encoding="utf-8") == '{\n  "valid": true\n}\n'


def test_repeated_skill_routing_trials_record_metrics_failures_and_majorities():
    root = Path(__file__).parents[1]
    suite = load_skill_routing_suite(root / "evals" / "skill-routing.yaml")
    requests = []

    def fake_adapter(_command, request):
        import json

        payload = json.loads(request)
        requests.append(payload)
        case = next(item for item in suite["cases"] if item["id"] == payload["case"])
        activated = case["expected_activation"]
        skill = case.get("expected_skill")
        if payload["case"] == "content-create-linkedin" and payload["trial"] == 1:
            skill = "voice-builder"
        if payload["case"] == "unrelated-code-review" and payload["trial"] == 2:
            activated = True
            skill = "content-creator"
        return json.dumps({"activated": activated, "skill": skill})

    report = run_skill_routing_trials(
        suite,
        "codex-desktop",
        "gpt-test-2026-08",
        ["reviewed-adapter"],
        executor=fake_adapter,
        generated_at="2026-08-09T12:00:00+00:00",
    )

    assert len(requests) == len(suite["cases"]) * 3
    assert report["metrics"]["total_trials"] == 24
    assert report["metrics"]["passed_trials"] == 22
    assert report["metrics"]["false_positives"] == 1
    assert report["metrics"]["false_negatives"] == 1
    assert len(report["failed_prompts"]) == 2
    assert all(case["majority"]["passed"] for case in report["cases"])


@pytest.mark.parametrize("trials", [0, 2, 4])
def test_repeated_skill_routing_trials_require_positive_odd_count(trials):
    root = Path(__file__).parents[1]
    suite = load_skill_routing_suite(root / "evals" / "skill-routing.yaml")

    with pytest.raises(ValueError, match="positive odd integer"):
        run_skill_routing_trials(suite, "host", "model", ["adapter"], trials)


@pytest.mark.parametrize(
    ("output", "message"),
    [
        ("not-json", "must be JSON"),
        ('{"activated": "yes"}', "requires boolean activated"),
        ('{"activated": true}', "require a skill"),
        ('{"activated": false, "skill": "content-creator"}', "must omit skill"),
        ('{"activated": false, "case": "wrong"}', "wrong trial"),
    ],
)
def test_repeated_skill_routing_trials_reject_invalid_adapter_output(output, message):
    suite = {
        "schema_version": "1.0",
        "instruction_word_budget": 10,
        "cases": [
            {
                "id": "positive-content",
                "category": "positive",
                "prompt": "Create content",
                "expected_activation": True,
                "expected_skill": "content-creator",
            },
            {
                "id": "positive-voice",
                "category": "positive",
                "prompt": "Build voice",
                "expected_activation": True,
                "expected_skill": "voice-builder",
            },
            {
                "id": "negative",
                "category": "negative",
                "prompt": "Review code",
                "expected_activation": False,
            },
            {
                "id": "near-miss",
                "category": "near-miss",
                "prompt": "Explain voice",
                "expected_activation": False,
            },
        ],
    }

    with pytest.raises(ValueError, match=message):
        run_skill_routing_trials(
            suite, "host", "model", ["adapter"], executor=lambda _command, _request: output
        )


def test_skill_routing_result_path_groups_sanitized_host_and_model():
    path = skill_routing_result_path(
        Path("reports"), "Codex Desktop", "gpt/test:latest", "2026-08-09T12:00:00+00:00"
    )

    assert path == Path("reports/Codex-Desktop/gpt-test-latest/2026-08-09T120000Z.json")


def test_live_skill_routing_workflow_is_manual_advisory_and_persists_results():
    root = Path(__file__).parents[1]
    workflow = (root / ".github/workflows/skill-routing-live.yml").read_text(encoding="utf-8")

    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "pull_request:" not in workflow
    assert "SKILL_ROUTING_ADAPTER_JSON" in workflow
    assert '--host "${HOST}"' in workflow
    assert '--model-version "${MODEL_VERSION}"' in workflow
    assert '--trials "${TRIALS}"' in workflow
    assert "skill-routing-live-results" in workflow
