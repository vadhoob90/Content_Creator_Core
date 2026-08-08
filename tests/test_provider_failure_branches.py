import json
import subprocess
from pathlib import Path

import pytest

from content_creator.domain import ModelRequest, ModelSelection
from content_creator.providers.base import ProviderError
from content_creator.providers.claude_native import ClaudeNativeProvider
from content_creator.providers.codex_native import CodexNativeProvider


def _request(provider, *, structured=True):
    return ModelRequest(
        role="writer",
        system="Write safely",
        user="Draft",
        selection=ModelSelection(
            provider=provider,
            profile="balanced",
            model="test-model",
            capabilities=[],
        ),
        output_schema={"type": "object", "properties": {"text": {"type": "string"}}}
        if structured
        else None,
    )


class ClaudeResult:
    def __init__(self, result):
        self.result = result

    def __call__(self, command, **_kwargs):
        if command[1:3] == ["auth", "status"]:
            auth = {
                "loggedIn": True,
                "authMethod": "claude.ai",
                "subscriptionType": "pro",
                "apiProvider": "firstParty",
            }
            return subprocess.CompletedProcess(command, 0, json.dumps(auth), "")
        return subprocess.CompletedProcess(command, 0, self.result, "")


@pytest.mark.parametrize(
    "auth",
    [
        {"loggedIn": False, "authMethod": "claude.ai", "subscriptionType": "pro"},
        {"loggedIn": True, "authMethod": "api_key", "subscriptionType": "pro"},
        {"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": None},
        {
            "loggedIn": True,
            "authMethod": "claude.ai",
            "subscriptionType": "pro",
            "apiProvider": "thirdParty",
        },
    ],
)
def test_claude_native_rejects_every_non_subscription_auth_shape(tmp_path, auth):
    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, json.dumps(auth), "")

    provider = ClaudeNativeProvider(tmp_path, "/fake/claude", runner)
    with pytest.raises(ProviderError, match="requires Claude subscription"):
        provider.verify()


def test_claude_native_rejects_malformed_auth_response(tmp_path):
    def runner(command, **_kwargs):
        return subprocess.CompletedProcess(command, 0, "not-json", "")

    provider = ClaudeNativeProvider(tmp_path, "/fake/claude", runner)

    with pytest.raises(ProviderError, match="could not verify"):
        provider.verify()


@pytest.mark.parametrize(
    ("payload", "structured", "message"),
    [
        ("not-json", True, "invalid JSON metadata"),
        (json.dumps({"is_error": True, "result": "denied"}), True, "request failed: denied"),
        (json.dumps({"subtype": "failed", "errors": ["bad"]}), True, "request failed"),
        (json.dumps({"subtype": "success", "result": "text"}), True, "without validated"),
        (json.dumps({"subtype": "success", "result": ""}), False, "no text output"),
    ],
)
def test_claude_native_fails_closed_on_invalid_generation_results(
    tmp_path, payload, structured, message
):
    provider = ClaudeNativeProvider(tmp_path, "/fake/claude", ClaudeResult(payload))

    with pytest.raises(ProviderError, match=message):
        provider.generate(_request("claude-native", structured=structured))


def test_claude_native_returns_plain_text_without_optional_capabilities(tmp_path):
    payload = json.dumps({"subtype": "success", "result": "plain answer"})
    provider = ClaudeNativeProvider(tmp_path, "/fake/claude", ClaudeResult(payload))

    response = provider.generate(_request("claude-native", structured=False))

    assert response.text == "plain answer"


@pytest.mark.parametrize("mode", ["missing", "empty"])
def test_codex_native_requires_a_nonempty_final_response(tmp_path, mode):
    def runner(command, **_kwargs):
        if command[1:3] == ["login", "status"]:
            return subprocess.CompletedProcess(command, 0, "Logged in using ChatGPT", "")
        if mode == "empty":
            output = Path(command[command.index("--output-last-message") + 1])
            output.write_text("", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "empty response")

    provider = CodexNativeProvider(tmp_path, "/fake/codex", runner)
    expected = "without writing" if mode == "missing" else "no text output"
    with pytest.raises(ProviderError, match=expected):
        provider.generate(_request("codex-native", structured=False))


def test_codex_native_runs_without_unrequested_optional_flags(tmp_path):
    calls = []

    def runner(command, **_kwargs):
        calls.append(command)
        if command[1:3] == ["login", "status"]:
            return subprocess.CompletedProcess(command, 0, "Logged in using ChatGPT", "")
        output = Path(command[command.index("--output-last-message") + 1])
        output.write_text("plain answer", encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    provider = CodexNativeProvider(tmp_path, "/fake/codex", runner)
    response = provider.generate(_request("codex-native", structured=False))

    assert response.text == "plain answer"
    assert "--output-schema" not in calls[1]
    assert not any("web_search" in item for item in calls[1])
