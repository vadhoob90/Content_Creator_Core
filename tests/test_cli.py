import json

from content_creator.cli import main


def test_doctor_validates_repository(capsys):
    assert main(["doctor"]) == 0
    assert capsys.readouterr().out.strip() == "Configuration OK"


def test_plan_reports_provider_neutral_route(capsys):
    assert main(["plan", "--provider", "anthropic", "--complexity", "deep"]) == 0
    output = json.loads(capsys.readouterr().out)

    assert output["provider"] == "anthropic"
    assert output["tier"] == "deep"
    assert output["model_reference"] == "${ANTHROPIC_DEEP_MODEL}"
