"""Provide runner capabilities."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from pydantic import ValidationError

from .configuration import Configuration
from .diagnostics import RuntimeDiagnostics
from .domain import ModelRequest, ModelResponse
from .prompting import PromptAssembler
from .providers import ProviderRegistry
from .runner_models import AgentRunOptions as AgentRunOptions


class AgentOutputError(ValueError):
    """Report agent output failures."""

    pass


class AgentRunner:
    """Execute repository-owned agent roles through a provider."""

    def __init__(
        self,
        configuration: Configuration,
        registry: ProviderRegistry,
        prompts: PromptAssembler,
        diagnostics: Optional[RuntimeDiagnostics] = None,
    ):
        """Initialize the agent runner."""
        self.configuration = configuration
        self.registry = registry
        self.prompts = prompts
        self.diagnostics = diagnostics
        self.history: list[ModelRequest] = []
        self.responses: list[Optional[ModelResponse]] = []

    def run(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: Optional[AgentRunOptions] = None,
    ) -> Any:
        """Run agent runner."""
        resolved_options = options or AgentRunOptions()
        request = self._request(role, role_key, instruction, payload, resolved_options)
        policy = self.configuration.diagnostic_policy
        max_attempts = policy["max_attempts"] if self.diagnostics and policy["enabled"] else 1
        for attempt in range(1, max_attempts + 1):
            result = self._attempt(request, role, attempt, max_attempts, resolved_options)
            if result is not None:
                return result
        raise AgentOutputError(f"{role} exhausted its attempts")

    def _request(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: AgentRunOptions,
    ) -> ModelRequest:
        """Return the request."""
        required = set(options.tools)
        if options.output_model:
            required.add("structured_output")
        selection = self.configuration.selection(
            role_key,
            provider=options.provider,
            profile=options.profile,
            required_capabilities=required,
        )
        return ModelRequest(
            role=role,
            system=self.prompts.system_prompt(role, options.order),
            user=self.prompts.user_prompt(instruction, payload),
            selection=selection,
            max_output_tokens=self.configuration.max_output_tokens,
            output_schema=(
                options.output_model.model_json_schema() if options.output_model else None
            ),
            tools=options.tools,
        )

    def _attempt(
        self,
        request: ModelRequest,
        role: str,
        attempt: int,
        max_attempts: int,
        options: AgentRunOptions,
    ) -> Any:
        """Return the attempt."""
        self.history.append(request)
        response_index = len(self.responses)
        self.responses.append(None)
        started_at = self.diagnostics.timer() if self.diagnostics else 0.0
        if self.diagnostics:
            self.diagnostics.attempt_started(
                role=role,
                attempt=attempt,
                provider=request.selection.provider,
                model=request.selection.model,
            )
        try:
            response = self.registry.get(request.selection.provider).generate(request)
            self.responses[response_index] = response
            result = self._parse_response(response.text, role, options)
        except Exception as error:
            if self._record_failure(error, request, role, attempt, max_attempts, started_at):
                return None
            raise
        if self.diagnostics:
            self.diagnostics.attempt_completed(
                role=role,
                attempt=attempt,
                provider=request.selection.provider,
                model=request.selection.model,
                started_at=started_at,
            )
        return result

    @staticmethod
    def _parse_response(response_text: str, role: str, options: AgentRunOptions) -> Any:
        """Parse response."""
        if not options.output_model:
            return response_text.strip()
        try:
            return options.output_model.model_validate(json.loads(response_text))
        except (json.JSONDecodeError, ValidationError) as error:
            raise AgentOutputError(f"{role} returned invalid structured output: {error}") from error

    def _record_failure(
        self,
        error: Exception,
        request: ModelRequest,
        role: str,
        attempt: int,
        max_attempts: int,
        started_at: float,
    ) -> bool:
        """Record failure."""
        retrying = bool(
            self.diagnostics and attempt < max_attempts and self.diagnostics.is_retryable(error)
        )
        if self.diagnostics:
            self.diagnostics.attempt_failed(
                error,
                role=role,
                attempt=attempt,
                provider=request.selection.provider,
                model=request.selection.model,
                started_at=started_at,
                retrying=retrying,
            )
        return retrying
