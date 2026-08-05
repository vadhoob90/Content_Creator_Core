"""Implement claude native provider integration."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from ..domain import ModelRequest, ModelResponse
from .base import ProviderError
from .native_cli import CommandRunner, NativeCliProvider


class ClaudeNativeProvider(NativeCliProvider):
    """Use Claude Code with Claude subscription authentication."""

    name = "claude-native"
    executable_name = "claude"
    api_environment_variables = ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"]

    def __init__(
        self,
        root: Optional[Path] = None,
        executable: Optional[str] = None,
        command_runner: Optional[CommandRunner] = None,
    ):
        """Initialize the claude native provider.

        Args:
            root (Optional[Path]): The workspace root directory. Defaults to ``None``.
            executable (Optional[str]): The executable text processed when init. Defaults to
                ``None``.
            command_runner (Optional[CommandRunner]): The command runner value passed to
                init. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        super().__init__(root, executable, command_runner)
        self._subscription_type: Optional[str] = None

    def _ensure_subscription_auth(self) -> None:
        """Return the ensure subscription auth.

        Returns:
            None: The callable updates ensure subscription auth state and returns no value.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        if self._authenticated:
            return
        result = self._run([self.executable, "auth", "status"], timeout=30)
        try:
            status: Dict[str, Any] = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise ProviderError(
                "claude-native could not verify Claude subscription authentication"
            ) from exc
        subscription = str(status.get("subscriptionType") or "").lower()
        if (
            not status.get("loggedIn")
            or status.get("authMethod") != "claude.ai"
            or not subscription
            or status.get("apiProvider") not in {None, "firstParty"}
        ):
            raise ProviderError(
                "claude-native requires Claude subscription authentication. "
                "Run 'claude auth login' without '--console'; API-key and Console "
                "authentication are intentionally rejected."
            )
        self._subscription_type = subscription
        self._authenticated = True

    def verify(self) -> Dict[str, str]:
        """Verify the claude native provider workflow.

        Returns:
            Dict[str, str]: The structured verified data for value.
        """
        self._ensure_subscription_auth()
        return {
            "authentication": "claude.ai",
            "subscription_type": self._subscription_type or "unknown",
        }

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate the claude native provider workflow.

        Translate the model request into a bounded Claude CLI invocation, validate
        structured output, and return normalized usage metadata.

        Args:
            request (ModelRequest): The validated request that initiates the operation.

        Returns:
            ModelResponse: The normalized model response with generated text and usage
                metadata.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        self._ensure_subscription_auth()
        with tempfile.TemporaryDirectory(prefix="content-creator-claude-") as directory:
            workdir = Path(directory)
            system_path = workdir / "system.md"
            system_path.write_text(
                self._system_prompt(request.system),
                encoding="utf-8",
            )
            command = [
                self.executable,
                "-p",
                "--bare",
                "--output-format",
                "json",
                "--model",
                request.selection.model,
                "--system-prompt-file",
                str(system_path),
                "--no-session-persistence",
                "--strict-mcp-config",
                "--permission-mode",
                "dontAsk",
                "--max-turns",
                "12",
            ]
            if request.selection.reasoning_effort:
                command.extend(["--effort", request.selection.reasoning_effort])
            if request.output_schema:
                command.extend(
                    [
                        "--json-schema",
                        json.dumps(request.output_schema, separators=(",", ":")),
                    ]
                )
            if "web_search" in request.tools:
                command.extend(["--tools", "WebSearch,WebFetch"])
            else:
                command.extend(["--tools", ""])
            result = self._run(
                command,
                input_text=request.user,
                cwd=workdir,
            )
            try:
                payload: Dict[str, Any] = json.loads(result.stdout)
            except json.JSONDecodeError as exc:
                raise ProviderError(
                    "claude-native returned invalid JSON metadata: {}".format(
                        self._shorten(result.stdout or "")
                    )
                ) from exc
            if payload.get("is_error") or payload.get("subtype") not in {
                None,
                "success",
            }:
                raise ProviderError(
                    "claude-native request failed: {}".format(
                        self._shorten(
                            str(payload.get("result") or payload.get("errors") or payload)
                        )
                    )
                )
            if request.output_schema:
                structured = payload.get("structured_output")
                if structured is None:
                    raise ProviderError(
                        "claude-native completed without validated structured output"
                    )
                text = json.dumps(structured, ensure_ascii=False)
            else:
                text = str(payload.get("result") or "").strip()
            if not text:
                raise ProviderError("claude-native returned no text output")
        return ModelResponse(
            text=text,
            provider=self.name,
            model=request.selection.model,
            raw_id=payload.get("session_id"),
        )
