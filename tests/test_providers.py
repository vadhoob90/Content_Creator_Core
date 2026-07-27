from types import SimpleNamespace

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


def request(provider):
    return ModelRequest(
        role="critic",
        system="system",
        user="user",
        selection=ModelSelection(
            provider=provider,
            profile="balanced",
            model="test-model",
            reasoning_effort="medium" if provider == "openai" else None,
            capabilities=["structured_output", "web_search"],
        ),
        output_schema={"type": "object", "properties": {}},
        tools=["web_search"],
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


def test_openai_incomplete_response_fails_closed():
    response = SimpleNamespace(
        output_text="partial", id="r1", status="incomplete", usage=None
    )
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


def test_registry_accepts_a_third_party_provider_adapter():
    provider = FakeProvider({"critic": ['{"ok": true}']})
    registry = ProviderRegistry()

    registry.register("local-llm", provider)

    assert registry.get("local-llm") is provider
