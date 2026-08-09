import json
import shutil

import pytest

import content_creator.voice_activation as voice_activation
from content_creator.cli import main
from content_creator.versioned_artifacts import hash_file
from content_creator.voice_activation import _validate_active_baseline, _validated_candidate
from content_creator.voice_models import VoiceError, VoiceManifest
from content_creator.voices import VoiceRegistry


def _guarded_candidate(project):
    material = project / "material"
    material.mkdir()
    sentence = (
        "By Guarded Person. A concrete explanation makes each decision visible "
        "and gives the reader evidence they can inspect. "
    )
    (material / "essay.txt").write_text(sentence * 24, encoding="utf-8")
    (material / "transcript.txt").write_text(sentence * 20, encoding="utf-8")
    main(
        [
            "--root",
            str(project),
            "voice",
            "create",
            "--name",
            "Guarded Person",
            "--authorised-by",
            "Owner",
            "--documents",
            str(material),
            "--offline-analysis",
        ]
    )
    candidate = project / "profiles" / "guarded-person" / "candidate"
    manifest = json.loads((candidate / "manifest.json").read_text(encoding="utf-8"))
    return candidate, manifest


def _write_failed_evaluation(candidate, manifest, hard_failures):
    evaluation_path = candidate / "evaluation-report.json"
    evaluation_path.write_text(
        json.dumps({"passed": False, "hard_failures": hard_failures}), encoding="utf-8"
    )
    evaluation_key = next(
        key for key, path in manifest["components"].items() if path == "evaluation-report.json"
    )
    updated = dict(manifest)
    updated["component_hashes"] = dict(manifest["component_hashes"])
    updated["component_hashes"][evaluation_key] = hash_file(evaluation_path)
    (candidate / "manifest.json").write_text(json.dumps(updated), encoding="utf-8")


def test_candidate_activation_fails_closed_on_invalid_candidate_state(project):
    candidate, original = _guarded_candidate(project)
    manifest_path = candidate / "manifest.json"

    manifest_path.rename(candidate / "manifest.backup")
    with pytest.raises(VoiceError, match="has not been built"):
        _validated_candidate(candidate, None)
    (candidate / "manifest.backup").rename(manifest_path)

    unauthorised = dict(original)
    unauthorised["authorisation"] = dict(original["authorisation"], confirmed=False)
    manifest_path.write_text(json.dumps(unauthorised), encoding="utf-8")
    with pytest.raises(VoiceError, match="authorisation has not been confirmed"):
        _validated_candidate(candidate, None)

    manifest_path.write_text(json.dumps(dict(original, status="active")), encoding="utf-8")
    with pytest.raises(VoiceError, match="not awaiting approval"):
        _validated_candidate(candidate, None)

    stale_delta = dict(original, evolution_delta_hash="0" * 64)
    manifest_path.write_text(json.dumps(stale_delta), encoding="utf-8")
    (candidate / "voice-evolution.json").write_text("{}", encoding="utf-8")
    with pytest.raises(VoiceError, match="evolution delta hash mismatch"):
        _validated_candidate(candidate, None)


def test_candidate_activation_distinguishes_integrity_failures_from_quality_risk(project):
    candidate, manifest_data = _guarded_candidate(project)

    _write_failed_evaluation(candidate, manifest_data, ["source integrity failed"])
    with pytest.raises(VoiceError, match="non-overridable integrity failures"):
        _validated_candidate(candidate, "Owner accepts quality risk")

    _write_failed_evaluation(candidate, manifest_data, [])
    with pytest.raises(VoiceError, match="evaluation did not pass"):
        _validated_candidate(candidate, None)
    manifest, path = _validated_candidate(candidate, "Owner accepts quality risk")
    assert manifest.id == "guarded-person"
    assert path == candidate / "evaluation-report.json"


def test_voice_activation_recovers_snapshot_after_process_interruption(project, monkeypatch):
    candidate, _manifest_data = _guarded_candidate(project)
    registry = VoiceRegistry(project)
    original_activate_registry = voice_activation._activate_registry
    interrupted = False

    def interrupt_registry_once(registry_service, registry_data, manifest, version):
        nonlocal interrupted
        if not interrupted:
            interrupted = True
            raise SystemExit("injected process interruption")
        original_activate_registry(registry_service, registry_data, manifest, version)

    monkeypatch.setattr(voice_activation, "_activate_registry", interrupt_registry_once)

    with pytest.raises(SystemExit, match="injected process interruption"):
        registry.activate("guarded-person", "Owner")
    receipt = registry.activate("guarded-person", "Owner")

    versions = candidate.parent / "versions"
    assert receipt.activated_version == "1.0.0"
    assert [path.name for path in versions.glob("[0-9]*")] == ["1.0.0"]
    assert registry.resolve("guarded-person")["version"] == "1.0.0"


def _evolution_manifest(original):
    return VoiceManifest.model_validate(
        {
            **original,
            "evolution_mode": "evolve",
            "baseline_version": "1.0.0",
            "baseline_candidate_hash": original["candidate_hash"],
        }
    )


@pytest.mark.parametrize(
    ("registry_entry", "message"),
    [
        ({"active_version": "2.0.0"}, "stale active baseline version"),
        (
            {"active_version": "1.0.0", "candidate_hash": "0" * 64},
            "stale registry baseline hash",
        ),
    ],
)
def test_evolution_activation_rejects_stale_registry_baselines(project, registry_entry, message):
    candidate, original = _guarded_candidate(project)
    manifest = _evolution_manifest(original)
    registry = {"profiles": {"guarded-person": registry_entry}}

    with pytest.raises(VoiceError, match=message):
        _validate_active_baseline(candidate.parent, registry, "guarded-person", manifest)


@pytest.mark.parametrize("tamper", ["manifest", "component"])
def test_evolution_activation_rejects_tampered_immutable_baseline(project, tamper):
    candidate, original = _guarded_candidate(project)
    voice_root = candidate.parent
    baseline = voice_root / "versions" / "1.0.0"
    shutil.copytree(candidate, baseline)
    manifest = _evolution_manifest(original)
    registry = {
        "profiles": {
            "guarded-person": {
                "active_version": "1.0.0",
                "candidate_hash": original["candidate_hash"],
            }
        }
    }
    if tamper == "manifest":
        baseline_data = dict(original, candidate_hash="0" * 64)
        (baseline / "manifest.json").write_text(json.dumps(baseline_data), encoding="utf-8")
        message = "stale active baseline hash"
    else:
        (baseline / "profile.md").write_text("tampered", encoding="utf-8")
        message = "Active baseline component hash mismatch"

    with pytest.raises(VoiceError, match=message):
        _validate_active_baseline(voice_root, registry, "guarded-person", manifest)
