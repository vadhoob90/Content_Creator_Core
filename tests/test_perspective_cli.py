import json

import content_creator.cli as cli
from content_creator.cli import main


def test_cli_creates_verifies_approves_and_lists_perspective(project, capsys):
    assert (
        main(
            [
                "--root",
                str(project),
                "perspective",
                "create",
                "--voice",
                "default",
                "--context",
                "legal-training",
                "--statement",
                "Training should teach recognition and escalation.",
                "--type",
                "principle",
                "--topic",
                "training",
                "--qualification",
                "Mandatory procedures still require recall.",
                "--evidence",
                "Direct author interview",
            ]
        )
        == 0
    )
    candidate = json.loads(capsys.readouterr().out)
    assert candidate["status"] == "awaiting_approval"

    assert (
        main(
            [
                "--root",
                str(project),
                "perspective",
                "verify",
                "--voice",
                "default",
                "--context",
                "legal-training",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["valid"]

    assert (
        main(
            [
                "--root",
                str(project),
                "perspective",
                "approve",
                "--voice",
                "default",
                "--context",
                "legal-training",
                "--approved-by",
                "Owner",
            ]
        )
        == 0
    )
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["activated_version"] == "1.0.0"

    assert (
        main(
            [
                "--root",
                str(project),
                "perspective",
                "list",
                "--voice",
                "default",
            ]
        )
        == 0
    )
    contexts = json.loads(capsys.readouterr().out)
    assert contexts["legal-training"]["status"] == "active"


def test_run_cli_passes_perspective_and_author_contribution(project, capsys, monkeypatch):
    class FakeOrchestrator:
        def __init__(self, root):
            self.root = root

        def start(self, order):
            return order

    monkeypatch.setattr(cli, "Orchestrator", FakeOrchestrator)
    assert (
        main(
            [
                "--root",
                str(project),
                "run",
                "Create training material",
                "--pack",
                "general-text",
                "--perspective-context",
                "legal-training",
                "--thesis",
                "Recognition matters more than memorisation.",
                "--author-supplied",
            ]
        )
        == 0
    )
    order = json.loads(capsys.readouterr().out)
    assert order["perspective_context"] == "legal-training"
    assert order["author_contribution"]["supplied_by_author"]
    assert order["author_contribution"]["thesis"].startswith("Recognition")
