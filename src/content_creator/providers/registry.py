from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from .base import Provider, ProviderError


class ProviderRegistry:
    def __init__(
        self,
        providers: Optional[Dict[str, Provider]] = None,
        root: Optional[Path] = None,
    ):
        self.providers = providers or {}
        self.root = root

    def register(self, name: str, provider: Provider) -> None:
        self.providers[name] = provider

    def get(self, name: str) -> Provider:
        if name in self.providers:
            return self.providers[name]
        if name == "openai":
            from .openai import OpenAIProvider

            provider: Provider = OpenAIProvider()
        elif name == "anthropic":
            from .anthropic import AnthropicProvider

            provider = AnthropicProvider()
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
