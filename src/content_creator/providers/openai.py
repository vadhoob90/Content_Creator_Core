"""Implement openai provider integration."""

from __future__ import annotations

from typing import Any, Dict

from ..domain import ModelRequest, ModelResponse
from .base import Provider, ProviderError


class OpenAIProvider(Provider):
    """Generate content through the OpenAI API."""

    name = "openai"

    def __init__(self, client: Any = None):
        """Initialize the OpenAI provider with an injected or default client.

        Args:
            client (Any): The client value passed to init. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        if client is None:
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ProviderError(
                    "Install the OpenAI adapter with: pip install -e '.[openai]'"
                ) from exc
            client = OpenAI(max_retries=2)
        self.client = client

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a model response through the OpenAI Responses API.

        Args:
            request (ModelRequest): The validated request that initiates the operation.

        Returns:
            ModelResponse: The normalized model response with generated text and usage
                metadata.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        kwargs: Dict[str, Any] = {
            "model": request.selection.model,
            "instructions": request.system,
            "input": request.user,
            "max_output_tokens": request.max_output_tokens,
        }
        if request.selection.reasoning_effort:
            kwargs["reasoning"] = {"effort": request.selection.reasoning_effort}
        if request.output_schema:
            kwargs["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "{}_output".format(request.role.replace("-", "_")),
                    "strict": True,
                    "schema": request.output_schema,
                }
            }
        if "web_search" in request.tools:
            kwargs["tools"] = [{"type": "web_search"}]

        try:
            response = self.client.responses.create(**kwargs)
        except Exception as exc:
            raise ProviderError("OpenAI request failed: {}".format(exc)) from exc
        if getattr(response, "status", None) == "incomplete":
            raise ProviderError("OpenAI response was incomplete")
        if not response.output_text:
            raise ProviderError("OpenAI returned no text output")
        usage = getattr(response, "usage", None)
        return ModelResponse(
            text=response.output_text,
            provider=self.name,
            model=request.selection.model,
            raw_id=getattr(response, "id", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
