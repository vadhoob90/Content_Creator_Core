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
        """Generate a response for a normalized request.

        Args:
            request (ModelRequest): The validated request that initiates the operation.

        Returns:
            ModelResponse: The normalized model response with generated text and usage
                metadata.
        """

    def verify(self) -> Dict[str, Any]:
        """Verify the provider workflow.

        Returns:
            Dict[str, Any]: The structured verified data for value.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        raise ProviderError("Provider does not expose an offline verification operation")
