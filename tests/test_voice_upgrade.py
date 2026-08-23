"""Verify governed learning-and-publication voice upgrades."""

import json
import os
from pathlib import Path

import pytest

from content_creator.cli import main
from content_creator.voice_models import VoiceManifest
from content_creator.voice_upgrade.epochs import epoch_path, load_epoch
from content_creator.voice_upgrade.service import VoiceUpgradeError


def _material(path: Path, phrase: str) -> Path:
    path.write_text(
        (phrase + " The explanation makes the operational choice visible. ") * 45,
        encoding="utf-8",
    )
    return path


def _active_voice(project, capsys):
    material = project / "author-material"
    material.mkdir()
    _material(material / "one.md", "By Example Person. Start from a concrete constraint.")
    _material(material / "two.md", "By Example Person. End with a bounded consequence.")
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "create",
                "--name",
                "Example Person",
                "--authorised-by",
                "Example Person",
                "--documents",
                str(material),
                "--offline-analysis",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--workspace", str(project), "voice", "approve", "example-person"]) == 0
    capsys.readouterr()
    return material


def _add_learning(project):
    path = epoch_path(project, "example-person", "1.0.0")
    epoch = json.loads(path.read_text(encoding="utf-8"))
    epoch["records"].append(
        {
            "id": "learning-opening",
            "role": "writer",
            "scope": "general",
            "principle": "Avoid generic staccato micro-sentences.",
            "evidence": "Explicit author feedback in reviewed run run-001.",
            "status": "active",
            "confidence": 1.0,
            "source_event": "author_feedback",
            "run_id": "run-001",
            "voice_id": "example-person",
            "voice_version": "1.0.0",
        }
    )
    path.write_text(json.dumps(epoch, indent=2), encoding="utf-8")


def _review_selection(project):
    upgrade = project / "profiles" / "example-person" / "upgrade"
    template = json.loads((upgrade / "learning-selection.template.json").read_text())
    template["reviewed_by"] = "Example Person"
    template["dispositions"][0].update(
        {
            "classification": "voice-constraint",
            "disposition": "incorporate",
            "rationale": "This is stable, author-specific linguistic guidance.",
        }
    )
    selection = upgrade / "learning-selection.json"
    selection.write_text(json.dumps(template, indent=2), encoding="utf-8")
    return selection


def test_incremental_upgrade_uses_only_delta_and_transitions_learning_epoch(project, capsys):
    material = _active_voice(project, capsys)
    _add_learning(project)
    new = _material(
        project / "new-author-article.md",
        "By Example Person. New evidence supports a more explicit transition.",
    )
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "add-sources",
                "example-person",
                "--documents",
                str(new),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade-plan",
                "example-person",
                "--offline-analysis",
            ]
        )
        == 0
    )
    plan_output = json.loads(capsys.readouterr().out)
    assert plan_output["evidence_baseline_count"] == 2
    assert plan_output["evidence_delta_count"] == 1
    assert plan_output["state"] == "awaiting_selection"
    selection = _review_selection(project)
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade",
                "example-person",
                "--offline-analysis",
                "--learning-selection",
                str(selection),
                "--idempotency-key",
                "example-person-v2",
            ]
        )
        == 0
    )
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    analysed = json.loads((candidate / "source-index.json").read_text())
    represented = json.loads((candidate / "evidence-baseline.json").read_text())
    constraints = json.loads((candidate / "constraints.json").read_text())
    assert len(analysed) == 1
    assert len(represented["records"]) == 3
    assert "learning-opening" in constraints["reviewed_voice_constraints"]
    assert all(str(material) not in item["cache_path"] for item in analysed)
    assert main(["--workspace", str(project), "voice", "approve", "example-person"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["activated_version"] == "2.0.0"
    assert receipt["selected_learning_ids"] == ["learning-opening"]
    old_epoch = json.loads(epoch_path(project, "example-person", "1.0.0").read_text())
    new_epoch = json.loads(epoch_path(project, "example-person", "2.0.0").read_text())
    assert old_epoch["status"] == "frozen"
    assert new_epoch["status"] == "active"
    assert new_epoch["records"] == []


def test_upgrade_plan_is_stale_after_learning_epoch_changes(project, capsys):
    _active_voice(project, capsys)
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade-plan",
                "example-person",
                "--mode",
                "full-corpus",
                "--offline-analysis",
            ]
        )
        == 0
    )
    capsys.readouterr()
    _add_learning(project)
    with pytest.raises(VoiceUpgradeError, match="learning epoch"):
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade",
                "example-person",
                "--mode",
                "full-corpus",
                "--offline-analysis",
            ]
        )


def test_rebuild_approval_cannot_drop_unreviewed_active_learning(project, capsys):
    _active_voice(project, capsys)
    _add_learning(project)
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "rebuild",
                "example-person",
                "--offline-analysis",
            ]
        )
        == 0
    )
    capsys.readouterr()
    with pytest.raises(Exception, match="requires voice upgrade planning"):
        main(["--workspace", str(project), "voice", "approve", "example-person"])


def test_starter_manifest_records_neutral_strategy_and_reviewed_transition(project, capsys):
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "onboard",
                "example-person",
                "--strategy",
                "starter",
                "--author-name",
                "Example Person",
            ]
        )
        == 0
    )
    capsys.readouterr()
    starter_manifest = VoiceManifest.model_validate_json(
        (project / "profiles/example-person/versions/1.0.0/manifest.json").read_text()
    )
    assert starter_manifest.strategy.value == "starter-neutral"


def test_incremental_plan_uses_hashes_for_duplicates_edits_and_no_op(project, capsys):
    material = _active_voice(project, capsys)
    duplicate = project / "duplicate.md"
    duplicate.write_text((material / "one.md").read_text(encoding="utf-8"), encoding="utf-8")
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "add-sources",
                "example-person",
                "--documents",
                str(duplicate),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade-plan",
                "example-person",
                "--offline-analysis",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["evidence_delta_count"] == 0
    assert plan["state"] == "no_material_change"
    assert len(plan["duplicates"]) == 1
    with pytest.raises(VoiceUpgradeError, match="no_material_change"):
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade",
                "example-person",
                "--offline-analysis",
            ]
        )

    _material(material / "one.md", "By Example Person. This is an edited older article.")
    os.utime(material / "one.md", (1, 1))
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade-plan",
                "example-person",
                "--offline-analysis",
            ]
        )
        == 0
    )
    edited = json.loads(capsys.readouterr().out)
    assert edited["evidence_delta_count"] == 1


def test_full_corpus_offline_builds_current_authorised_corpus(project, capsys):
    _active_voice(project, capsys)
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade-plan",
                "example-person",
                "--mode",
                "full-corpus",
                "--offline-analysis",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["historical_private_corpus_transmitted"] is False
    assert plan["data_sharing"]["source_count"] == 2
    assert "--offline-analysis" in plan["exact_commands"][0]
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade",
                "example-person",
                "--mode",
                "full-corpus",
                "--offline-analysis",
            ]
        )
        == 0
    )
    capsys.readouterr()
    analysed = json.loads(
        (project / "profiles/example-person/candidate/source-index.json").read_text()
    )
    assert len(analysed) == 2


def test_full_corpus_provider_plan_requires_explicit_sharing_approval(project, capsys):
    _active_voice(project, capsys)
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade-plan",
                "example-person",
                "--mode",
                "full-corpus",
                "--provider",
                "anthropic",
            ]
        )
        == 0
    )
    plan = json.loads(capsys.readouterr().out)
    assert plan["state"] == "awaiting_provider_approval"
    assert plan["historical_private_corpus_transmitted"] is True
    assert plan["exact_commands"][0][-2:] == ["--provider", "anthropic"]
    with pytest.raises(VoiceUpgradeError, match="explicit approval"):
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "upgrade",
                "example-person",
                "--mode",
                "full-corpus",
                "--provider",
                "anthropic",
            ]
        )


def test_incremental_build_retry_returns_same_candidate(project, capsys):
    _active_voice(project, capsys)
    new = _material(project / "new.md", "By Example Person. Add one bounded example.")
    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "add-sources",
                "example-person",
                "--documents",
                str(new),
            ]
        )
        == 0
    )
    capsys.readouterr()
    plan_args = [
        "--workspace",
        str(project),
        "voice",
        "upgrade-plan",
        "example-person",
        "--offline-analysis",
    ]
    assert main(plan_args) == 0
    capsys.readouterr()
    build_args = [
        "--workspace",
        str(project),
        "voice",
        "upgrade",
        "example-person",
        "--offline-analysis",
        "--idempotency-key",
        "stable-retry",
    ]
    assert main(build_args) == 0
    first = json.loads(capsys.readouterr().out)
    assert main(build_args) == 0
    second = json.loads(capsys.readouterr().out)
    assert second["candidate_hash"] == first["candidate_hash"]


def test_legacy_learning_requires_explicit_version_assignment(project):
    legacy = project / "profiles/legacy/learnings/memory.json"
    legacy.parent.mkdir(parents=True)
    legacy.write_text(
        json.dumps(
            {
                "version": 1,
                "records": [
                    {
                        "id": "legacy-learning",
                        "status": "active",
                        "principle": "Keep the consequence bounded.",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    unassigned = load_epoch(project, "legacy", "1.0.0")
    assert unassigned.records == []
    assert not epoch_path(project, "legacy", "1.0.0").exists()
    assigned = load_epoch(project, "legacy", "1.0.0", migrate_legacy=True)
    assert [record["id"] for record in assigned.records] == ["legacy-learning"]
    assert epoch_path(project, "legacy", "1.0.0").is_file()
