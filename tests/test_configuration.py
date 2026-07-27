import yaml

from content_creator.configuration import Configuration, ConfigurationError
from content_creator.domain import Critique
from content_creator.prompting import PromptAssembler
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.runner import AgentOutputError, AgentRunner


def test_model_selector_uses_first_capable_candidate(project):
    path = project / "config" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["anthropic"]["profiles"]["balanced"]["candidates"] = [
        {"model": "fast-but-no-search", "capabilities": ["structured_output"]},
        {
            "model": "search-capable",
            "capabilities": ["structured_output", "web_search"],
        },
        {
            "model": "also-capable",
            "capabilities": ["structured_output", "web_search"],
        },
    ]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    selected = Configuration(project).selection(
        "writer-post", required_capabilities={"structured_output", "web_search"}
    )
    assert selected.model == "search-capable"


def test_model_selector_fails_closed_when_capability_is_missing(project):
    try:
        Configuration(project).selection(
            "writer-post", required_capabilities={"unsupported_tool"}
        )
    except ConfigurationError as exc:
        assert "unsupported_tool" in str(exc)
    else:
        raise AssertionError("Expected ConfigurationError")


def test_runner_rejects_invalid_structured_output(project):
    runner = AgentRunner(
        Configuration(project),
        ProviderRegistry({"anthropic": FakeProvider({"critic": ["not-json"]})}),
        PromptAssembler(project),
    )
    try:
        runner.run(
            role="critic",
            role_key="critic-post",
            instruction="Review",
            payload={"draft": "x"},
            output_model=Critique,
        )
    except AgentOutputError as exc:
        assert "invalid structured output" in str(exc)
    else:
        raise AssertionError("Expected AgentOutputError")
