import builtins
import sys
from types import ModuleType, SimpleNamespace

import pytest

from content_creator.domain import ModelRequest, ModelSelection
from content_creator.providers.base import ProviderError
from content_creator.providers.bedrock import BedrockProvider


class Capture:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return self.response


def request(*, tools=None):
    return ModelRequest(
        role="writer",
        system="system",
        user="user",
        selection=ModelSelection(
            provider="bedrock",
            profile="balanced",
            model="global.anthropic.claude-sonnet-5",
            capabilities=["structured_output"],
        ),
        output_schema={
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        },
        tools=tools or [],
    )


def test_bedrock_constructs_the_sdk_client_with_bounded_retries(monkeypatch):
    client = SimpleNamespace()
    options = []

    def construct(**kwargs):
        options.append(kwargs)
        return client

    anthropic = ModuleType("anthropic")
    anthropic.AnthropicBedrock = construct
    monkeypatch.setitem(sys.modules, "anthropic", anthropic)

    assert BedrockProvider().client is client
    assert options == [{"max_retries": 2}]


def test_bedrock_explains_the_missing_optional_dependency(monkeypatch):
    real_import = builtins.__import__

    def reject_anthropic(name, *args, **kwargs):
        if name == "anthropic":
            raise ImportError("anthropic unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_anthropic)

    with pytest.raises(ProviderError, match=r"pip install -e '.\[bedrock\]'"):
        BedrockProvider()


def test_bedrock_reuses_messages_contract_with_prompt_validated_json():
    response = SimpleNamespace(
        content=[SimpleNamespace(type="text", text='{"ok":true}')],
        id="bedrock-message",
        stop_reason="end_turn",
        usage=SimpleNamespace(input_tokens=2, output_tokens=3),
    )
    capture = Capture(response)

    result = BedrockProvider(SimpleNamespace(messages=capture)).generate(request())

    assert capture.kwargs["model"] == "global.anthropic.claude-sonnet-5"
    assert "output_config" not in capture.kwargs
    assert "STRUCTURED OUTPUT" in capture.kwargs["system"]
    assert result.provider == "bedrock"
    assert result.text == '{"ok":true}'


def test_bedrock_rejects_unsupported_server_side_web_search():
    provider = BedrockProvider(SimpleNamespace(messages=SimpleNamespace()))

    with pytest.raises(ProviderError, match="does not support server-side web search"):
        provider.generate(request(tools=["web_search"]))


def test_bedrock_transport_failures_name_the_selected_provider():
    client = SimpleNamespace(
        messages=SimpleNamespace(
            create=lambda **_: (_ for _ in ()).throw(RuntimeError("transport unavailable"))
        )
    )

    with pytest.raises(ProviderError, match="Bedrock request failed: transport unavailable"):
        BedrockProvider(client).generate(request())


def test_bedrock_verify_uses_the_standard_aws_credential_chain(monkeypatch):
    sessions = []

    class Session:
        def __init__(self, **kwargs):
            sessions.append(kwargs)

        def get_credentials(self):
            return SimpleNamespace(method="shared-credentials-file")

    boto3 = ModuleType("boto3")
    boto3.Session = Session
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    provider = BedrockProvider(
        SimpleNamespace(
            api_key=None,
            aws_profile="content-author",
            aws_region="eu-west-2",
        )
    )

    assert provider.verify() == {
        "authentication": "shared-credentials-file",
        "region": "eu-west-2",
    }
    assert sessions == [{"profile_name": "content-author", "region_name": "eu-west-2"}]


def test_bedrock_verify_accepts_an_aws_bedrock_bearer_token():
    provider = BedrockProvider(
        SimpleNamespace(
            api_key="configured",
            aws_profile=None,
            aws_region="us-east-1",
        )
    )

    assert provider.verify() == {
        "authentication": "bedrock-api-key",
        "region": "us-east-1",
    }


def test_bedrock_verify_fails_when_the_credential_chain_is_empty(monkeypatch):
    class Session:
        def __init__(self, **kwargs):
            self.options = kwargs

        def get_credentials(self):
            return None

    boto3 = ModuleType("boto3")
    boto3.Session = Session
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    provider = BedrockProvider(
        SimpleNamespace(api_key=None, aws_profile=None, aws_region="eu-west-2")
    )

    with pytest.raises(ProviderError, match="No AWS credentials found"):
        provider.verify()


def test_bedrock_verify_reports_credential_chain_errors(monkeypatch):
    class Session:
        def __init__(self, **kwargs):
            del kwargs
            raise RuntimeError("profile is invalid")

    boto3 = ModuleType("boto3")
    boto3.Session = Session
    monkeypatch.setitem(sys.modules, "boto3", boto3)
    provider = BedrockProvider(
        SimpleNamespace(api_key=None, aws_profile="missing", aws_region="eu-west-2")
    )

    with pytest.raises(ProviderError, match="AWS credential verification failed"):
        provider.verify()


def test_bedrock_verify_explains_missing_aws_dependencies(monkeypatch):
    real_import = builtins.__import__

    def reject_boto3(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("boto3 unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_boto3)
    provider = BedrockProvider(
        SimpleNamespace(api_key=None, aws_profile=None, aws_region="eu-west-2")
    )

    with pytest.raises(ProviderError, match=r"pip install -e '.\[bedrock\]'"):
        provider.verify()
