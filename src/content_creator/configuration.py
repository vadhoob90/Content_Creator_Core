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
            workspace = self._read_yaml(workspace_config) if workspace_config.exists() else {}
            configured = workspace.get("provider", {}) or {}
            if not isinstance(configured, dict):
                raise ConfigurationError("provider configuration must be a mapping")
            provider = configured.get("default")
        if not provider:
            provider = self.models.get("defaults", {}).get("provider")
        if not provider:
            raise ConfigurationError(
                "No provider selected. Set CONTENT_CREATOR_PROVIDER, pass "
                "--provider, or set provider.default in content-creator.yaml"
            )
        if provider not in self.models["providers"]:
            raise ConfigurationError("Unknown default provider: {}".format(provider))
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
        return self._read_yaml(self.resources.path("rubrics/{}.yaml".format(name)))

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
            raise ConfigurationError("perspective.mode must be explicit, automatic, or disabled")
        return policy

    @property
    def coordinator_policy(self) -> Dict[str, Any]:
        path = self.root / "content-creator.yaml"
        data = self._read_yaml(path) if path.exists() else {}
        configured = data.get("coordinator", {}) or {}
        if not isinstance(configured, dict):
            raise ConfigurationError("coordinator configuration must be a mapping")
        policy = {
            "name": "Content Creator Coordinator",
            "default_voice": None,
            "default_pack": "general-text",
            "ask_before_voice_change": True,
            "require_final_review": True,
            "external_publication": "disabled",
            "review_reminder": None,
        }
        policy.update(configured)
        if policy["external_publication"] != "disabled":
            raise ConfigurationError("coordinator.external_publication must be disabled")
        if not isinstance(policy["ask_before_voice_change"], bool):
            raise ConfigurationError("coordinator.ask_before_voice_change must be a boolean")
        if not isinstance(policy["require_final_review"], bool):
            raise ConfigurationError("coordinator.require_final_review must be a boolean")
        return policy

    @property
    def diagnostic_policy(self) -> Dict[str, Any]:
        path = self.root / "content-creator.yaml"
        data = self._read_yaml(path) if path.exists() else {}
        configured = data.get("diagnostics", {}) or {}
        if not isinstance(configured, dict):
            raise ConfigurationError("diagnostics configuration must be a mapping")
        policy = {
            "enabled": True,
            "max_attempts": 2,
            "defer_recovered_until_publication": True,
        }
        policy.update(configured)
        if not isinstance(policy["enabled"], bool):
            raise ConfigurationError("diagnostics.enabled must be a boolean")
        if not isinstance(policy["max_attempts"], int) or not (1 <= policy["max_attempts"] <= 3):
            raise ConfigurationError("diagnostics.max_attempts must be an integer from 1 to 3")
        if policy["defer_recovered_until_publication"] is not True:
            raise ConfigurationError("diagnostics.defer_recovered_until_publication must be true")
        return policy

    @property
    def statistical_voice_score_policy(self) -> Dict[str, Any]:
        path = self.root / "content-creator.yaml"
        data = self._read_yaml(path) if path.exists() else {}
        configured = data.get("statistical_voice_score")
        if configured is None:
            # Compatibility with the unreleased voice-assessment configuration.
            configured = data.get("voice_assessment", {}) or {}
            if "mode" in configured and "method" not in configured:
                configured = dict(configured)
                legacy_mode = configured.pop("mode")
                if legacy_mode not in {"statistical", "ml"}:
                    raise ConfigurationError("voice_assessment.mode must be statistical or ml")
                configured["method"] = "deterministic" if legacy_mode == "statistical" else "ml"
        if not isinstance(configured, dict):
            raise ConfigurationError("statistical_voice_score configuration must be a mapping")
        policy = {
            "enabled": False,
            "method": "deterministic",
            "minimum_sources": 20,
            "minimum_draft_words": 100,
            "outlier_iqr_multiplier": 1.5,
            "max_reported_outliers": 8,
        }
        policy.update(configured)
        if not isinstance(policy["enabled"], bool):
            raise ConfigurationError("statistical_voice_score.enabled must be a boolean")
        if policy["method"] not in {"deterministic", "ml"}:
            raise ConfigurationError("statistical_voice_score.method must be deterministic or ml")
        for name, minimum, maximum in (
            ("minimum_sources", 3, 1000),
            ("minimum_draft_words", 25, 10000),
            ("max_reported_outliers", 1, 50),
        ):
            value = policy[name]
            if not isinstance(value, int) or not minimum <= value <= maximum:
                raise ConfigurationError(
                    "statistical_voice_score.{} must be an integer from {} to {}".format(
                        name, minimum, maximum
                    )
                )
        multiplier = policy["outlier_iqr_multiplier"]
        if isinstance(multiplier, bool) or not isinstance(multiplier, (int, float)):
            raise ConfigurationError(
                "statistical_voice_score.outlier_iqr_multiplier must be a number"
            )
        if not 1.0 <= float(multiplier) <= 5.0:
            raise ConfigurationError(
                "statistical_voice_score.outlier_iqr_multiplier must be from 1.0 to 5.0"
            )
        policy["outlier_iqr_multiplier"] = float(multiplier)
        return policy

    @property
    def voice_assessment_policy(self) -> Dict[str, Any]:
        """Compatibility alias for callers using the pre-release name."""

        return self.statistical_voice_score_policy
