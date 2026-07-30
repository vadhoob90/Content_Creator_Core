import json

import pytest
import yaml

import content_creator.cli as cli
from content_creator.cli import main
from content_creator.configuration import ConfigurationError


def test_doctor_validates_repository(capsys):
    assert main(["doctor"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["status"] == "ok"
    assert output["checks"]["content_packs"] == [
        "general-text",
        "linkedin-article",
        "linkedin-post",
    ]
    assert output["checks"]["default_voice"] is True


def test_default_help_is_calm_and_advanced_commands_remain_discoverable(capsys):
    parser = cli.build_parser()
    with pytest.raises(SystemExit) as result:
        parser.parse_args(["--help"])
    assert result.value.code == 0
    help_text = capsys.readouterr().out
    assert "start" in help_text
    assert "overview" in help_text
    assert "==SUPPRESS==" not in help_text
    assert "voice               " not in help_text

    assert main(["advanced"]) == 0
    advanced = capsys.readouterr().out
    assert "voice" in advanced
    assert "coordinator" in advanced
    assert parser.parse_args(["voice", "list"]).command == "voice"


def test_plan_reports_provider_neutral_work_order(capsys):
    assert (
        main(
            [
                "plan",
                "Write a LinkedIn article with deep research",
                "--provider",
                "anthropic",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)

    assert output["provider"] == "anthropic"
    assert output["content_pack"] == "linkedin-article"
    assert output["research_depth"] == "deep"


def test_doctor_uses_packaged_default_when_workspace_asset_is_missing(
    project, capsys
):
    (project / "profiles" / "default" / "voice.md").unlink()

    assert main(["--root", str(project), "doctor"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "ok"
    assert output["checks"]["default_voice"] is True


def test_init_provider_verify_and_pack_create(project, capsys, monkeypatch):
    assert main(["--root", str(project), "init"]) == 0
    initialised = json.loads(capsys.readouterr().out)
    assert initialised["agents"]["status"]["complete"] is True
    assert ".agents/skills/content-creator/SKILL.md" in initialised["skills"]["created"]
    assert ".agents/skills/voice-builder/SKILL.md" in initialised["skills"]["created"]
    assert (project / "agents" / "writer.md").exists()
    assert (project / ".agents" / "skills" / "content-creator" / "SKILL.md").exists()
    assert (project / "learnings" / "memory.json").exists()
    assert (project / "content-creator.yaml").exists()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    assert main(["--root", str(project), "provider", "verify", "openai"]) == 0
    capsys.readouterr()
    assert (
        main(
            [
                "--root",
                str(project),
                "pack",
                "create",
                "internal-briefing",
                "--extends",
                "general-text",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert (project / "packs" / "internal-briefing" / "validators.yaml").exists()


def test_provider_select_persists_workspace_choice(project, capsys):
    assert (
        main(
            [
                "--root",
                str(project),
                "provider",
                "select",
                "codex-native",
            ]
        )
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    configuration = yaml.safe_load(
        (project / "content-creator.yaml").read_text(encoding="utf-8")
    )

    assert output["provider"] == "codex-native"
    assert configuration["provider"]["default"] == "codex-native"


def test_agent_scaffold_preserves_repository_customisation(tmp_path, capsys):
    agents = tmp_path / "agents"
    agents.mkdir()
    writer = agents / "writer.md"
    writer.write_text("# Custom writer", encoding="utf-8")

    assert main(["--root", str(tmp_path), "agents", "scaffold"]) == 0
    result = json.loads(capsys.readouterr().out)

    assert writer.read_text(encoding="utf-8") == "# Custom writer"
    assert "writer.md" in result["preserved"]
    assert result["status"]["complete"] is True

    assert main(["--root", str(tmp_path), "agents", "diff-template"]) == 0
    difference = json.loads(capsys.readouterr().out)
    assert "writer.md" in difference["changed"]


def test_configuration_errors_are_reported_without_a_traceback(
    project, capsys, monkeypatch
):
    class FailingOrchestrator:
        def __init__(self, root):
            self.root = root

        def plan_request(self, request, provider=None):
            raise ConfigurationError("No provider selected")

    monkeypatch.setattr(cli, "Orchestrator", FailingOrchestrator)

    assert main(["--root", str(project), "plan", "Ambiguous request"]) == 8
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "status": "error",
        "error_type": "ConfigurationError",
        "error": "No provider selected",
    }


def test_yaml_brief_reaches_run_command(project, tmp_path, capsys, monkeypatch):
    brief = tmp_path / "brief.yaml"
    brief.write_text(
        """
request: Explain a useful system
topic: Useful system
voice_id: default
content_pack: general-text
format: text
research:
  depth: none
  source: none
""".strip(),
        encoding="utf-8",
    )

    class FakeOrchestrator:
        def __init__(self, root):
            self.root = root

        def start(self, order):
            return order

    monkeypatch.setattr(cli, "Orchestrator", FakeOrchestrator)
    assert (
        main(["--root", str(project), "run", "--brief", str(brief)])
        == 0
    )
    output = json.loads(capsys.readouterr().out)
    assert output["content_pack"] == "general-text"
    assert output["research_depth"] == "none"
