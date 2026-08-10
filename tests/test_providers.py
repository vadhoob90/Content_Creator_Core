import builtins
from types import SimpleNamespace

import pytest
import yaml

from content_creator.domain import ModelRequest, ModelSelection
from content_creator.providers.anthropic import AnthropicProvider
from content_creator.providers.base import ProviderError
from content_creator.providers.fake import FakeProvider
from content_creator.providers.openai import OpenAIProvider
from content_creator.providers.registry import ProviderRegistry


class Capture:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def request(provider, *, structured=True, search=True, reasoning=True):
    return ModelRequest(
        role="critic",
        system="system",
        user="user",
        selection=ModelSelection(
            provider=provider,
            profile="balanced",
            model="test-model",
            reasoning_effort="medium" if provider == "openai" and reasoning else None,
            capabilities=["structured_output", "web_search"],
        ),
        output_schema={"type": "object", "properties": {}} if structured else None,
        tools=["web_search"] if search else [],
    )


def test_openai_adapter_translates_normalized_request():
    response = SimpleNamespace(
        output_text='{"ok":true}',
        id="r1",
        status="completed",
        usage=SimpleNamespace(input_tokens=2, output_tokens=3),
    )
    capture = Capture(response)
    client = SimpleNamespace(responses=capture)
    result = OpenAIProvider(client).generate(request("openai"))
    assert capture.kwargs["instructions"] == "system"
    assert capture.kwargs["reasoning"] == {"effort": "medium"}
    assert capture.kwargs["text"]["format"]["type"] == "json_schema"
    assert capture.kwargs["tools"] == [{"type": "web_search"}]
    assert result.text == '{"ok":true}'


@pytest.mark.usefixtures("anthropic_sdk_stub")
def test_anthropic_adapter_translates_normalized_request():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"ok":true}')],
        id="m1",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=2, output_tokens=3),
    )
    capture = Capture(response)
    client = SimpleNamespace(messages=capture)
    result = AnthropicProvider(client).generate(request("anthropic"))
    assert capture.kwargs["system"] == "system"
    assert capture.kwargs["messages"] == [{"role": "user", "content": "user"}]
    assert capture.kwargs["output_config"]["format"]["type"] == "json_schema"
    assert capture.kwargs["tools"][0]["name"] == "web_search"
    assert result.text == '{"ok":true}'


@pytest.mark.usefixtures("anthropic_sdk_stub")
def test_anthropic_adapter_uses_configured_web_search_tool():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="researched")],
        stop_reason="end_turn",
        usage=None,
    )
    capture = Capture(response)

    AnthropicProvider(
        SimpleNamespace(messages=capture),
        web_search_tool="web_search_20250305",
    ).generate(request("anthropic", structured=False))

    assert capture.kwargs["tools"] == [{"type": "web_search_20250305", "name": "web_search"}]


def test_anthropic_adapter_rejects_unknown_web_search_tool():
    with pytest.raises(ProviderError, match="Unsupported Anthropic web-search tool"):
        AnthropicProvider(object(), web_search_tool="web_search_latest")


def test_openai_incomplete_response_fails_closed():
    response = SimpleNamespace(output_text="partial", id="r1", status="incomplete", usage=None)
    client = SimpleNamespace(responses=Capture(response))
    try:
        OpenAIProvider(client).generate(request("openai"))
    except ProviderError as exc:
        assert "incomplete" in str(exc)
    else:
        raise AssertionError("Expected ProviderError")


def test_anthropic_token_limit_fails_closed():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="partial")],
        id="m1",
        stop_reason="max_tokens",
        usage=None,
    )
    client = SimpleNamespace(messages=Capture(response))
    try:
        AnthropicProvider(client).generate(request("anthropic"))
    except ProviderError as exc:
        assert "token limit" in str(exc)
    else:
        raise AssertionError("Expected ProviderError")


def test_openai_minimal_response_omits_unrequested_capabilities():
    response = SimpleNamespace(output_text="plain text", status="completed")
    capture = Capture(response)

    result = OpenAIProvider(SimpleNamespace(responses=capture)).generate(
        request("openai", structured=False, search=False, reasoning=False)
    )

    assert "reasoning" not in capture.kwargs
    assert "text" not in capture.kwargs
    assert "tools" not in capture.kwargs
    assert result.raw_id is None
    assert result.input_tokens is None
    assert result.output_tokens is None


def test_anthropic_ignores_non_text_blocks_and_omits_unrequested_capabilities():
    response = SimpleNamespace(
        content=[
            SimpleNamespace(type="tool_use", text="must not be returned"),
            SimpleNamespace(type="text", text="first"),
            SimpleNamespace(type="text", text="second"),
        ],
        stop_reason="end_turn",
    )
    capture = Capture(response)

    result = AnthropicProvider(SimpleNamespace(messages=capture)).generate(
        request("anthropic", structured=False, search=False)
    )

    assert "output_config" not in capture.kwargs
    assert "tools" not in capture.kwargs
    assert result.text == "first\nsecond"
    assert result.raw_id is None
    assert result.input_tokens is None
    assert result.output_tokens is None


@pytest.mark.parametrize(
    ("provider", "client", "message"),
    [
        (
            OpenAIProvider,
            SimpleNamespace(
                responses=SimpleNamespace(
                    create=lambda **_: (_ for _ in ()).throw(RuntimeError("transport unavailable"))
                )
            ),
            "OpenAI request failed: transport unavailable",
        ),
        (
            AnthropicProvider,
            SimpleNamespace(
                messages=SimpleNamespace(
                    create=lambda **_: (_ for _ in ()).throw(RuntimeError("transport unavailable"))
                )
            ),
            "Anthropic request failed: transport unavailable",
        ),
    ],
)
def test_api_provider_transport_failures_preserve_stable_boundary(provider, client, message):
    with pytest.raises(ProviderError, match=message):
        provider(client).generate(request(provider.name))


def test_openai_empty_output_fails_closed():
    response = SimpleNamespace(output_text="", status="completed")

    with pytest.raises(ProviderError, match="no text output"):
        OpenAIProvider(SimpleNamespace(responses=Capture(response))).generate(request("openai"))


def test_anthropic_non_text_output_fails_closed():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="tool_use", text="not model text")],
        stop_reason="end_turn",
    )

    with pytest.raises(ProviderError, match="no text output"):
        AnthropicProvider(SimpleNamespace(messages=Capture(response))).generate(
            request("anthropic")
        )


def test_registry_accepts_a_third_party_provider_adapter():
    provider = FakeProvider({"critic": ['{"ok": true}']})
    registry = ProviderRegistry()

    registry.register("local-llm", provider)

    assert registry.get("local-llm") is provider


def test_registry_rejects_unknown_provider_without_mutation():
    registry = ProviderRegistry()

    with pytest.raises(ProviderError, match="Unknown provider: missing"):
        registry.get("missing")

    assert registry.providers == {}


@pytest.mark.parametrize(
    ("name", "module_name", "class_name"),
    [
        ("openai", "content_creator.providers.openai", "OpenAIProvider"),
        ("anthropic", "content_creator.providers.anthropic", "AnthropicProvider"),
        ("bedrock", "content_creator.providers.bedrock", "BedrockProvider"),
        ("codex-native", "content_creator.providers.codex_native", "CodexNativeProvider"),
        ("claude-native", "content_creator.providers.claude_native", "ClaudeNativeProvider"),
    ],
)
def test_registry_lazily_constructs_and_caches_supported_providers(
    monkeypatch,
    tmp_path,
    name,
    module_name,
    class_name,
):
    provider = FakeProvider({})
    constructed = []

    def construct(**kwargs):
        constructed.append(kwargs)
        return provider

    monkeypatch.setattr(f"{module_name}.{class_name}", construct)
    registry = ProviderRegistry(root=tmp_path)

    assert registry.get(name) is provider
    assert registry.get(name) is provider
    assert len(constructed) == 1
    if name.endswith("-native"):
        assert constructed == [{"root": tmp_path}]
    else:
        assert constructed == [{}]


def test_registry_applies_workspace_anthropic_web_search_tool(project, monkeypatch):
    path = project / "config" / "models.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["providers"]["anthropic"]["web_search_tool"] = "web_search_20250305"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    constructed = []

    def construct(**kwargs):
        constructed.append(kwargs)
        return FakeProvider({})

    monkeypatch.setattr("content_creator.providers.anthropic.AnthropicProvider", construct)

    ProviderRegistry(root=project).get("anthropic")

    assert constructed == [{"web_search_tool": "web_search_20250305"}]


@pytest.mark.parametrize(
    ("missing_module", "provider", "extra"),
    [
        ("openai", OpenAIProvider, "openai"),
        ("anthropic", AnthropicProvider, "anthropic"),
    ],
)
def test_api_provider_explains_missing_optional_dependency(
    monkeypatch,
    missing_module,
    provider,
    extra,
):
    real_import = builtins.__import__

    def reject_optional_dependency(name, *args, **kwargs):
        if name == missing_module:
            raise ImportError(f"{missing_module} unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_optional_dependency)

    with pytest.raises(ProviderError, match=rf"pip install -e '.\[{extra}\]'"):
        provider()
