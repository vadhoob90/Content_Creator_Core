"""Implement registry provider integration."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .base import Provider, ProviderError


class ProviderRegistry:
    """Manage provider records."""

    def __init__(
        self,
        providers: Optional[Dict[str, Provider]] = None,
        root: Optional[Path] = None,
    ):
        """Initialize the provider registry with its required state and collaborators.

        Args:
            providers (Optional[Dict[str, Provider]]): The providers value passed to init.
                Defaults to ``None``.
            root (Optional[Path]): The workspace root directory. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.providers = providers or {}
        self.root = root

    def register(self, name: str, provider: Provider) -> None:
        """Register the provider registry workflow.

        Args:
            name (str): The stable or human-readable name for the domain object.
            provider (Provider): The provider implementation used for generation.

        Returns:
            None: The callable updates register state and returns no value.
        """
        self.providers[name] = provider

    def get(self, name: str) -> Provider:
        """Retrieve the provider registry managed by provider registry.

        Args:
            name (str): The stable or human-readable name for the domain object.

        Returns:
            Provider: The resulting provider for get.

        Raises:
            ProviderError: If the provider operation cannot complete.
        """
        if name in self.providers:
            return self.providers[name]
        if name == "openai":
            from .openai import OpenAIProvider

            provider: Provider = OpenAIProvider()
        elif name == "anthropic":
            from .anthropic import AnthropicProvider

            options = {}
            if self.root is not None and (self.root / "config" / "models.yaml").exists():
                from ..configuration import Configuration

                options["web_search_tool"] = Configuration(self.root).anthropic_web_search_tool
            provider = AnthropicProvider(**options)
        elif name == "bedrock":
            from .bedrock import BedrockProvider

            provider = BedrockProvider()
        elif name == "codex-native":
            from .codex_native import CodexNativeProvider

            provider = CodexNativeProvider(root=self.root)
        elif name == "claude-native":
            from .claude_native import ClaudeNativeProvider

            provider = ClaudeNativeProvider(root=self.root)
        else:
            raise ProviderError("Unknown provider: {}".format(name))
        self.providers[name] = provider
        return provider
