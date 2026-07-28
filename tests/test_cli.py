import json

import content_creator.cli as cli
from content_creator.cli import main


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
    capsys.readouterr()
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
