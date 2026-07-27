import json

import pytest
from pydantic import ValidationError

from content_creator.domain import WorkOrder
from content_creator.learning import LearningMemory
from content_creator.orchestrator import OrchestrationError, Orchestrator
from content_creator.packs import PackRegistry
from content_creator.prompting import PromptAssembler


def test_linkedin_capabilities_live_in_content_packs(project):
    packs = {pack.id: pack for pack in PackRegistry(project).list()}

    assert packs["linkedin-post"].format == "post"
    assert packs["linkedin-article"].format == "article"
    assert packs["linkedin-post"].destination == "content/linkedin-post/published"


def test_pack_and_format_mismatch_fails_before_a_run_is_created(project):
    orchestrator = Orchestrator(project)

    with pytest.raises(OrchestrationError, match="expects format article"):
        orchestrator.start(
            WorkOrder(
                request="write",
                topic="topic",
                content_pack="linkedin-article",
                format="post",
            )
        )

    assert not list((project / "runs").glob("*/state.json"))


@pytest.mark.parametrize("field", ["content_pack", "voice_id"])
def test_repository_identifiers_reject_path_traversal(field):
    with pytest.raises(ValidationError, match="Repository ids"):
        WorkOrder(request="write", topic="topic", **{field: "../outside"})


def test_prompt_and_learning_memory_are_scoped_to_selected_voice(project):
    profile = project / "profiles" / "second-voice"
    (profile / "learnings").mkdir(parents=True)
    (profile / "voice.md").write_text(
        "# Voice Profile: Second Voice\n\nUse grounded examples.",
        encoding="utf-8",
    )
    (profile / "learnings" / "memory.json").write_text(
        json.dumps(
            {
                "version": 1,
                "records": [
                    {
                        "role": "writer",
                        "principle": "Prefer a concrete example.",
                        "status": "active",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    order = WorkOrder(
        request="write",
        topic="topic",
        voice_id="second-voice",
    )
    prompt = PromptAssembler(project).system_prompt("writer", order)

    assert "Second Voice" in prompt
    assert "Prefer a concrete example." in prompt
    assert "Default Placeholder" not in prompt
    assert LearningMemory(project, "second-voice").path == (
        profile / "learnings" / "memory.json"
    )
