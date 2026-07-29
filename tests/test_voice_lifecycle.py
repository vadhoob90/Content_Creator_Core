import json

import pytest
from conftest import passing_critique, valid_draft

from content_creator.cli import main
from content_creator.domain import RunStatus, WorkOrder
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.voices import VoiceError, VoiceRegistry


def _voice_material(project):
    material = project / "material"
    material.mkdir()
    sentence = (
        "By Example Person. A concrete explanation begins with a recognisable "
        "problem and then makes each decision visible to the reader. "
    )
    first = material / "essay.txt"
    second = material / "transcript.txt"
    first.write_text(sentence * 24, encoding="utf-8")
    second.write_text(
        "Example: " + sentence * 20,
        encoding="utf-8",
    )
    return material


def test_voice_id_label_and_author_identity_are_separate(project, capsys):
    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "create",
                "--voice-id",
                "example-person-general",
                "--label",
                "Example Person — General",
                "--author-name",
                "Example Person",
                "--author-alias",
                "E. Person",
                "--authorised-by",
                "Example Owner",
                "--no-build",
            ]
        )
        == 0
    )
    order = json.loads(capsys.readouterr().out)

    assert order["voice_id"] == "example-person-general"
    assert order["display_name"] == "Example Person — General"
    assert order["author_name"] == "Example Person"
    assert order["author_aliases"] == ["E. Person"]


def test_voice_build_approve_idempotency_deactivate_and_reactivate(project, capsys):
    material = _voice_material(project)
    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "create",
                "--name",
                "Example Person",
                "--authorised-by",
                "Owner",
                "--use",
                "general-text",
                "--documents",
                str(material),
                "--offline-analysis",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert main(["--root", str(project), "voice", "verify", "example-person"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "approve",
                "example-person",
                "--approved-by",
                "Owner",
            ]
        )
        == 0
    )
    first = json.loads(capsys.readouterr().out)
    assert first["activated_version"] == "1.0.0"

    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "approve",
                "example-person",
                "--approved-by",
                "Owner",
            ]
        )
        == 0
    )
    repeated = json.loads(capsys.readouterr().out)
    assert repeated == first

    registry = VoiceRegistry(project)
    assert registry.resolve("example-person")["version"] == "1.0.0"
    registry.deactivate("example-person", "permission withdrawn")
    with pytest.raises(VoiceError, match="not active"):
        registry.resolve("example-person")

    receipt = registry.activate("example-person", "Owner", "reactivation")
    assert receipt.activated_version == "2.0.0"


def test_candidate_and_unknown_voice_cannot_resolve(project):
    material = _voice_material(project)
    main(
        [
            "--root",
            str(project),
            "voice",
            "create",
            "--name",
            "Candidate Person",
            "--authorised-by",
            "Owner",
            "--documents",
            str(material),
            "--offline-analysis",
        ]
    )
    registry = VoiceRegistry(project)
    with pytest.raises(VoiceError, match="not complete"):
        registry.resolve("candidate-person")
    with pytest.raises(VoiceError, match="Unknown voice"):
        registry.resolve("missing-person")


def test_activation_hash_failure_is_atomic_and_historical_version_resolves(project):
    material = _voice_material(project)
    main(
        [
            "--root",
            str(project),
            "voice",
            "create",
            "--name",
            "Protected Person",
            "--authorised-by",
            "Owner",
            "--documents",
            str(material),
            "--offline-analysis",
        ]
    )
    candidate = project / "profiles" / "protected-person" / "candidate"
    (candidate / "profile.md").write_text("tampered", encoding="utf-8")
    registry = VoiceRegistry(project)
    with pytest.raises(VoiceError, match="hash mismatch"):
        registry.activate("protected-person", "Owner")
    assert "protected-person" not in registry.list()


def test_pinned_version_remains_resolvable_after_deactivation(project, capsys):
    material = _voice_material(project)
    main(
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
    capsys.readouterr()
    main(
        [
            "--root",
            str(project),
            "voice",
            "approve",
            "example-person",
        ]
    )
    capsys.readouterr()
    registry = VoiceRegistry(project)
    registry.deactivate("example-person", "withdrawn")
    with pytest.raises(VoiceError, match="not active"):
        registry.resolve("example-person", "1.0.0")
    assert (
        registry.resolve("example-person", "1.0.0", allow_inactive=True)[
            "version"
        ]
        == "1.0.0"
    )


def test_active_voice_component_tampering_is_rejected(project, capsys):
    material = _voice_material(project)
    main(
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
    capsys.readouterr()
    main(["--root", str(project), "voice", "approve", "example-person"])
    capsys.readouterr()
    profile = (
        project
        / "profiles"
        / "example-person"
        / "versions"
        / "1.0.0"
        / "profile.md"
    )
    profile.write_text("tampered", encoding="utf-8")
    with pytest.raises(VoiceError, match="Active voice component hash mismatch"):
        VoiceRegistry(project).resolve("example-person")


def test_repeated_build_has_stable_candidate_hash(project):
    material = _voice_material(project)
    main(
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
    first = json.loads(
        (project / "profiles" / "example-person" / "candidate" / "manifest.json").read_text()
    )
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
    second = json.loads(
        (project / "profiles" / "example-person" / "candidate" / "manifest.json").read_text()
    )
    assert second["candidate_hash"] == first["candidate_hash"]
    candidate = project / "profiles" / "example-person" / "candidate"
    signature = json.loads((candidate / "linguistic-signature.json").read_text())
    assert signature["framework"] == "lightweight-corpus-stylistics"
    assert "linguistic_signature" in second["components"]


def test_cli_exposes_candidate_linguistic_signature(project, capsys):
    material = _voice_material(project)
    main(
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
    capsys.readouterr()

    assert (
        main(
            [
                "--root",
                str(project),
                "voice",
                "signature",
                "example-person",
            ]
        )
        == 0
    )
    signature = json.loads(capsys.readouterr().out)
    assert signature["framework"] == "lightweight-corpus-stylistics"


def test_failed_rebuild_preserves_previous_candidate(project):
    material = _voice_material(project)
    main(
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
    manifest = (
        project / "profiles" / "example-person" / "candidate" / "manifest.json"
    )
    before = manifest.read_text(encoding="utf-8")
    work_order = project / "profiles" / "example-person" / "work-order.json"
    data = json.loads(work_order.read_text(encoding="utf-8"))
    data["documents"] = [str(project / "missing.txt")]
    work_order.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(Exception, match="previous candidate preserved"):
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
    assert manifest.read_text(encoding="utf-8") == before


def test_fresh_fixture_voice_creates_versioned_content(project, capsys):
    material = _voice_material(project)
    main(
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
    capsys.readouterr()
    main(["--root", str(project), "voice", "approve", "example-person"])
    capsys.readouterr()
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry(
            {
                "anthropic": FakeProvider(
                    {
                        "writer": [valid_draft()],
                        "critic": [passing_critique()],
                    }
                )
            }
        ),
    )
    state = orchestrator.start(
        WorkOrder(
            request="Explain a useful system",
            topic="Useful system",
            voice_id="example-person",
            content_pack="general-text",
            format="text",
            pack_options={"length": "50:600"},
        )
    )
    context = json.loads(
        (project / "runs" / state.id / "resolved-context.json").read_text()
    )
    assert state.status == RunStatus.READY
    assert context["engine_version"] == "0.4.0"
    assert context["voice"]["version"] == "1.0.0"
    assert context["component_hashes"]["agent_harness"].startswith("sha256:")
    assert context["component_hashes"]["repository_agent_writer"].startswith(
        "sha256:"
    )
    assert context["component_hashes"][
        "repository_learning_memory"
    ].startswith("sha256:")
    assert context["component_hashes"]["voice_profile"].startswith("sha256:")
