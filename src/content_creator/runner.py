from __future__ import annotations

import json
from typing import Any, Dict, Optional, Type, TypeVar

from pydantic import BaseModel, ValidationError

from .configuration import Configuration
from .domain import ModelRequest, WorkOrder
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
    ):
        self.configuration = configuration
        self.registry = registry
        self.prompts = prompts
        self.history = []
        self.responses = []

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
        tools: Optional[list] = None,
    ):
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
        self.history.append(request)
        response = self.registry.get(selection.provider).generate(request)
        self.responses.append(response)
        if not output_model:
            return response.text.strip()
        try:
            return output_model.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            raise AgentOutputError(
                "{} returned invalid structured output: {}".format(role, exc)
            ) from exc
