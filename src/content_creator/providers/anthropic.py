from __future__ import annotations

from typing import Any, Dict, List

from ..domain import ModelRequest, ModelResponse
from .base import Provider, ProviderError


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, client: Any = None):
        if client is None:
            try:
                from anthropic import Anthropic
            except ImportError as exc:
                raise ProviderError(
                    "Install the Anthropic adapter with: pip install -e '.[anthropic]'"
                ) from exc
            client = Anthropic(max_retries=2)
        self.client = client

    def generate(self, request: ModelRequest) -> ModelResponse:
        kwargs: Dict[str, Any] = {
            "model": request.selection.model,
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.output_schema:
            kwargs["output_config"] = {
                "format": {
                    "type": "json_schema",
                    "schema": request.output_schema,
                }
            }
        if "web_search" in request.tools:
            kwargs["tools"] = [{"type": "web_search_20260318", "name": "web_search"}]

        try:
            response = self.client.messages.create(**kwargs)
        except Exception as exc:
            raise ProviderError("Anthropic request failed: {}".format(exc)) from exc
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ProviderError("Anthropic response reached the output-token limit")

        texts: List[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                texts.append(block.text)
        if not texts:
            raise ProviderError("Anthropic returned no text output")
        usage = getattr(response, "usage", None)
        return ModelResponse(
            text="\n".join(texts),
            provider=self.name,
            model=request.selection.model,
            raw_id=getattr(response, "id", None),
            input_tokens=getattr(usage, "input_tokens", None),
            output_tokens=getattr(usage, "output_tokens", None),
        )
