from types import SimpleNamespace

import pytest

from content_creator.domain import ModelRequest, ModelSelection, PlanningDecision
from content_creator.providers.anthropic import AnthropicProvider
from content_creator.providers.base import ProviderError


def model_request(schema):
    return ModelRequest(
        role="briefing-agent",
        system="role contract",
        user="create a work order",
        selection=ModelSelection(
            provider="anthropic",
            profile="fast",
            model="test-model",
            capabilities=["structured_output"],
        ),
        output_schema=schema,
        tools=[],
    )


def response(text='{"ok":true}'):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        id="message-1",
        stop_reason="end_turn",
        usage=None,
    )


class Capture:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def provider(capture):
    return AnthropicProvider(SimpleNamespace(messages=capture))


def test_anthropic_normalises_supported_schema_for_grammar_mode():
    schema = {
        "type": "object",
        "properties": {
            "score": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            }
        },
        "required": ["score"],
    }
    capture = Capture([response()])

    provider(capture).generate(model_request(schema))

    strict = capture.calls[0]["output_config"]["format"]["schema"]
    assert strict["additionalProperties"] is False
    assert "minimum" not in strict["properties"]["score"]
    assert "maximum" not in strict["properties"]["score"]
    assert "minimum" in strict["properties"]["score"]["description"]


def test_anthropic_uses_prompt_json_for_current_planning_schema():
    capture = Capture([response('{"needs_clarification":true}')])

    provider(capture).generate(model_request(PlanningDecision.model_json_schema()))

    call = capture.calls[0]
    assert "output_config" not in call
    assert "Return only valid JSON" in call["system"]
    assert "pack_options" in call["system"]


def test_anthropic_uses_prompt_json_above_documented_optional_parameter_limit():
    properties = {f"field_{index}": {"type": "string"} for index in range(25)}
    capture = Capture([response()])

    provider(capture).generate(
        model_request({"type": "object", "properties": properties, "required": []})
    )

    assert "output_config" not in capture.calls[0]
    assert "field_24" in capture.calls[0]["system"]


@pytest.mark.parametrize(
    "message",
    [
        "Schema is too complex for compilation",
        "compiled grammar is too large",
        "Grammar compilation timed out",
    ],
)
def test_anthropic_retries_grammar_complexity_failures_with_prompt_json(message):
    capture = Capture([RuntimeError(message), response()])
    schema = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
        "required": ["answer"],
    }

    result = provider(capture).generate(model_request(schema))

    assert result.text == '{"ok":true}'
    assert "output_config" in capture.calls[0]
    assert "output_config" not in capture.calls[1]
    assert "Return only valid JSON" in capture.calls[1]["system"]


def test_anthropic_does_not_retry_unrelated_transport_failures():
    capture = Capture([RuntimeError("transport unavailable")])

    with pytest.raises(ProviderError, match="Anthropic request failed: transport unavailable"):
        provider(capture).generate(model_request({"type": "object", "properties": {}}))

    assert len(capture.calls) == 1


def test_anthropic_reports_failed_prompt_json_retry_with_stable_boundary():
    capture = Capture(
        [
            RuntimeError("Schema is too complex for compilation"),
            RuntimeError("transport unavailable"),
        ]
    )

    with pytest.raises(
        ProviderError,
        match="Anthropic prompt-based structured-output fallback failed: transport unavailable",
    ):
        provider(capture).generate(model_request({"type": "object", "properties": {}}))


def test_anthropic_uses_foundry_client_for_legacy_foundry_base_url(monkeypatch):
    direct_calls = []
    foundry_calls = []
    foundry_client = object()
    monkeypatch.setenv(
        "ANTHROPIC_BASE_URL",
        "https://example-resource.services.ai.azure.com/anthropic",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "foundry-test-key")
    monkeypatch.delenv("ANTHROPIC_FOUNDRY_BASE_URL", raising=False)
    monkeypatch.setenv("ANTHROPIC_FOUNDRY_RESOURCE", "wrong-resource")
    monkeypatch.setattr(
        "anthropic.Anthropic",
        lambda **kwargs: direct_calls.append(kwargs),
    )
    monkeypatch.setattr(
        "anthropic.AnthropicFoundry",
        lambda **kwargs: foundry_calls.append(kwargs) or foundry_client,
    )

    instance = AnthropicProvider()

    assert instance.client is foundry_client
    assert direct_calls == []
    assert foundry_calls == [
        {
            "resource": "example-resource",
            "api_key": "foundry-test-key",
            "max_retries": 2,
        }
    ]
