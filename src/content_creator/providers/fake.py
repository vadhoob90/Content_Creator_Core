from __future__ import annotations

import json
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Iterable

from pydantic import BaseModel

from ..domain import ModelRequest, ModelResponse
from .base import Provider, ProviderError


class FakeProvider(Provider):
    """Deterministic provider for unit tests and replay evaluations."""

    name = "fake"

    def __init__(self, responses: Dict[str, Iterable[Any]]):
        self.responses: Dict[str, Deque[Any]] = defaultdict(deque)
        for role, values in responses.items():
            self.responses[role].extend(values)
        self.requests = []

    def generate(self, request: ModelRequest) -> ModelResponse:
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
