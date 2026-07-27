import json

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


def test_doctor_fails_when_a_required_asset_is_missing(project, capsys):
    (project / "profiles" / "default" / "voice.md").unlink()

    assert main(["--root", str(project), "doctor"]) == 1
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "error"
    assert output["checks"]["default_voice"] is False
