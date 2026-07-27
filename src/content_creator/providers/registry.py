from __future__ import annotations

from typing import Dict, Optional

from .base import Provider, ProviderError


class ProviderRegistry:
    def __init__(self, providers: Optional[Dict[str, Provider]] = None):
        self.providers = providers or {}

    def register(self, name: str, provider: Provider) -> None:
        self.providers[name] = provider

    def get(self, name: str) -> Provider:
        if name in self.providers:
            return self.providers[name]
        if name == "openai":
            from .openai import OpenAIProvider

            provider = OpenAIProvider()
        elif name == "anthropic":
            from .anthropic import AnthropicProvider

            provider = AnthropicProvider()
        else:
            raise ProviderError("Unknown provider: {}".format(name))
        self.providers[name] = provider
        return provider
