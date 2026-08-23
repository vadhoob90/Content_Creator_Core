import json

import pytest
import yaml

from content_creator.domain import LearningExtraction, WorkOrder
from content_creator.learning import LearningMemory
from content_creator.orchestrator import Orchestrator
from content_creator.perspective_support import PerspectiveEntry, PerspectiveProvenance
from content_creator.perspectives import PerspectiveError, PerspectiveRegistry
from content_creator.voice_upgrade.epochs import epoch_path, load_epoch
from content_creator.voices import VoiceError, VoiceRegistry


def _starter(project, voice_id="author-linkedin"):
    return VoiceRegistry(project).activate_starter(
        voice_id,
        "Author — LinkedIn",
        "Author",
        "Author",
        ["linkedin-post"],
    )


def _default_voice(project, voice_id):
    path = project / "content-creator.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data.setdefault("coordinator", {})["default_voice"] = voice_id
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _perspective(project, context_id="space-law"):
    registry = PerspectiveRegistry(project, "default")
    registry.stage(
        context_id,
        [
            PerspectiveEntry(
                id="space-001",
                statement="Preserve expertise boundaries.",
                provenance=[PerspectiveProvenance(kind="author", reference="review")],
            )
        ],
    )
    registry.activate(context_id, "Author")
    return registry


def test_pause_and_reactivation_receipts_preserve_version_and_rotate_epoch(project):
    _starter(project)
    registry = VoiceRegistry(project)
    original = registry.resolve("author-linkedin")

    paused = registry.deactivate("author-linkedin", "channel pause", "Author")

    assert paused["action"] == "deactivate"
    assert paused["actor"] == "Author"
    assert registry.get("author-linkedin")["status"] == "inactive"
    assert load_epoch(project, "author-linkedin", "1.0.0").status == "frozen"
    with pytest.raises(VoiceError, match="not active"):
        Orchestrator(project).start(
            WorkOrder(request="write", topic="topic", voice_id="author-linkedin")
        )

    resumed = registry.reactivate("author-linkedin", "Author")
    current = registry.resolve("author-linkedin")

    assert resumed["action"] == "reactivate"
    assert current["version"] == original["version"] == "1.0.0"
    assert current["learning_epoch_id"] == "activation-2"
    assert sorted(
        path.name for path in (project / "profiles" / "author-linkedin" / "versions").iterdir()
    ) == ["1.0.0"]
    assert (
        len(
            list(
                (project / "profiles" / "author-linkedin" / "lifecycle" / "receipts").glob("*.json")
            )
        )
        == 2
    )
    assert registry.verify_lifecycle("author-linkedin")["valid"] is True


def test_retirement_requires_default_decision_and_stale_plan_is_rejected(project):
    _starter(project)
    _default_voice(project, "author-linkedin")
    registry = VoiceRegistry(project)
    plan = registry.retirement_plan("author-linkedin")

    with pytest.raises(ValueError, match="default"):
        registry.retire("author-linkedin", "Author", "leaving LinkedIn", plan["binding_hash"])

    memory = epoch_path(project, "author-linkedin", "1.0.0")
    data = json.loads(memory.read_text(encoding="utf-8"))
    data["records"].append(
        {
            "id": "new-learning",
            "role": "writer",
            "principle": "Use concrete openings.",
            "status": "active",
        }
    )
    memory.write_text(json.dumps(data, indent=2), encoding="utf-8")
    with pytest.raises(VoiceError, match="stale"):
        registry.retire(
            "author-linkedin",
            "Author",
            "leaving LinkedIn",
            plan["binding_hash"],
            clear_default=True,
        )

    current = registry.retirement_plan("author-linkedin")
    receipt = registry.retire(
        "author-linkedin",
        "Author",
        "leaving LinkedIn",
        current["binding_hash"],
        clear_default=True,
    )

    assert receipt["resulting_status"] == "retired"
    assert registry.get("author-linkedin")["status"] == "retired"
    assert (
        yaml.safe_load((project / "content-creator.yaml").read_text())["coordinator"][
            "default_voice"
        ]
        is None
    )
    assert load_epoch(project, "author-linkedin", "1.0.0").status == "frozen"
    with pytest.raises(VoiceError, match="not active"):
        LearningMemory(project, "author-linkedin", "1.0.0").apply(
            "historical-run", LearningExtraction(candidates=[])
        )


def test_retired_voice_uses_reviewed_restore_path_and_fresh_epoch(project):
    _starter(project)
    registry = VoiceRegistry(project)
    plan = registry.retirement_plan("author-linkedin")
    registry.retire("author-linkedin", "Author", "leaving channel", plan["binding_hash"])

    with pytest.raises(VoiceError, match="restore path"):
        registry.reactivate("author-linkedin", "Author")
    restore_plan = registry.retirement_plan("author-linkedin")
    receipt = registry.restore(
        "author-linkedin",
        "Author",
        "Reviewer",
        restore_plan["binding_hash"],
    )

    assert receipt["action"] == "restore"
    assert receipt["actor"] == "Reviewer"
    assert registry.resolve("author-linkedin")["version"] == "1.0.0"
    assert registry.resolve("author-linkedin")["learning_epoch_id"] == "activation-2"


def test_perspective_context_lifecycle_and_exact_hash_candidate_decision(project):
    registry = _perspective(project)
    original = registry.resolve("space-law")
    paused = registry.deactivate("space-law", "temporary pause", "Author")
    resumed = registry.reactivate("space-law", "Author")

    assert paused["action"] == "deactivate"
    assert resumed["action"] == "reactivate"
    assert registry.resolve("space-law")["version"] == original["version"]

    registry.retire_entry("space-law", "space-001", "position withdrawn")
    candidate = json.loads(
        (
            project
            / "profiles"
            / "default"
            / "perspectives"
            / "space-law"
            / "candidate"
            / "manifest.json"
        ).read_text()
    )
    decision = registry.decide_candidate(
        "space-law",
        candidate["candidate_hash"],
        "Author",
        "do not activate this change",
    )
    assert decision["action"] == "reject-candidate"
    with pytest.raises(PerspectiveError, match="stale"):
        registry.decide_candidate("space-law", "sha256:stale", "Author", "wrong candidate")

    plan = registry.retirement_plan("space-law")
    retired = registry.retire_context(
        "space-law",
        "Author",
        "context no longer used",
        plan_hash=plan["binding_hash"],
        candidate_disposition="reject",
    )
    assert retired["resulting_status"] == "retired"
    with pytest.raises(PerspectiveError, match="restore path"):
        registry.reactivate("space-law", "Author")
    restore_plan = registry.retirement_plan("space-law")
    restored = registry.restore_context(
        "space-law", "Author", "Reviewer", restore_plan["binding_hash"]
    )
    assert restored["resulting_status"] == "active"
    assert registry.resolve("space-law")["version"] == "1.0.0"
    assert registry.verify_lifecycle("space-law")["valid"] is True
