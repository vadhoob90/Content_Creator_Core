import json
import time

import pytest
import yaml
from conftest import passing_critique, valid_draft

import content_creator.cli as cli
from content_creator.cli import main
from content_creator.commands.voice_status_rendering import render_voice_status
from content_creator.orchestrator import Orchestrator
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.voices import VoiceRegistry


def _create_workspace(tmp_path, capsys):
    workspace = tmp_path / "author-workspace"
    assert (
        main(
            [
                "workspace",
                "create",
                str(workspace),
                "--name",
                "Author Workspace",
                "--author-name",
                "Example Author",
                "--voice-id",
                "example-general",
                "--voice-label",
                "Example Author — General",
                "--pack",
                "linkedin-post",
                "--core-ref",
                "v1.19.0",
            ]
        )
        == 0
    )
    capsys.readouterr()
    return workspace


def test_setup_snapshot_turns_existing_state_into_four_author_milestones(tmp_path, capsys):
    workspace = _create_workspace(tmp_path, capsys)

    assert main(["--workspace", str(workspace), "setup", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["schema_version"] == "1.0"
    assert result["completed_count"] == 1
    assert result["total_count"] == 4
    assert [item["id"] for item in result["milestones"]] == [
        "workspace",
        "writing-style",
        "model-connection",
        "first-piece",
    ]
    assert result["milestones"][1]["status"] == "choice-required"
    assert result["recommended_action"]["id"] == "choose-voice-route"
    assert [choice["command"] for choice in result["choices"]] == [
        ["setup", "starter"],
        ["setup", "source-derived"],
    ]


def test_setup_human_view_uses_progressive_disclosure(tmp_path, capsys):
    workspace = _create_workspace(tmp_path, capsys)

    assert main(["--workspace", str(workspace), "setup"]) == 0
    output = capsys.readouterr().out

    assert "Content Creator setup" in output
    assert "1 of 4 ready" in output
    assert "Writing style" in output
    assert "Neutral starter" in output
    assert "Personalised from my writing" in output
    for internal_term in ("manifest_hash", "learning_epoch", "candidate_hash", "registry.json"):
        assert internal_term not in output

    assert (
        main(
            [
                "--workspace",
                str(workspace),
                "voice",
                "status",
                "example-general",
                "--human",
            ]
        )
        == 0
    )
    status = capsys.readouterr().out
    assert "Status: choose how to begin" in status
    assert "content-creator setup starter" in status
    assert "candidate_hash" not in status

    assert main(["--workspace", str(workspace), "setup", "--details"]) == 0
    detailed = capsys.readouterr().out
    assert "Advanced details:" in detailed
    assert "content-creator personalisation show" in detailed


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (
            {"active": {"status": "active", "strategy": "starter-neutral"}},
            "Status: ready (neutral starter)",
        ),
        ({"candidate": "awaiting_approval"}, "Status: review required"),
        ({}, "Status: setup in progress"),
    ],
)
def test_human_voice_status_progressively_discloses_each_state(result, expected):
    assert expected in render_voice_status(result)


def test_setup_starter_infers_known_workspace_arguments_and_stays_concise(tmp_path, capsys):
    workspace = _create_workspace(tmp_path, capsys)

    assert main(["--workspace", str(workspace), "setup", "starter"]) == 0
    output = capsys.readouterr().out

    assert "Writing style ready" in output
    assert "Example Author" in output
    assert "sha256:" not in output
    assert "learning epoch" not in output.lower()
    resolved = VoiceRegistry(workspace).resolve("example-general")
    assert resolved["strategy"] == "starter-neutral"
    manifest = json.loads(
        (workspace / resolved["path"] / "manifest.json").read_text(encoding="utf-8")
    )
    assert "linkedin-post" in manifest["supported_packs"]

    assert main(["--workspace", str(workspace), "setup", "--json"]) == 0
    setup = json.loads(capsys.readouterr().out)
    assert setup["milestones"][1]["status"] == "ready"
    assert setup["recommended_action"]["id"] == "select-provider"


def test_source_derived_setup_defers_content_until_evidence_review(tmp_path, capsys):
    workspace = _create_workspace(tmp_path, capsys)

    assert main(["--workspace", str(workspace), "setup", "source-derived"]) == 0
    output = capsys.readouterr().out
    assert "Personalised writing setup started" in output

    assert main(["--workspace", str(workspace), "setup", "--json"]) == 0
    setup = json.loads(capsys.readouterr().out)
    assert setup["ready_for_content"] is False
    assert setup["milestones"][1]["status"] == "in-progress"
    assert setup["recommended_action"]["id"] == "continue-voice-onboarding"
    assert setup["choices"] == []


def test_setup_provider_verifies_before_persisting_selection(tmp_path, capsys, monkeypatch):
    workspace = _create_workspace(tmp_path, capsys)
    main(["--workspace", str(workspace), "setup", "starter"])
    capsys.readouterr()

    class VerifiedCodex:
        def verify(self):
            return {"authentication": "chatgpt"}

    monkeypatch.setattr(
        "content_creator.provider_setup.ProviderRegistry.get",
        lambda self, name: VerifiedCodex(),
    )
    monkeypatch.setattr(
        "content_creator.provider_setup.shutil.which",
        lambda executable: "/usr/local/bin/{}".format(executable),
    )

    assert (
        main(
            [
                "--workspace",
                str(workspace),
                "setup",
                "provider",
                "codex-native",
                "--json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    configuration = yaml.safe_load((workspace / "content-creator.yaml").read_text())

    assert result["status"] == "verified"
    assert result["provider"] == "codex-native"
    assert configuration["provider"]["default"] == "codex-native"
    assert (workspace / ".content-creator" / "provider-verification.json").is_file()

    assert main(["--workspace", str(workspace), "setup", "--json"]) == 0
    setup = json.loads(capsys.readouterr().out)
    assert setup["milestones"][2]["status"] == "ready"
    assert setup["recommended_action"]["id"] == "create-content"


def test_setup_requires_explicit_billing_confirmation_for_api_provider(
    tmp_path, capsys, monkeypatch
):
    workspace = _create_workspace(tmp_path, capsys)
    monkeypatch.setenv("OPENAI_API_KEY", "configured")

    assert main(["--workspace", str(workspace), "setup", "provider", "openai", "--json"]) == 8
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "confirmation-required"
    assert result["provider"] == "openai"
    assert "usage-billed" in result["message"]
    configuration = yaml.safe_load((workspace / "content-creator.yaml").read_text())
    assert configuration.get("provider", {}).get("default") is None


def test_setup_surfaces_an_unavailable_selected_provider_with_exact_recovery(
    tmp_path, capsys, monkeypatch
):
    workspace = _create_workspace(tmp_path, capsys)
    main(["--workspace", str(workspace), "setup", "starter"])
    capsys.readouterr()
    configuration_path = workspace / "content-creator.yaml"
    configuration = yaml.safe_load(configuration_path.read_text(encoding="utf-8"))
    configuration["provider"] = {"default": "codex-native"}
    configuration_path.write_text(yaml.safe_dump(configuration, sort_keys=False), encoding="utf-8")
    monkeypatch.setattr("content_creator.coordinator.shutil.which", lambda _: None)
    monkeypatch.setattr("content_creator.provider_setup.shutil.which", lambda _: None)

    assert main(["--workspace", str(workspace), "setup", "--json"]) == 0
    setup = json.loads(capsys.readouterr().out)

    assert setup["ready_for_content"] is False
    assert setup["milestones"][2]["status"] == "verification-required"
    assert setup["recommended_action"]["command"] == [
        "setup",
        "provider",
        "codex-native",
    ]


def test_start_does_not_offer_run_until_setup_prerequisites_are_ready(tmp_path, capsys):
    workspace = _create_workspace(tmp_path, capsys)
    request = "Write a concise LinkedIn post. No external research is required."

    assert main(["--workspace", str(workspace), "start", request]) == 0
    output = capsys.readouterr().out

    assert "Proposed content plan" in output
    assert "Finish setup before creating this piece" in output
    assert "Next command: content-creator run" not in output
    assert "content-creator setup" in output


def test_coordinator_context_exposes_the_same_setup_snapshot(tmp_path, capsys):
    workspace = _create_workspace(tmp_path, capsys)

    assert main(["--workspace", str(workspace), "coordinator", "context"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["setup"]["recommended_action"] == result["recommended_action"]
    assert result["setup"]["milestones"][1]["status"] == "choice-required"


def test_fake_provider_golden_path_reaches_reviewable_draft_within_budget(
    tmp_path, capsys, monkeypatch
):
    started = time.monotonic()
    workspace = _create_workspace(tmp_path, capsys)
    assert main(["--workspace", str(workspace), "setup", "starter"]) == 0
    capsys.readouterr()

    class VerifiedCodex:
        def verify(self):
            return {"authentication": "chatgpt"}

    provider_get = ProviderRegistry.get
    monkeypatch.setattr(
        "content_creator.provider_setup.ProviderRegistry.get",
        lambda self, name: VerifiedCodex(),
    )
    monkeypatch.setattr("content_creator.provider_setup.shutil.which", lambda _: "/bin/codex")
    monkeypatch.setattr("content_creator.coordinator.shutil.which", lambda _: "/bin/codex")
    assert main(["--workspace", str(workspace), "setup", "provider", "codex-native"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(ProviderRegistry, "get", provider_get)

    fake = FakeProvider({"writer": [valid_draft()], "critic": [passing_critique()]})

    class GoldenPathOrchestrator:
        def __init__(self, root):
            self.delegate = Orchestrator(root, registry=ProviderRegistry({"codex-native": fake}))
            self.runner = self.delegate.runner

        def plan_request(self, request, provider=None):
            return self.delegate.plan_request(request, provider)

        def start(self, order, **kwargs):
            return self.delegate.start(order, **kwargs)

    monkeypatch.setattr(cli, "Orchestrator", GoldenPathOrchestrator)
    request = "Write a useful LinkedIn post. No external research is required."
    assert main(["--workspace", str(workspace), "run", request]) == 0
    result = json.loads(capsys.readouterr().out)

    assert result["status"] == "ready"
    assert time.monotonic() - started < 600
