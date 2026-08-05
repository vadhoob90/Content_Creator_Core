"""Implement base provider integration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict

from ..domain import ModelRequest, ModelResponse


class ProviderError(RuntimeError):
    """Report provider failures."""

    pass


class Provider(ABC):
    """Represent a provider."""

    name: str

    @abstractmethod
    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a response for a normalized request."""

    def verify(self) -> Dict[str, Any]:
        """Verify provider."""
        raise ProviderError("Provider does not expose an offline verification operation")
