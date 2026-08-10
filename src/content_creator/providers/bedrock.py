"""Implement Amazon Bedrock provider integration."""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..domain import ModelRequest, ModelResponse
from .anthropic import AnthropicProvider
from .base import ProviderError


class BedrockProvider(AnthropicProvider):
    """Generate content through Claude on Amazon Bedrock."""

    name = "bedrock"
    _REQUEST_LABEL = "Bedrock"

    @classmethod
    def _default_client(cls) -> Any:
        """Construct the Anthropic SDK's Amazon Bedrock client.

        Returns:
            Any: The configured Anthropic Bedrock SDK client.

        Raises:
            ProviderError: If the optional Bedrock adapter is unavailable.
        """
        try:
            from anthropic import AnthropicBedrock
        except ImportError as exc:
            raise ProviderError(
                "Install the Bedrock adapter with: pip install -e '.[bedrock]'"
            ) from exc
        return AnthropicBedrock(max_retries=2)

    @classmethod
    def _strict_schema(
        _cls: type[BedrockProvider], _schema: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Use Core's downstream-validated JSON fallback for Bedrock.

        Args:
            _cls (type[BedrockProvider]): The Bedrock provider class receiving the schema
                policy request.
            _schema (Dict[str, Any]): The provider-neutral JSON schema.

        Returns:
            Optional[Dict[str, Any]]: Always ``None`` because Bedrock Runtime does not
                consistently expose native structured outputs across supported models.
        """
        return None

    def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a response through Bedrock's Anthropic Messages API.

        Args:
            request (ModelRequest): The validated request that initiates the operation.

        Returns:
            ModelResponse: The normalized model response.

        Raises:
            ProviderError: If an unsupported server-side tool is requested.
        """
        if "web_search" in request.tools:
            raise ProviderError("Bedrock does not support server-side web search")
        return super().generate(request)

    def verify(self) -> Dict[str, Any]:
        """Verify SDK availability and the standard AWS credential chain.

        Returns:
            Dict[str, Any]: Non-secret authentication and region metadata.

        Raises:
            ProviderError: If credentials cannot be resolved locally.
        """
        region = getattr(self.client, "aws_region", None)
        if getattr(self.client, "api_key", None):
            return {"authentication": "bedrock-api-key", "region": region}
        try:
            import boto3
        except ImportError as exc:
            raise ProviderError(
                "Install the Bedrock adapter with: pip install -e '.[bedrock]'"
            ) from exc
        profile = getattr(self.client, "aws_profile", None)
        try:
            session = boto3.Session(profile_name=profile, region_name=region)
            credentials = session.get_credentials()
        except Exception as exc:
            raise ProviderError("AWS credential verification failed: {}".format(exc)) from exc
        if credentials is None:
            raise ProviderError(
                "No AWS credentials found. Configure AWS_PROFILE, environment credentials, "
                "workload identity, or AWS_BEARER_TOKEN_BEDROCK."
            )
        method = getattr(credentials, "method", None) or "aws-credential-chain"
        return {"authentication": str(method), "region": region}
