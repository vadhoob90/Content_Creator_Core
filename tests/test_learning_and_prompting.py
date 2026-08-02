import json

import pytest
from pydantic import ValidationError

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


def test_repository_and_voice_learnings_are_composed_separately(project):
    repository_memory = {
        "version": 1,
        "records": [
            {
                "id": "repository-a",
                "run_id": "run-a",
                "role": "writer",
                "principle": "State the governing context early.",
                "evidence": "Repository owner instruction",
                "status": "active",
                "confidence": 1,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    voice_memory = {
        "version": 1,
        "records": [
            {
                "id": "voice-a",
                "run_id": "run-b",
                "role": "writer",
                "principle": "Prefer a restrained conclusion.",
                "evidence": "Author instruction",
                "status": "active",
                "confidence": 1,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    (project / "learnings" / "memory.json").write_text(
        json.dumps(repository_memory), encoding="utf-8"
    )
    (project / "profiles" / "default" / "learnings" / "memory.json").write_text(
        json.dumps(voice_memory), encoding="utf-8"
    )

    prompt = PromptAssembler(project).system_prompt("writer")

    assert "## Active repository learnings" in prompt
    assert "State the governing context early." in prompt
    assert "## Active voice learnings" in prompt
    assert "Prefer a restrained conclusion." in prompt


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
        (project / "profiles" / "default" / "learnings" / "memory.json").read_text(encoding="utf-8")
    )
    assert len(saved["records"]) == 1


def test_learning_candidate_rejects_unsupported_role():
    with pytest.raises(ValidationError, match="Unsupported learning role 'author'"):
        LearningExtraction.model_validate(
            {
                "candidates": [
                    {
                        "role": "author",
                        "principle": "Treat a subject position as a voice rule.",
                        "evidence": "Publication",
                        "status": "active",
                        "confidence": 1,
                    }
                ]
            }
        )


def test_legacy_unsupported_active_role_requires_author_review(project):
    memory = {
        "version": 1,
        "records": [
            {
                "id": "legacy-author-learning",
                "run_id": "legacy-run",
                "role": "author",
                "principle": "An inert legacy principle.",
                "evidence": "Legacy extraction",
                "status": "active",
                "confidence": 1,
                "created_at": "2026-01-01T00:00:00Z",
            }
        ],
    }
    path = project / "profiles" / "default" / "learnings" / "memory.json"
    path.write_text(json.dumps(memory), encoding="utf-8")

    with pytest.raises(ValueError, match=r"legacy-author-learning \(author\)"):
        PromptAssembler(project).system_prompt("writer")


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
