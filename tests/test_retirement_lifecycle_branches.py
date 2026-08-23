import json
import shutil
from types import SimpleNamespace

import pytest

from content_creator.lifecycle_models import LifecycleDisposition, LifecycleReceipt
from content_creator.lifecycle_support import (
    AtomicArtifactTransaction,
    append_catalogue_receipt,
    default_voice,
    receipt_path_for,
    updated_default_configuration,
    validate_decision_text,
    verify_receipts,
    version_catalogue,
    voice_withdrawal_updates,
)
from content_creator.perspective_context_lifecycle import PerspectiveContextLifecycleService
from content_creator.perspective_support import (
    PerspectiveEntry,
    PerspectiveError,
    PerspectiveProvenance,
)
from content_creator.perspectives import PerspectiveRegistry
from content_creator.storage import RunStore
from content_creator.voice_lifecycle import VoiceLifecycleService, VoiceTransition
from content_creator.voice_upgrade.epochs import load_epoch
from content_creator.voices import VoiceError, VoiceRegistry


def _starter(project, voice_id="author-linkedin"):
    return VoiceRegistry(project).activate_starter(
        voice_id,
        "Author — LinkedIn",
        "Author",
        "Author",
        ["linkedin-post"],
    )


def _context(project, voice_id, context_id):
    registry = PerspectiveRegistry(project, voice_id)
    registry.stage(
        context_id,
        [
            PerspectiveEntry(
                id=f"{context_id}-001",
                statement="Preserve expertise boundaries.",
                provenance=[PerspectiveProvenance(kind="author", reference="review")],
            )
        ],
    )
    registry.activate(context_id, "Author")
    return registry


def _receipt(object_id="author-linkedin"):
    return LifecycleReceipt(
        object_type="voice",
        object_id=object_id,
        action="retire",
        actor="Author",
        reason="retired",
        decided_at="2026-08-23T12:00:00+00:00",
        prior_status="active",
        resulting_status="retired",
        prior_registry_hash="sha256:before",
        resulting_registry_hash="sha256:after",
    )


def test_support_validates_decisions_defaults_and_compensates_transactions(project, monkeypatch):
    with pytest.raises(ValueError, match="actor"):
        validate_decision_text(" ", "reason")
    with pytest.raises(ValueError, match="reason"):
        validate_decision_text("Author", " ")

    empty = project / "empty"
    empty.mkdir()
    assert default_voice(empty) is None
    assert updated_default_configuration(project, "not-default", None, False) is None
    configuration = project / "content-creator.yaml"
    configuration.write_text("coordinator:\n  default_voice: author-linkedin\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clear-default"):
        updated_default_configuration(project, "author-linkedin", None, False)
    with pytest.raises(ValueError, match="own default"):
        updated_default_configuration(project, "author-linkedin", "author-linkedin", False)
    assert "default_voice: replacement" in updated_default_configuration(
        project, "author-linkedin", "replacement", False
    )

    existing = project / "existing.txt"
    created = project / "created.txt"
    failing = project / "failing.txt"
    existing.write_text("before", encoding="utf-8")
    original = RunStore._atomic_text

    def fail_last(path, content):
        if path == failing:
            raise OSError("simulated failure")
        original(path, content)

    monkeypatch.setattr(RunStore, "_atomic_text", staticmethod(fail_last))
    with pytest.raises(OSError, match="simulated"):
        AtomicArtifactTransaction(
            [(existing, "after"), (created, "new"), (failing, "never")]
        ).commit()
    assert existing.read_text(encoding="utf-8").strip() == "before"
    assert not created.exists()


def test_support_builds_disposition_run_catalogue_and_verification_updates(project):
    _starter(project)
    run_path = project / "runs" / "run-open" / "state.json"
    run_path.parent.mkdir(parents=True)
    run_path.write_text(json.dumps({"status": "drafting"}), encoding="utf-8")
    receipt = _receipt()
    epoch = load_epoch(project, "author-linkedin", "1.0.0", migrate_legacy=True)
    transition = SimpleNamespace(
        dispositions=[
            LifecycleDisposition(
                kind="voice-candidate",
                stable_id="author-linkedin",
                artifact_hash="sha256:" + "1" * 64,
                action="retain",
            ),
            LifecycleDisposition(
                kind="perspective-candidate",
                stable_id="context",
                artifact_hash="sha256:" + "2" * 64,
                action="reject",
            ),
        ],
        run_disposition="abandon",
        affected_runs=["run-open"],
        actor="Author",
        reason="retired",
    )
    evidence = SimpleNamespace(epoch=epoch, version="1.0.0")
    updates = voice_withdrawal_updates(
        project,
        project / "profiles" / "author-linkedin",
        receipt,
        transition,
        evidence,
        None,
        "coordinator: {}\n",
    )
    assert any("candidate-decisions" in str(path) for path, _ in updates)
    assert any('"status": "abandoned"' in text for path, text in updates if path == run_path)

    version_one = project / "profiles" / "author-linkedin" / "versions" / "1.0.0"
    version_two = version_one.parent / "2.0.0"
    shutil.copytree(version_one, version_two)
    manifest_path = version_two / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["version"] = "2.0.0"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    catalogue = version_catalogue(project, "author-linkedin", "2.0.0")
    assert catalogue.records[0].successor_version == "2.0.0"
    append_catalogue_receipt(catalogue, "missing", "historical", "missing.json")
    append_catalogue_receipt(catalogue, "2.0.0", "selected", "receipt.json")
    append_catalogue_receipt(catalogue, "2.0.0", "selected", "receipt.json", epoch)
    assert catalogue.records[1].lifecycle_receipts == ["receipt.json"]

    invalid_base = project / "invalid"
    invalid_path = invalid_base / "lifecycle" / "receipts" / "broken.json"
    invalid_path.parent.mkdir(parents=True)
    invalid_path.write_text("not-json", encoding="utf-8")
    result = verify_receipts(project, [invalid_base])
    assert result.valid is False

    no_version_base = project / "no-version"
    valid_path = receipt_path_for(no_version_base, receipt)
    valid_path.parent.mkdir(parents=True)
    valid_path.write_text(receipt.model_dump_json(indent=2), encoding="utf-8")
    assert verify_receipts(project, [no_version_base]).valid is True
    valid_path.write_text(valid_path.read_text().replace("retired", "withdrawn"), encoding="utf-8")
    assert verify_receipts(project, [no_version_base]).valid is False


def test_voice_retirement_inventory_requires_every_pending_disposition(project):
    _starter(project)
    voice_root = project / "profiles" / "author-linkedin"
    shutil.copytree(voice_root / "versions" / "1.0.0", voice_root / "candidate")
    candidate_path = voice_root / "candidate" / "manifest.json"
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    candidate["status"] = "awaiting_approval"
    candidate["candidate_hash"] = "sha256:" + "1" * 64
    candidate_path.write_text(json.dumps(candidate, indent=2), encoding="utf-8")

    perspectives = _context(project, "author-linkedin", "space-law")
    perspectives.retire_entry("space-law", "space-law-001", "changed position")
    proposal = (
        project
        / "profiles"
        / "author-linkedin"
        / "perspectives"
        / "space-law"
        / "proposals"
        / "proposal-open.json"
    )
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(
        json.dumps({"id": "proposal-open", "status": "candidate"}), encoding="utf-8"
    )
    run = project / "runs" / "run-open" / "state.json"
    run.parent.mkdir(parents=True)
    run.write_text(
        json.dumps(
            {
                "status": "drafting",
                "work_order": {"voice_id": "author-linkedin", "voice_version": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )

    registry = VoiceRegistry(project)
    plan = registry.retirement_plan("author-linkedin")
    with pytest.raises(VoiceError, match="voice candidates"):
        registry.retire("author-linkedin", "Author", "retired", plan["binding_hash"])
    with pytest.raises(VoiceError, match="perspective candidates"):
        registry.retire(
            "author-linkedin",
            "Author",
            "retired",
            plan["binding_hash"],
            candidate_disposition="retain",
        )
    with pytest.raises(VoiceError, match="proposals"):
        registry.retire(
            "author-linkedin",
            "Author",
            "retired",
            plan["binding_hash"],
            candidate_disposition="retain",
            perspective_candidate_disposition="retain",
        )
    with pytest.raises(VoiceError, match="Incomplete runs"):
        registry.retire(
            "author-linkedin",
            "Author",
            "retired",
            plan["binding_hash"],
            candidate_disposition="retain",
            perspective_candidate_disposition="retain",
            proposal_disposition="retain",
        )
    receipt = registry.retire(
        "author-linkedin",
        "Author",
        "retired",
        plan["binding_hash"],
        candidate_disposition="reject",
        perspective_candidate_disposition="abandon",
        proposal_disposition="reject",
        run_disposition="abandon",
    )
    assert len(receipt["candidate_dispositions"]) == 3
    assert json.loads(run.read_text(encoding="utf-8"))["status"] == "abandoned"


def test_voice_and_context_lifecycle_reject_invalid_states_and_migrate_legacy(project):
    _starter(project)
    voices = VoiceRegistry(project)
    service = VoiceLifecycleService(voices)
    with pytest.raises(VoiceError, match="inactive"):
        voices.reactivate("author-linkedin", "Author")
    active_plan = voices.retirement_plan("author-linkedin")
    with pytest.raises(VoiceError, match="retired"):
        voices.restore("author-linkedin", "Author", "Reviewer", active_plan["binding_hash"])
    with pytest.raises(VoiceError, match="legacy inactive"):
        voices.migrate_legacy_lifecycle("author-linkedin", "Reviewer")
    with pytest.raises(VoiceError, match="Unknown voice"):
        service._withdraw(
            "missing",
            VoiceTransition({"active"}, "inactive", "deactivate", "Author", "pause"),
        )
    with pytest.raises(VoiceError, match="no selected version"):
        service._verify_selected("author-linkedin", {})

    _starter(project, "legacy-voice")
    registry = voices._read()
    registry["profiles"]["legacy-voice"]["status"] = "inactive"
    voices.path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    migrated = voices.migrate_legacy_lifecycle("legacy-voice", "Reviewer")
    assert migrated["legacy_migration"] is True
    with pytest.raises(VoiceError, match="already exist"):
        voices.migrate_legacy_lifecycle("legacy-voice", "Reviewer")

    contexts = _context(project, "author-linkedin", "policy")
    context_service = PerspectiveContextLifecycleService(contexts)
    with pytest.raises(PerspectiveError, match="Unknown"):
        context_service.plan("missing")
    with pytest.raises(PerspectiveError, match="cannot reactivate"):
        contexts.reactivate("policy", "Author")
    context_plan = contexts.retirement_plan("policy")
    with pytest.raises(PerspectiveError, match="cannot restore"):
        contexts.restore_context("policy", "Author", "Reviewer", context_plan["binding_hash"])
    with pytest.raises(PerspectiveError, match="stale"):
        contexts.retire_context("policy", "Author", "retired", plan_hash="sha256:stale")
    with pytest.raises(PerspectiveError, match="reject or abandon"):
        contexts.decide_candidate("policy", "sha256:none", "Author", "bad", "retain")
    shutil.rmtree(contexts.context_root("policy") / "candidate")
    with pytest.raises(PerspectiveError, match="has not been created"):
        contexts.decide_candidate("policy", "sha256:none", "Author", "bad")
    with pytest.raises(PerspectiveError, match="legacy inactive"):
        contexts.migrate_legacy_lifecycle("policy", "Reviewer")

    legacy_contexts = _context(project, "author-linkedin", "legacy-policy")
    context_registry = legacy_contexts._read()
    context_registry["contexts"]["legacy-policy"]["status"] = "inactive"
    legacy_contexts.registry_path.write_text(
        json.dumps(context_registry, indent=2), encoding="utf-8"
    )
    migrated_context = legacy_contexts.migrate_legacy_lifecycle("legacy-policy", "Reviewer")
    assert migrated_context["legacy_migration"] is True
    with pytest.raises(PerspectiveError, match="already exist"):
        legacy_contexts.migrate_legacy_lifecycle("legacy-policy", "Reviewer")


def test_context_retirement_requires_candidate_and_proposal_dispositions(project):
    contexts = _context(project, "default", "energy")
    contexts.retire_entry("energy", "energy-001", "changed position")
    proposal = contexts.context_root("energy") / "proposals" / "open.json"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text(json.dumps({"id": "open", "status": "staged"}), encoding="utf-8")
    plan = contexts.retirement_plan("energy")
    with pytest.raises(PerspectiveError, match="candidate requires"):
        contexts.retire_context("energy", "Author", "retired", plan_hash=plan["binding_hash"])
    with pytest.raises(PerspectiveError, match="proposals require"):
        contexts.retire_context(
            "energy",
            "Author",
            "retired",
            plan_hash=plan["binding_hash"],
            candidate_disposition="retain",
        )
    retired = contexts.retire_context(
        "energy",
        "Author",
        "retired",
        plan_hash=plan["binding_hash"],
        candidate_disposition="abandon",
        proposal_disposition="reject",
    )
    assert retired["resulting_status"] == "retired"

    lifecycle = PerspectiveContextLifecycleService(contexts)
    assert lifecycle._valid_actions("active")[0] == "deactivate"
    assert lifecycle._valid_actions("inactive")[0] == "reactivate"
    assert lifecycle._valid_actions("retired")[0] == "restore-context-plan"
    assert lifecycle._valid_actions("candidate") == ["inspect-history", "verify-lifecycle"]
