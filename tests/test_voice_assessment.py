import json

import yaml
from conftest import passing_critique, valid_draft

from content_creator.cli import main
from content_creator.domain import WorkOrder
from content_creator.linguistics import build_linguistic_signature
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.voice_assessment import assess_linguistic_signature
from content_creator.voices import hash_file


def _signature(count=24):
    return build_linguistic_signature(
        [
            {
                "id": "source-{:03d}".format(index),
                "kind": "text",
                "weight": 1.0,
                "text": (
                    "I keep the argument measured because context matters. "
                    "However, a useful system should preserve judgment. "
                )
                * (8 + (index % 4))
                + ("You can test this claim. " * (index % 4)),
            }
            for index in range(count)
        ]
    )


def _install_active_voice(project, signature):
    version = project / "profiles" / "alice" / "versions" / "1.0.0"
    version.mkdir(parents=True)
    (version / "profile.md").write_text("# Alice voice", encoding="utf-8")
    (version / "linguistic-signature.json").write_text(
        json.dumps(signature), encoding="utf-8"
    )
    (version / "source-index.json").write_text("[]", encoding="utf-8")
    components = {
        "profile": "profile.md",
        "sources": "source-index.json",
        "linguistic_signature": "linguistic-signature.json",
    }
    (version / "manifest.json").write_text(
        json.dumps(
            {
                "id": "alice",
                "display_name": "Alice",
                "version": "1.0.0",
                "status": "active",
                "candidate_hash": "sha256:fixture",
                "components": components,
                "component_hashes": {
                    name: hash_file(version / filename)
                    for name, filename in components.items()
                },
                "supported_packs": {"linkedin-post": "high"},
                "authorisation": {"confirmed": True},
            }
        ),
        encoding="utf-8",
    )
    (project / "profiles" / "registry.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "profiles": {
                    "alice": {
                        "status": "active",
                        "active_version": "1.0.0",
                        "versions": {
                            "1.0.0": {
                                "status": "active",
                                "path": "profiles/alice/versions/1.0.0",
                            }
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def test_assessment_reports_material_outliers_without_authorship_claim():
    report = assess_linguistic_signature(
        _signature(),
        ("You? You! You should always act now! " * 40),
        voice_id="alice",
        voice_version="1.0.0",
        max_reported_outliers=50,
    )

    assert report["status"] == "material_outliers"
    assert report["outlier_count"] > 0
    assert any(
        item["feature"] == "second_person_per_1000_words"
        for item in report["outliers"]
    )
    assert "not proof of authorship" in report["claim_limit"]


def test_assessment_refuses_to_overstate_a_small_corpus():
    report = assess_linguistic_signature(
        _signature(8),
        valid_draft(),
        voice_id="alice",
        voice_version="1.0.0",
    )

    assert report["status"] == "insufficient_evidence"
    assert report["outliers"] == []


def test_disabled_assessment_does_not_enter_the_run(project):
    fake = FakeProvider(
        {"writer": [valid_draft()], "critic": [passing_critique()]}
    )
    orchestrator = Orchestrator(
        project,
        registry=ProviderRegistry({"anthropic": fake}),
    )

    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            format="post",
        )
    )

    assert not (project / "runs" / state.id / "voice-assessment-01.json").exists()
    critic_request = next(
        request for request in fake.requests if request.role == "critic"
    )
    critic_payload = json.loads(critic_request.user.split("\nINPUT\n", 1)[1])
    assert "voice_assessment" not in critic_payload


def test_enabled_assessment_is_advisory_to_critic_only(project):
    _install_active_voice(project, _signature())
    configuration = yaml.safe_load(
        (project / "content-creator.yaml").read_text(encoding="utf-8")
    ) if (project / "content-creator.yaml").exists() else {}
    configuration["voice_assessment"] = {"enabled": True}
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(configuration), encoding="utf-8"
    )
    assessed_draft = valid_draft() + "\n\n" + valid_draft()
    fake = FakeProvider(
        {"writer": [assessed_draft], "critic": [passing_critique()]}
    )
    orchestrator = Orchestrator(
        project, registry=ProviderRegistry({"anthropic": fake})
    )

    state = orchestrator.start(
        WorkOrder(
            request="write",
            topic="topic",
            content_pack="linkedin-post",
            voice_id="alice",
            format="post",
        )
    )

    report_path = project / "runs" / state.id / "voice-assessment-01.json"
    assert report_path.exists()
    critic_request = next(request for request in fake.requests if request.role == "critic")
    critic_payload = json.loads(critic_request.user.split("\nINPUT\n", 1)[1])
    assert critic_payload["voice_assessment"]["status"] in {
        "no_material_outliers",
        "material_outliers",
    }
    writer_request = next(request for request in fake.requests if request.role == "writer")
    writer_payload = json.loads(writer_request.user.split("\nINPUT\n", 1)[1])
    assert "voice_assessment" not in writer_payload
    assert "advisory evidence only" in critic_request.user


def test_cli_can_assess_explicitly_while_automation_is_disabled(
    project, capsys
):
    _install_active_voice(project, _signature())
    draft = project / "draft.md"
    draft.write_text(valid_draft() + "\n\n" + valid_draft(), encoding="utf-8")

    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "assess",
                "alice",
                "--draft",
                str(draft),
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["voice_id"] == "alice"
    assert report["status"] in {
        "no_material_outliers",
        "material_outliers",
    }
