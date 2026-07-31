import pytest
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


def test_default_provider_can_be_selected_for_current_shell(project, monkeypatch):
    monkeypatch.setenv("CONTENT_CREATOR_PROVIDER", "openai")
    assert Configuration(project).default_provider == "openai"


def test_native_provider_can_be_selected_for_current_shell(project, monkeypatch):
    monkeypatch.setenv("CONTENT_CREATOR_PROVIDER", "codex-native")
    assert Configuration(project).default_provider == "codex-native"


def test_default_provider_requires_deliberate_selection(project, monkeypatch):
    monkeypatch.delenv("CONTENT_CREATOR_PROVIDER", raising=False)
    path = project / "config" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["defaults"]["provider"] = None
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="No provider selected"):
        _ = Configuration(project).default_provider


def test_workspace_can_persist_an_explicit_provider(project, monkeypatch):
    monkeypatch.delenv("CONTENT_CREATOR_PROVIDER", raising=False)
    path = project / "config" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["defaults"]["provider"] = None
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    (project / "content-creator.yaml").write_text(
        yaml.safe_dump({"provider": {"default": "claude-native"}}),
        encoding="utf-8",
    )

    assert Configuration(project).default_provider == "claude-native"


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


def test_diagnostic_policy_has_safe_defaults(project):
    policy = Configuration(project).diagnostic_policy

    assert policy == {
        "enabled": True,
        "max_attempts": 2,
        "defer_recovered_until_publication": True,
    }


def test_diagnostic_policy_rejects_unbounded_retries(project):
    path = project / "content-creator.yaml"
    data = yaml.safe_load(path.read_text()) if path.exists() else {}
    data["diagnostics"] = {"max_attempts": 10}
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="from 1 to 3"):
        _ = Configuration(project).diagnostic_policy


def test_voice_assessment_is_off_by_default(project):
    assert Configuration(project).voice_assessment_policy == {
        "enabled": False,
        "minimum_sources": 20,
        "minimum_draft_words": 100,
        "outlier_iqr_multiplier": 1.5,
        "max_reported_outliers": 8,
    }


def test_voice_assessment_policy_validates_bounds(project):
    path = project / "content-creator.yaml"
    path.write_text(
        yaml.safe_dump({"voice_assessment": {"minimum_sources": 2}}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="minimum_sources"):
        _ = Configuration(project).voice_assessment_policy
