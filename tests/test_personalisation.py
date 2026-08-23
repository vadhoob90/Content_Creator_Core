import json

from content_creator.cli import main
from content_creator.voice_upgrade.epochs import epoch_path
from content_creator.voices import VoiceRegistry


def _memory(records):
    return json.dumps({"version": 1, "records": records}, indent=2)


def test_personalisation_explains_agents_learning_voice_and_paths(project, capsys):
    writer = project / "agents" / "writer.md"
    writer.write_text(
        writer.read_text() + "\n\nUse Bharath's editorial boundary.",
        encoding="utf-8",
    )
    VoiceRegistry(project).activate_starter(
        "bharath-linkedin",
        "Bharath Vadhoola — LinkedIn",
        "Bharath Vadhoola",
        "Bharath Vadhoola",
        ["linkedin-post"],
    )
    voice_memory = epoch_path(project, "bharath-linkedin", "1.0.0")
    voice_memory.parent.mkdir(parents=True, exist_ok=True)
    voice_memory.write_text(
        _memory(
            [
                {
                    "id": "writer-active",
                    "role": "writer",
                    "status": "active",
                    "scope": "targeted revisions",
                    "principle": "Preserve approved wording during targeted revisions.",
                    "evidence": "Explicit author feedback.",
                },
                {
                    "id": "critic-provisional",
                    "role": "critic",
                    "status": "provisional",
                    "scope": "general",
                    "principle": "Check whether the opening is too abstract.",
                    "evidence": "Inferred from one revision.",
                },
            ]
        ),
        encoding="utf-8",
    )

    assert main(["--root", str(project), "personalisation", "show", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    writer_agent = next(item for item in report["agents"] if item["role"] == "writer")
    voice = next(item for item in report["voices"] if item["voice_id"] == "bharath-linkedin")

    assert writer_agent["personalisation"] == "customised"
    assert writer_agent["receives_voice"] is True
    assert writer_agent["receives_learnings"] is True
    assert voice["active"]["version"] == "1.0.0"
    assert voice["candidate"]["status"] == "none"
    assert voice["learnings"]["counts"] == {
        "writer": {"active": 1},
        "critic": {"provisional": 1},
    }
    assert report["prompt_layers"][-1]["layer"] == "rubrics-and-pack-instructions"
    assert report["navigation"]["guide"] == "PERSONALISATION.md"

    assert main(["--root", str(project), "personalisation", "show"]) == 0
    text = capsys.readouterr().out
    assert "How this workspace is personalised" in text
    assert "writer: customised" in text
    assert "Preserve approved wording during targeted revisions." in text
    assert "Check whether the opening is too abstract." not in text
    assert "Bharath Vadhoola — LinkedIn" in text


def test_overview_and_help_signpost_personalisation(project, capsys):
    assert main(["--root", str(project), "overview"]) == 0
    assert "content-creator personalisation show" in capsys.readouterr().out

    parser = main.__globals__["runtime"].build_parser()
    try:
        parser.parse_args(["--help"])
    except SystemExit as error:
        assert error.code == 0
    assert "personalisation" in capsys.readouterr().out
