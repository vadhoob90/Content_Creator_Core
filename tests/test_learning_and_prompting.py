import json

from content_creator.domain import LearningExtraction
from content_creator.learning import LearningMemory
from content_creator.prompting import PromptAssembler


def test_active_learning_enters_prompt_but_provisional_does_not(project):
    memory = {
        "version": 1,
        "records": [
            {
                "id": "a",
                "run_id": "run-a",
                "role": "writer",
                "principle": "Keep concrete openings.",
                "evidence": "Explicit author feedback",
                "status": "active",
                "confidence": 1,
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": "b",
                "run_id": "run-b",
                "role": "writer",
                "principle": "Always use two paragraphs.",
                "evidence": "Inferred once",
                "status": "provisional",
                "confidence": 0.5,
                "created_at": "2026-01-01T00:00:00Z",
            },
        ],
    }
    (project / "profiles" / "default" / "learnings" / "memory.json").write_text(
        json.dumps(memory), encoding="utf-8"
    )
    prompt = PromptAssembler(project).system_prompt("writer")
    assert "Keep concrete openings." in prompt
    assert "Always use two paragraphs." not in prompt


def test_learning_memory_deduplicates_same_role_and_principle(project):
    extraction = LearningExtraction.model_validate(
        {
            "candidates": [
                {
                    "role": "writer",
                    "principle": "Keep concrete openings.",
                    "evidence": "Explicit",
                    "status": "active",
                    "confidence": 1,
                }
            ]
        }
    )
    memory = LearningMemory(project)
    memory.apply("run-1", extraction)
    memory.apply("run-2", extraction)
    saved = json.loads(
        (
            project / "profiles" / "default" / "learnings" / "memory.json"
        ).read_text(encoding="utf-8")
    )
    assert len(saved["records"]) == 1


def test_learning_conflict_is_surfaced_and_consolidation_is_candidate(project):
    memory = LearningMemory(project)
    first = LearningExtraction.model_validate(
        {
            "candidates": [
                {
                    "role": "writer",
                    "principle": "Always begin with a concrete example.",
                    "evidence": "Explicit",
                    "status": "active",
                    "confidence": 1,
                }
            ]
        }
    )
    second = LearningExtraction.model_validate(
        {
            "candidates": [
                {
                    "role": "writer",
                    "principle": "Never begin with a concrete example.",
                    "evidence": "Explicit",
                    "status": "active",
                    "confidence": 1,
                }
            ]
        }
    )
    memory.apply("run-1", first, explicit_feedback="yes")
    memory.apply("run-2", second, explicit_feedback="yes")
    saved = json.loads(memory.path.read_text(encoding="utf-8"))
    assert saved["records"][1]["conflicts_with"]
    candidate = memory.consolidate_candidate()
    assert json.loads(candidate.read_text())["status"] == "candidate"
