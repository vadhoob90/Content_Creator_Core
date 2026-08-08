import json

import pytest

from content_creator.cli import main
from content_creator.voice_rejection import candidate_decision
from content_creator.voices import VoiceError, VoiceRegistry


def _voice_material(project):
    material = project / "material"
    material.mkdir()
    sentence = (
        "By Example Person. A concrete explanation begins with a recognisable "
        "problem and then makes each decision visible to the reader. "
    )
    (material / "essay.txt").write_text(sentence * 24, encoding="utf-8")
    (material / "transcript.txt").write_text("Example: " + sentence * 20, encoding="utf-8")
    return material


def _create(project, material):
    return main(
        [
            "--root",
            str(project),
            "voice",
            "create",
            "--name",
            "Example Person",
            "--authorised-by",
            "Owner",
            "--documents",
            str(material),
            "--offline-analysis",
        ]
    )


def test_approved_candidate_copy_is_not_reported_as_pending(project, capsys):
    _create(project, _voice_material(project))
    capsys.readouterr()
    main(["--root", str(project), "voice", "approve", "example-person"])
    capsys.readouterr()

    active = VoiceRegistry(project).get("example-person")

    assert candidate_decision(project, "example-person", active)["status"] == "already_active"


def test_reject_candidate_preserves_active_voice_and_is_idempotent(project, capsys):
    material = _voice_material(project)
    _create(project, material)
    capsys.readouterr()
    main(["--root", str(project), "voice", "approve", "example-person"])
    capsys.readouterr()
    source = material / "essay.txt"
    source.write_text(source.read_text() + "\nA newly observed ending.", encoding="utf-8")
    main(
        [
            "--root",
            str(project),
            "voice",
            "rebuild",
            "example-person",
            "--offline-analysis",
        ]
    )
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    candidate_hash = json.loads((candidate / "manifest.json").read_text())["candidate_hash"]
    registry_path = project / "profiles" / "registry.json"
    registry_before = registry_path.read_bytes()
    active_profile = project / "profiles" / "example-person" / "versions" / "1.0.0" / "profile.md"
    profile_before = active_profile.read_bytes()
    arguments = [
        "--root",
        str(project),
        "voice",
        "reject",
        "example-person",
        "--candidate-hash",
        candidate_hash,
        "--rejected-by",
        "Owner",
        "--reason",
        "The active version remains preferable.",
    ]

    assert main(arguments) == 0
    first = json.loads(capsys.readouterr().out)
    assert first["candidate_hash"] == candidate_hash
    assert first["active_version"] == "1.0.0"
    assert registry_path.read_bytes() == registry_before
    assert active_profile.read_bytes() == profile_before
    assert not candidate.exists()
    rejected = project / first["snapshot_path"]
    assert json.loads((rejected / "manifest.json").read_text())["status"] == "rejected"
    assert VoiceRegistry(project).resolve("example-person")["version"] == "1.0.0"

    assert main(arguments) == 0
    assert json.loads(capsys.readouterr().out) == first


def test_reject_refuses_changed_candidate_without_mutation(project, capsys):
    _create(project, _voice_material(project))
    capsys.readouterr()
    candidate = project / "profiles" / "example-person" / "candidate"
    before = (candidate / "manifest.json").read_bytes()

    with pytest.raises(VoiceError, match="changed after review"):
        main(
            [
                "--root",
                str(project),
                "voice",
                "reject",
                "example-person",
                "--candidate-hash",
                "sha256:" + "0" * 64,
                "--rejected-by",
                "Owner",
                "--reason",
                "Not this candidate.",
            ]
        )

    assert (candidate / "manifest.json").read_bytes() == before
