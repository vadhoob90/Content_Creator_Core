"""Implement fake provider integration."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Iterable

from pydantic import BaseModel

from ..domain import ModelRequest, ModelResponse
from .base import Provider, ProviderError


class FakeProvider(Provider):
    """Represent the fake provider contract."""

    name = "fake"

    def __init__(self, responses: Dict[str, Iterable[Any]]):
        """Initialize the fake provider with its required state and collaborators.

        Args:
            responses (Dict[str, Iterable[Any]]): The responses collection consumed while
                init.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.responses: Dict[str, Deque[Any]] = defaultdict(deque)
        for role, values in responses.items():
            self.responses[role].extend(values)
        self.requests: list[ModelRequest] = []

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate the fake provider workflow.

        Args:
            request (ModelRequest): The validated request that initiates the operation.

        Returns:
            ModelResponse: The normalized model response with generated text and usage
                metadata.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        self.requests.append(request)
        if not self.responses[request.role]:
            raise ProviderError("No scripted response for role {}".format(request.role))
        value = self.responses[request.role].popleft()
        if isinstance(value, BaseModel):
            text = value.model_dump_json()
        elif isinstance(value, (dict, list)):
            text = json.dumps(value)
        elif isinstance(value, Exception):
            raise value
        else:
            text = str(value)
        return ModelResponse(text=text, provider=self.name, model=request.selection.model)
