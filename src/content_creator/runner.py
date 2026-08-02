from __future__ import annotations

import json
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .configuration import Configuration
from .diagnostics import RuntimeDiagnostics
from .domain import ModelRequest, ModelResponse, WorkOrder
from .prompting import PromptAssembler
from .providers import ProviderRegistry

T = TypeVar("T", bound=BaseModel)


class AgentOutputError(ValueError):
    pass


class AgentRunner:
    def __init__(
        self,
        configuration: Configuration,
        registry: ProviderRegistry,
        prompts: PromptAssembler,
        diagnostics: Optional[RuntimeDiagnostics] = None,
    ):
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
        order: Optional[WorkOrder] = None,
        output_model: Optional[Type[T]] = None,
        provider: Optional[str] = None,
        profile: Optional[str] = None,
        tools: Optional[list[str]] = None,
    ) -> Any:
        required = set(tools or [])
        if output_model:
            required.add("structured_output")
        selection = self.configuration.selection(
            role_key,
            provider=provider,
            profile=profile,
            required_capabilities=required,
        )
        request = ModelRequest(
            role=role,
            system=self.prompts.system_prompt(role, order),
            user=self.prompts.user_prompt(instruction, payload),
            selection=selection,
            max_output_tokens=self.configuration.max_output_tokens,
            output_schema=output_model.model_json_schema() if output_model else None,
            tools=tools or [],
        )
        policy = self.configuration.diagnostic_policy
        max_attempts = policy["max_attempts"] if self.diagnostics and policy["enabled"] else 1
        for attempt in range(1, max_attempts + 1):
            self.history.append(request)
            response_index = len(self.responses)
            self.responses.append(None)
            started_at = self.diagnostics.timer() if self.diagnostics else 0.0
            if self.diagnostics:
                self.diagnostics.attempt_started(
                    role=role,
                    attempt=attempt,
                    provider=selection.provider,
                    model=selection.model,
                )
            try:
                response = self.registry.get(selection.provider).generate(request)
                self.responses[response_index] = response
                if not output_model:
                    result = response.text.strip()
                else:
                    try:
                        result = output_model.model_validate(json.loads(response.text))
                    except (json.JSONDecodeError, ValidationError) as exc:
                        raise AgentOutputError(
                            "{} returned invalid structured output: {}".format(role, exc)
                        ) from exc
            except Exception as exc:
                retrying = bool(
                    self.diagnostics
                    and attempt < max_attempts
                    and self.diagnostics.is_retryable(exc)
                )
                if self.diagnostics:
                    self.diagnostics.attempt_failed(
                        exc,
                        role=role,
                        attempt=attempt,
                        provider=selection.provider,
                        model=selection.model,
                        started_at=started_at,
                        retrying=retrying,
                    )
                if retrying:
                    continue
                raise
            if self.diagnostics:
                self.diagnostics.attempt_completed(
                    role=role,
                    attempt=attempt,
                    provider=selection.provider,
                    model=selection.model,
                    started_at=started_at,
                )
            return result
        raise AgentOutputError("{} exhausted its attempts".format(role))
