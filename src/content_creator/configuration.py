from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .domain import ModelSelection
from .resource_paths import ResourceResolver


class ConfigurationError(ValueError):
    pass


class Configuration:
    def __init__(self, root: Path, model_config: Optional[Path] = None):
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        path = model_config or self.resources.path("config/models.yaml")
        self.models = self._read_yaml(path)

    @staticmethod
    def _read_yaml(path: Path) -> Dict[str, Any]:
        if not path.exists():
            raise ConfigurationError("Missing configuration: {}".format(path))
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfigurationError("Expected a mapping in {}".format(path))
        return data

    @property
    def default_provider(self) -> str:
        provider = os.getenv("CONTENT_CREATOR_PROVIDER")
        if not provider:
            workspace_config = self.root / "content-creator.yaml"
            workspace = (
                self._read_yaml(workspace_config)
                if workspace_config.exists()
                else {}
            )
            configured = workspace.get("provider", {}) or {}
            if not isinstance(configured, dict):
                raise ConfigurationError(
                    "provider configuration must be a mapping"
                )
            provider = configured.get("default")
        if not provider:
            provider = self.models.get("defaults", {}).get("provider")
        if not provider:
            raise ConfigurationError(
                "No provider selected. Set CONTENT_CREATOR_PROVIDER, pass "
                "--provider, or set provider.default in content-creator.yaml"
            )
        if provider not in self.models["providers"]:
            raise ConfigurationError(
                "Unknown default provider: {}".format(provider)
            )
        return provider

    @property
    def max_output_tokens(self) -> int:
        return int(self.models["defaults"].get("max_output_tokens", 6000))

    def selection(
        self,
        role_key: str,
        provider: Optional[str] = None,
        profile: Optional[str] = None,
        required_capabilities=None,
    ) -> ModelSelection:
        provider_name = provider or self.default_provider
        profile_name = profile or self.models["roles"].get(role_key)
        if not profile_name:
            raise ConfigurationError("No model profile configured for role {}".format(role_key))
        try:
            profile_details = self.models["providers"][provider_name]["profiles"][profile_name]
        except KeyError as exc:
            raise ConfigurationError(
                "Unknown provider/profile combination: {}/{}".format(provider_name, profile_name)
            ) from exc
        candidates = profile_details.get("candidates", [profile_details])
        required = set(required_capabilities or [])
        for details in candidates:
            capabilities = list(details.get("capabilities", []))
            if required.issubset(capabilities):
                return ModelSelection(
                    provider=provider_name,
                    profile=profile_name,
                    model=str(details["model"]),
                    reasoning_effort=details.get("reasoning_effort"),
                    capabilities=capabilities,
                )
        raise ConfigurationError(
            "No {} candidate satisfies capabilities: {}".format(
                profile_name, ", ".join(sorted(required))
            )
        )

    def rubric(self, name: str) -> Dict[str, Any]:
        return self._read_yaml(
            self.resources.path("rubrics/{}.yaml".format(name))
        )

    @property
    def perspective_policy(self) -> Dict[str, Any]:
        path = self.root / "content-creator.yaml"
        data = self._read_yaml(path) if path.exists() else {}
        configured = data.get("perspective", {}) or {}
        if not isinstance(configured, dict):
            raise ConfigurationError("perspective configuration must be a mapping")
        policy = {
            "mode": "explicit",
            "allow_multiple": False,
            "ask_when_ambiguous": True,
            "show_resolution": True,
            "conflict_policy": "propose-update",
        }
        policy.update(configured)
        if policy["mode"] not in {"explicit", "automatic", "disabled"}:
            raise ConfigurationError(
                "perspective.mode must be explicit, automatic, or disabled"
            )
        return policy
