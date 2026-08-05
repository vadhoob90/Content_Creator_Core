"""Implement codex native provider integration."""

from __future__ import annotations

import json
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, Optional

from ..domain import ModelRequest, ModelResponse
from .base import ProviderError
from .native_cli import CommandRunner, NativeCliProvider


class CodexNativeProvider(NativeCliProvider):
    """Use the locally authenticated Codex CLI instead of the OpenAI API."""

    name = "codex-native"
    executable_name = "codex"
    api_environment_variables = ["OPENAI_API_KEY"]

    def __init__(
        self,
        root: Optional[Path] = None,
        executable: Optional[str] = None,
        command_runner: Optional[CommandRunner] = None,
    ):
        """Initialize the codex native provider.

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

    def _ensure_subscription_auth(self) -> None:
        """Return the ensure subscription auth.

        Returns:
            None: The callable updates ensure subscription auth state and returns no value.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        if self._authenticated:
            return
        result = self._run([self.executable, "login", "status"], timeout=30)
        status = "{}\n{}".format(result.stdout or "", result.stderr or "")
        if "Logged in using ChatGPT" not in status:
            raise ProviderError(
                "codex-native requires ChatGPT subscription authentication. "
                "Run 'codex login' and choose ChatGPT; API-key authentication is "
                "intentionally rejected."
            )
        self._authenticated = True

    def verify(self) -> Dict[str, str]:
        """Verify the codex native provider workflow.

        Returns:
            Dict[str, str]: The structured verified data for value.
        """
        self._ensure_subscription_auth()
        return {"authentication": "chatgpt"}

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate the codex native provider workflow.

        Translate the model request into a bounded Codex CLI invocation, validate structured
        output, and return normalized usage metadata.

        Args:
            request (ModelRequest): The validated request that initiates the operation.

        Returns:
            ModelResponse: The normalized model response with generated text and usage
                metadata.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        self._ensure_subscription_auth()
        with tempfile.TemporaryDirectory(prefix="content-creator-codex-") as directory:
            workdir = Path(directory)
            output_path = workdir / "response.txt"
            prompt = self._prompt(request.system, request.user)
            command = [
                self.executable,
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--cd",
                str(workdir),
                "--model",
                request.selection.model,
                "--output-last-message",
                str(output_path),
            ]
            if request.selection.reasoning_effort:
                command.extend(
                    [
                        "--config",
                        'model_reasoning_effort="{}"'.format(request.selection.reasoning_effort),
                    ]
                )
            if "web_search" in request.tools:
                command.extend(["--config", 'web_search="live"'])
            if request.output_schema:
                strict_schema = self._strict_schema(request.output_schema)
                if strict_schema:
                    schema_path = workdir / "schema.json"
                    schema_path.write_text(json.dumps(strict_schema), encoding="utf-8")
                    command.extend(["--output-schema", str(schema_path)])
                else:
                    prompt += (
                        "\n\nReturn only valid JSON matching this schema. The caller "
                        "will validate it and reject any mismatch.\n\nJSON SCHEMA\n"
                        + json.dumps(request.output_schema, ensure_ascii=False)
                    )
            command.append("-")
            result = self._run(
                command,
                input_text=prompt,
                cwd=workdir,
            )
            if not output_path.exists():
                raise ProviderError("codex-native completed without writing its final response")
            text = output_path.read_text(encoding="utf-8").strip()
            if not text:
                detail = (result.stderr or result.stdout or "").strip()
                raise ProviderError(
                    "codex-native returned no text output: {}".format(self._shorten(detail))
                )
        return ModelResponse(
            text=text,
            provider=self.name,
            model=request.selection.model,
        )

    @classmethod
    def _strict_schema(cls, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return an OpenAI-strict schema, or None for open-ended mappings.

        Args:
            schema (Dict[str, Any]): The schema collection consumed while strict schema.

        Returns:
            Optional[Dict[str, Any]]: The resulting strict schema when available; otherwise
                ``None``.
        """
        result = deepcopy(schema)
        if not cls._make_objects_strict(result):
            return None
        return result

    @classmethod
    def _make_objects_strict(cls, value: Any) -> bool:
        """Return the make objects strict.

        Args:
            value (Any): The value to process.

        Returns:
            bool: Whether make objects strict satisfies the documented condition.
        """
        if isinstance(value, list):
            return all(cls._make_objects_strict(item) for item in value)
        if not isinstance(value, dict):
            return True
        if value.get("type") == "object":
            additional = value.get("additionalProperties")
            if isinstance(additional, dict) or additional is True:
                return False
            value["additionalProperties"] = False
            properties = value.get("properties")
            if isinstance(properties, dict):
                value["required"] = list(properties)
        return all(cls._make_objects_strict(item) for item in value.values())
