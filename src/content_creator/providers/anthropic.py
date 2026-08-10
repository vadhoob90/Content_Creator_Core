"""Implement anthropic provider integration."""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from ..domain import ModelRequest, ModelResponse
from .base import Provider, ProviderError


class AnthropicProvider(Provider):
    """Generate content through the Anthropic API."""

    name = "anthropic"
    _MAX_OPTIONAL_PARAMETERS = 24
    _MAX_UNION_PARAMETERS = 16
    _COMPLEXITY_ERRORS = (
        "schema is too complex",
        "compiled grammar is too large",
        "grammar compilation timed out",
    )

    def __init__(self, client: Any = None):
        """Initialize the Anthropic provider with an injected or default client.

        Args:
            client (Any): The client value passed to init. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.

        """
        if client is None:
            client = self._default_client()
        self.client = client

    @classmethod
    def _default_client(cls) -> Any:
        """Construct the direct or Microsoft Foundry Anthropic client.

        Returns:
            Any: The configured Anthropic SDK client.

        Raises:
            ProviderError: If the optional Anthropic adapter is unavailable.
        """
        try:
            from anthropic import Anthropic, AnthropicFoundry
        except ImportError as exc:
            raise ProviderError(
                "Install the Anthropic adapter with: pip install -e '.[anthropic]'"
            ) from exc
        base_url = cls._foundry_base_url()
        resource = cls._foundry_resource(base_url)
        if not base_url and not resource:
            return Anthropic(max_retries=2)
        options: Dict[str, Any] = {"max_retries": 2}
        if resource:
            options["resource"] = resource
        elif base_url:
            options["base_url"] = base_url
        api_key = os.getenv("ANTHROPIC_FOUNDRY_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
        if api_key:
            options["api_key"] = api_key
        return AnthropicFoundry(**options)

    @staticmethod
    def _foundry_base_url() -> Optional[str]:
        """Return an explicitly configured Microsoft Foundry endpoint.

        Returns:
            Optional[str]: The Foundry base URL when configured; otherwise ``None``.
        """
        configured = os.getenv("ANTHROPIC_FOUNDRY_BASE_URL")
        if configured:
            return configured
        legacy = os.getenv("ANTHROPIC_BASE_URL")
        if legacy and ".services.ai.azure.com/anthropic" in legacy.lower():
            return legacy
        return None

    @staticmethod
    def _foundry_resource(base_url: Optional[str]) -> Optional[str]:
        """Resolve the Foundry resource while preferring an explicit endpoint.

        Args:
            base_url (Optional[str]): The configured Foundry endpoint.

        Returns:
            Optional[str]: The Foundry resource name when available; otherwise ``None``.
        """
        if base_url:
            hostname = (urlparse(base_url).hostname or "").lower()
            suffix = ".services.ai.azure.com"
            if hostname.endswith(suffix):
                resource = hostname[: -len(suffix)]
                if resource:
                    return resource
        return os.getenv("ANTHROPIC_FOUNDRY_RESOURCE")

    @classmethod
    def _strict_schema(cls, schema: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return an Anthropic-compatible schema within grammar limits.

        Args:
            schema (Dict[str, Any]): The original provider-neutral JSON schema.

        Returns:
            Optional[Dict[str, Any]]: The strict schema, or ``None`` when prompt-based JSON
                is required.
        """
        if cls._has_open_mapping(schema):
            return None
        try:
            from anthropic import transform_schema

            strict = transform_schema(schema)
        except (ImportError, TypeError, ValueError):
            return None
        optional, unions = cls._schema_complexity(strict)
        if optional > cls._MAX_OPTIONAL_PARAMETERS or unions > cls._MAX_UNION_PARAMETERS:
            return None
        return strict

    @classmethod
    def _has_open_mapping(cls, value: Any) -> bool:
        """Return whether a schema contains an open-ended object mapping.

        Args:
            value (Any): The schema node to inspect.

        Returns:
            bool: Whether prompt-based JSON is required to preserve mapping semantics.
        """
        if isinstance(value, list):
            return any(cls._has_open_mapping(item) for item in value)
        if not isinstance(value, dict):
            return False
        additional = value.get("additionalProperties")
        if additional is True or isinstance(additional, dict):
            return True
        return any(cls._has_open_mapping(item) for item in value.values())

    @classmethod
    def _schema_complexity(cls, value: Any) -> Tuple[int, int]:
        """Return optional and union parameter counts across a JSON schema.

        Args:
            value (Any): The schema node to inspect.

        Returns:
            Tuple[int, int]: Optional-parameter and union-parameter counts.
        """
        optional = 0
        unions = 0
        if isinstance(value, list):
            for item in value:
                item_optional, item_unions = cls._schema_complexity(item)
                optional += item_optional
                unions += item_unions
            return optional, unions
        if not isinstance(value, dict):
            return optional, unions
        properties = value.get("properties")
        if isinstance(properties, dict):
            required = set(value.get("required", []))
            optional += sum(name not in required for name in properties)
            unions += sum(cls._is_union(schema) for schema in properties.values())
        for item in value.values():
            item_optional, item_unions = cls._schema_complexity(item)
            optional += item_optional
            unions += item_unions
        return optional, unions

    @staticmethod
    def _is_union(value: Any) -> bool:
        """Return whether a parameter schema uses a union type.

        Args:
            value (Any): The parameter schema to inspect.

        Returns:
            bool: Whether the schema uses ``anyOf``, ``oneOf``, or a type array.
        """
        if not isinstance(value, dict):
            return False
        return "anyOf" in value or "oneOf" in value or isinstance(value.get("type"), list)

    @staticmethod
    def _prompt_json_kwargs(kwargs: Dict[str, Any], schema: Dict[str, Any]) -> Dict[str, Any]:
        """Return request arguments for downstream-validated prompt JSON.

        Args:
            kwargs (Dict[str, Any]): The base Anthropic request arguments.
            schema (Dict[str, Any]): The original provider-neutral JSON schema.

        Returns:
            Dict[str, Any]: Request arguments without grammar-mode structured output.
        """
        fallback = dict(kwargs)
        fallback.pop("output_config", None)
        fallback["system"] = (
            str(kwargs["system"])
            + "\n\nSTRUCTURED OUTPUT\nReturn only valid JSON matching the schema below. "
            "Do not wrap the JSON in a Markdown code fence. The caller validates the "
            "result and rejects any mismatch.\n\nJSON SCHEMA\n"
            + json.dumps(schema, ensure_ascii=False, separators=(",", ":"))
        )
        return fallback

    @classmethod
    def _is_complexity_error(cls, error: Exception) -> bool:
        """Return whether Anthropic rejected grammar compilation complexity.

        Args:
            error (Exception): The provider exception to classify.

        Returns:
            bool: Whether a prompt-based JSON retry is appropriate.
        """
        message = str(error).lower()
        return any(fragment in message for fragment in cls._COMPLEXITY_ERRORS)

    def _create_message(
        self,
        kwargs: Dict[str, Any],
        schema: Optional[Dict[str, Any]],
    ) -> Any:
        """Create one message with a bounded structured-output fallback.

        Args:
            kwargs (Dict[str, Any]): The prepared Anthropic request arguments.
            schema (Optional[Dict[str, Any]]): The original output schema.

        Returns:
            Any: The Anthropic SDK message response.

        Raises:
            ProviderError: If the initial request or bounded fallback fails.
        """
        try:
            return self.client.messages.create(**kwargs)
        except Exception as exc:
            if not schema or "output_config" not in kwargs or not self._is_complexity_error(exc):
                raise ProviderError("Anthropic request failed: {}".format(exc)) from exc
        fallback = self._prompt_json_kwargs(kwargs, schema)
        try:
            return self.client.messages.create(**fallback)
        except Exception as exc:
            raise ProviderError(
                "Anthropic prompt-based structured-output fallback failed: {}".format(exc)
            ) from exc

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a model response through the Anthropic Messages API.

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
            "max_tokens": request.max_output_tokens,
            "system": request.system,
            "messages": [{"role": "user", "content": request.user}],
        }
        if request.output_schema:
            strict_schema = self._strict_schema(request.output_schema)
            if strict_schema:
                kwargs["output_config"] = {
                    "format": {
                        "type": "json_schema",
                        "schema": strict_schema,
                    }
                }
            else:
                kwargs = self._prompt_json_kwargs(kwargs, request.output_schema)
        if "web_search" in request.tools:
            kwargs["tools"] = [{"type": "web_search_20260318", "name": "web_search"}]

        response = self._create_message(kwargs, request.output_schema)
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
