import json

import pytest
from pydantic import ValidationError

from content_creator.domain import WorkOrder
from content_creator.learning import LearningMemory
from content_creator.orchestrator import OrchestrationError, Orchestrator
from content_creator.packs import PackRegistry
from content_creator.prompting import PromptAssembler
from content_creator.validation import validate_draft
from content_creator.voices import VoiceError, VoiceRegistry, hash_file


def test_linkedin_capabilities_live_in_content_packs(project):
    packs = {pack.id: pack for pack in PackRegistry(project).list()}

    assert packs["linkedin-post"].format == "post"
    assert packs["linkedin-article"].format == "article"
    assert packs["linkedin-post"].destination == "content/linkedin-post/published"
    assert packs["linkedin-post"].statistical_voice_score.eligible is False
    assert packs["linkedin-article"].statistical_voice_score.eligible is True


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


@pytest.mark.parametrize("field", ["content_pack", "voice_id", "perspective_context"])
def test_repository_identifiers_reject_path_traversal(field):
    with pytest.raises(ValidationError, match="Repository ids"):
        WorkOrder(request="write", topic="topic", **{field: "../outside"})


def test_prompt_and_learning_memory_are_scoped_to_selected_voice(project):
    profile = project / "profiles" / "second-voice"
    version = profile / "versions" / "1.0.0"
    (profile / "learnings").mkdir(parents=True)
    version.mkdir(parents=True)
    (version / "profile.md").write_text(
        "# Voice Profile: Second Voice\n\n"
        "| Lifecycle status | Candidate — built, not approved |\n\n"
        "| Approved voice patterns | None |\n\n"
        "> Observations must not be treated as approved writing instructions.\n\n"
        "Use grounded examples.",
        encoding="utf-8",
    )
    (version / "manifest.json").write_text(
        json.dumps(
            {
                "id": "second-voice",
                "display_name": "Second Voice",
                "version": "1.0.0",
                "status": "active",
                "candidate_hash": "sha256:fixture",
                "components": {"profile": "profile.md"},
                "component_hashes": {"profile": hash_file(version / "profile.md")},
                "supported_packs": {"general-text": "medium"},
                "authorisation": {"confirmed": True},
            }
        ),
        encoding="utf-8",
    )
    (project / "profiles" / "registry.json").write_text(
        json.dumps(
            {
                "profiles": {
                    "second-voice": {
                        "status": "active",
                        "active_version": "1.0.0",
                    }
                }
            }
        ),
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
    assert "## Authoritative resolved voice lifecycle" in prompt
    assert "Status: active" in prompt
    assert "Version: 1.0.0" in prompt
    assert "Candidate — built, not approved" not in prompt
    assert "Approved voice patterns | None" not in prompt
    assert "not be treated as approved writing instructions" not in prompt
    assert "Prefer a concrete example." in prompt
    assert "Default Placeholder" not in prompt
    assert LearningMemory(project, "second-voice").path == (profile / "learnings" / "memory.json")

    _mark_manifest_awaiting(version)
    with pytest.raises(VoiceError, match="Voice lifecycle mismatch"):
        VoiceRegistry(project).resolve("second-voice")


def _mark_manifest_awaiting(version):
    manifest_path = version / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "awaiting_approval"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_general_text_resolves_and_forbidden_override_fails(project):
    registry = PackRegistry(project)
    pack = registry.resolve("general-text", {"length": "300:500"})
    assert pack.defaults["length"] == "300:500"

    with pytest.raises(Exception, match="Forbidden pack override"):
        registry.resolve("general-text", {"provider_api_key": "secret"})


def test_child_pack_preserves_integrity_validators(project):
    registry = PackRegistry(project)
    base = registry.resolve("general-text")
    child = registry.resolve("linkedin-post")

    assert set(base.integrity_validators) <= set(child.integrity_validators)


def test_optional_validator_is_applied_only_when_selected(project):
    registry = PackRegistry(project)
    general = registry.resolve("general-text", {"length": "1:20"})
    order = WorkOrder(
        request="write",
        topic="topic",
        content_pack="general-text",
        format="text",
        pack_options={"length": "1:20"},
    )

    assert "Hashtags are not allowed" not in validate_draft(
        "# Heading is valid here", order, general.validators
    )
    assert "Hashtags are not allowed" in validate_draft(
        "#growth is not valid here", order, ["no-hashtags"]
    )
