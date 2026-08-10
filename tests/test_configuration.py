import pytest
import yaml

from content_creator.configuration import Configuration, ConfigurationError
from content_creator.domain import Critique
from content_creator.prompting import PromptAssembler
from content_creator.providers import FakeProvider, ProviderRegistry
from content_creator.runner import AgentOutputError, AgentRunner, AgentRunOptions


def _write_workspace_config(project, section, value):
    path = project / "content-creator.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}
    data[section] = value
    path.write_text(yaml.safe_dump(data), encoding="utf-8")


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
        Configuration(project).selection("writer-post", required_capabilities={"unsupported_tool"})
    except ConfigurationError as exc:
        assert "unsupported_tool" in str(exc)
    else:
        raise AssertionError("Expected ConfigurationError")


def test_anthropic_web_search_tool_can_target_an_older_gateway(project):
    path = project / "config" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["anthropic"]["web_search_tool"] = "web_search_20250305"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    assert Configuration(project).anthropic_web_search_tool == "web_search_20250305"


def test_anthropic_web_search_tool_rejects_unknown_versions(project):
    path = project / "config" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["anthropic"]["web_search_tool"] = "web_search_latest"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")

    with pytest.raises(ConfigurationError, match="anthropic.web_search_tool"):
        _ = Configuration(project).anthropic_web_search_tool


def test_bedrock_model_profiles_support_structured_work_but_not_live_search(project):
    configuration = Configuration(project)

    selected = configuration.selection(
        "writer-post",
        provider="bedrock",
        required_capabilities={"structured_output"},
    )

    assert selected.model == "global.anthropic.claude-sonnet-5"
    assert selected.capabilities == ["structured_output"]
    with pytest.raises(ConfigurationError, match="web_search"):
        configuration.selection(
            "researcher-light",
            provider="bedrock",
            required_capabilities={"structured_output", "web_search"},
        )


def test_configuration_reader_rejects_missing_and_non_mapping_yaml(tmp_path):
    with pytest.raises(ConfigurationError, match="Missing configuration"):
        Configuration._read_yaml(tmp_path / "missing.yaml")

    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("- list\n- not-a-mapping\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="Expected a mapping"):
        Configuration._read_yaml(invalid)


def test_default_provider_rejects_unknown_provider(project, monkeypatch):
    monkeypatch.setenv("CONTENT_CREATOR_PROVIDER", "unregistered")

    with pytest.raises(ConfigurationError, match="Unknown default provider"):
        _ = Configuration(project).default_provider


def test_model_selector_rejects_missing_role_and_profile(project):
    configuration = Configuration(project)
    with pytest.raises(ConfigurationError, match="No model profile configured"):
        configuration.selection("unknown-role")
    with pytest.raises(ConfigurationError, match="Unknown provider/profile combination"):
        configuration.selection("writer-post", profile="unknown-profile")


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
            options=AgentRunOptions(output_model=Critique),
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


def test_statistical_voice_score_is_off_by_default(project):
    assert Configuration(project).statistical_voice_score_policy == {
        "enabled": False,
        "method": "deterministic",
        "minimum_sources": 20,
        "minimum_draft_words": 100,
        "outlier_iqr_multiplier": 1.5,
        "max_reported_outliers": 8,
    }


def test_statistical_voice_score_policy_validates_bounds(project):
    path = project / "content-creator.yaml"
    path.write_text(
        yaml.safe_dump({"statistical_voice_score": {"minimum_sources": 2}}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="minimum_sources"):
        _ = Configuration(project).statistical_voice_score_policy


def test_statistical_voice_score_rejects_unknown_method(project):
    path = project / "content-creator.yaml"
    path.write_text(
        yaml.safe_dump({"statistical_voice_score": {"method": "automatic-ml"}}),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError, match="deterministic or ml"):
        _ = Configuration(project).statistical_voice_score_policy


def test_legacy_voice_assessment_configuration_is_mapped(project):
    path = project / "content-creator.yaml"
    path.write_text(
        yaml.safe_dump({"voice_assessment": {"enabled": True, "mode": "statistical"}}),
        encoding="utf-8",
    )

    policy = Configuration(project).statistical_voice_score_policy

    assert policy["enabled"] is True
    assert policy["method"] == "deterministic"


@pytest.mark.parametrize(
    ("section", "attribute", "message"),
    [
        ("provider", "default_provider", "provider configuration must be a mapping"),
        ("perspective", "perspective_policy", "perspective configuration must be a mapping"),
        (
            "publication_provenance",
            "publication_provenance_policy",
            "publication_provenance configuration must be a mapping",
        ),
        ("coordinator", "coordinator_policy", "coordinator configuration must be a mapping"),
        ("diagnostics", "diagnostic_policy", "diagnostics configuration must be a mapping"),
        (
            "statistical_voice_score",
            "statistical_voice_score_policy",
            "statistical_voice_score configuration must be a mapping",
        ),
    ],
)
def test_configuration_sections_reject_non_mapping_values(project, section, attribute, message):
    _write_workspace_config(project, section, "invalid")

    with pytest.raises(ConfigurationError, match=message):
        getattr(Configuration(project), attribute)


def test_perspective_policy_rejects_unknown_mode(project):
    _write_workspace_config(project, "perspective", {"mode": "implicit"})

    with pytest.raises(ConfigurationError, match="explicit, automatic, or disabled"):
        _ = Configuration(project).perspective_policy


@pytest.mark.parametrize("directory", ["/tmp/receipts", "../receipts", "."])
def test_publication_receipts_must_stay_inside_workspace(project, directory):
    _write_workspace_config(
        project,
        "publication_provenance",
        {"receipts_directory": directory},
    )

    with pytest.raises(ConfigurationError, match="must stay inside the workspace"):
        _ = Configuration(project).publication_provenance_policy


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("policy", "best-effort", "publication_provenance.policy"),
        ("semantic_review", "all", "publication_provenance.semantic_review"),
    ],
)
def test_publication_provenance_rejects_unknown_policy_values(project, setting, value, message):
    _write_workspace_config(project, "publication_provenance", {setting: value})

    with pytest.raises(ConfigurationError, match=message):
        _ = Configuration(project).publication_provenance_policy


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("external_publication", "enabled", "external_publication must be disabled"),
        ("ask_before_voice_change", "yes", "ask_before_voice_change must be a boolean"),
        ("require_final_review", 1, "require_final_review must be a boolean"),
    ],
)
def test_coordinator_policy_rejects_unsafe_values(project, setting, value, message):
    _write_workspace_config(project, "coordinator", {setting: value})

    with pytest.raises(ConfigurationError, match=message):
        _ = Configuration(project).coordinator_policy


@pytest.mark.parametrize(
    ("setting", "value", "message"),
    [
        ("enabled", "yes", "diagnostics.enabled must be a boolean"),
        ("max_attempts", True, "max_attempts must be an integer"),
        (
            "defer_recovered_until_publication",
            False,
            "defer_recovered_until_publication must be true",
        ),
    ],
)
def test_diagnostic_policy_rejects_unsafe_values(project, setting, value, message):
    _write_workspace_config(project, "diagnostics", {setting: value})

    with pytest.raises(ConfigurationError, match=message):
        _ = Configuration(project).diagnostic_policy


@pytest.mark.parametrize(
    ("setting", "value"),
    [
        ("minimum_draft_words", 24),
        ("max_reported_outliers", 51),
    ],
)
def test_statistical_voice_score_rejects_out_of_range_integer_settings(project, setting, value):
    _write_workspace_config(project, "statistical_voice_score", {setting: value})

    with pytest.raises(ConfigurationError, match=setting):
        _ = Configuration(project).statistical_voice_score_policy


@pytest.mark.parametrize(
    ("settings", "message"),
    [
        ({"enabled": "yes"}, "enabled must be a boolean"),
        ({"outlier_iqr_multiplier": True}, "must be a number"),
        ({"outlier_iqr_multiplier": 5.1}, "must be from 1.0 to 5.0"),
    ],
)
def test_statistical_voice_score_rejects_unsafe_scalar_settings(project, settings, message):
    _write_workspace_config(project, "statistical_voice_score", settings)

    with pytest.raises(ConfigurationError, match=message):
        _ = Configuration(project).statistical_voice_score_policy


def test_legacy_voice_assessment_rejects_unknown_mode(project):
    _write_workspace_config(project, "voice_assessment", {"mode": "hybrid"})

    with pytest.raises(ConfigurationError, match="mode must be statistical or ml"):
        _ = Configuration(project).statistical_voice_score_policy
