import json

import yaml
from conftest import passing_critique, valid_draft

from content_creator.cli import main
from content_creator.domain import WorkOrder
from content_creator.linguistics import build_linguistic_signature
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.voice_assessment import (
    assess_linguistic_signature,
    load_score_preference,
    save_score_preference,
)
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
                "supported_packs": {
                    "linkedin-post": "high",
                    "linkedin-article": "high",
                },
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
    assert report["type"] == "statistical_voice_score"
    assert report["method"] == "deterministic"
    assert 0 <= report["score"] < 100
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


def test_disabled_score_does_not_enter_the_run(project):
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

    assert not (
        project / "runs" / state.id / "statistical-voice-score-01.json"
    ).exists()
    critic_request = next(
        request for request in fake.requests if request.role == "critic"
    )
    critic_payload = json.loads(critic_request.user.split("\nINPUT\n", 1)[1])
    assert "statistical_voice_score" not in critic_payload


def test_enabled_score_is_advisory_to_critic_only(project):
    _install_active_voice(project, _signature())
    configuration = yaml.safe_load(
        (project / "content-creator.yaml").read_text(encoding="utf-8")
    ) if (project / "content-creator.yaml").exists() else {}
    configuration["statistical_voice_score"] = {"enabled": True}
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(configuration), encoding="utf-8"
    )
    assessed_draft = "\n\n".join(valid_draft() for _ in range(10))
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
            content_pack="linkedin-article",
            voice_id="alice",
            format="article",
        )
    )

    report_path = project / "runs" / state.id / "statistical-voice-score-01.json"
    assert report_path.exists()
    critic_request = next(request for request in fake.requests if request.role == "critic")
    critic_payload = json.loads(critic_request.user.split("\nINPUT\n", 1)[1])
    assert critic_payload["statistical_voice_score"]["status"] in {
        "no_material_outliers",
        "material_outliers",
    }
    writer_request = next(request for request in fake.requests if request.role == "writer")
    writer_payload = json.loads(writer_request.user.split("\nINPUT\n", 1)[1])
    assert "statistical_voice_score" not in writer_payload
    assert "advisory evidence only" in critic_request.user


def test_voice_preference_enables_score_when_workspace_default_is_off(project):
    _install_active_voice(project, _signature())
    save_score_preference(
        project,
        "alice",
        enabled=True,
        method="deterministic",
        selected_by="Alice",
    )
    assessed_draft = "\n\n".join(valid_draft() for _ in range(10))
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
            content_pack="linkedin-article",
            voice_id="alice",
            format="article",
        )
    )

    report = json.loads(
        (
            project / "runs" / state.id / "statistical-voice-score-01.json"
        ).read_text(encoding="utf-8")
    )
    assert report["method"] == "deterministic"
    assert report["score"] is not None


def test_short_form_pack_never_supplies_score_to_critic(project):
    _install_active_voice(project, _signature())
    configuration = {"statistical_voice_score": {"enabled": True}}
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(configuration), encoding="utf-8"
    )
    save_score_preference(
        project,
        "alice",
        enabled=True,
        method="deterministic",
        selected_by="Alice",
    )
    fake = FakeProvider(
        {"writer": [valid_draft()], "critic": [passing_critique()]}
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

    assert not (
        project / "runs" / state.id / "statistical-voice-score-01.json"
    ).exists()
    critic_request = next(
        request for request in fake.requests if request.role == "critic"
    )
    critic_payload = json.loads(critic_request.user.split("\nINPUT\n", 1)[1])
    assert "statistical_voice_score" not in critic_payload


def test_voice_preference_can_disable_workspace_default(project):
    _install_active_voice(project, _signature())
    configuration = {"statistical_voice_score": {"enabled": True}}
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump(configuration), encoding="utf-8"
    )
    save_score_preference(
        project,
        "alice",
        enabled=False,
        method="deterministic",
        selected_by="Alice",
    )
    fake = FakeProvider(
        {"writer": [valid_draft()], "critic": [passing_critique()]}
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

    assert not (
        project / "runs" / state.id / "statistical-voice-score-01.json"
    ).exists()


def test_cli_can_score_explicitly_while_automation_is_disabled(
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
                "score",
                "alice",
                "--draft",
                str(draft),
                "--method",
                "deterministic",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["voice_id"] == "alice"
    assert report["type"] == "statistical_voice_score"
    assert report["method"] == "deterministic"
    assert report["score"] is not None
    assert report["status"] in {
        "no_material_outliers",
        "material_outliers",
    }


def test_voice_creation_records_score_preference(project, capsys):
    documents = project / "voice-documents"
    documents.mkdir()
    (documents / "sample.md").write_text(valid_draft(), encoding="utf-8")

    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "create",
                "--author-name",
                "Alice",
                "--authorised-by",
                "Alice",
                "--documents",
                str(documents),
                "--no-build",
                "--statistical-voice-score",
                "deterministic",
            ]
        )
        == 0
    )
    capsys.readouterr()

    preference = load_score_preference(project, "alice")
    assert preference["enabled"] is True
    assert preference["method"] == "deterministic"


def test_score_config_changes_one_voice_preference(project, capsys):
    _install_active_voice(project, _signature())

    assert (
        main(
            [
                "--workspace",
                str(project),
                "voice",
                "score-config",
                "alice",
                "--enable",
                "--method",
                "ml",
                "--selected-by",
                "Alice",
            ]
        )
        == 0
    )
    report = json.loads(capsys.readouterr().out)

    assert report["enabled"] is True
    assert report["method"] == "ml"
