"""Provide configuration capabilities."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Collection, Dict, Optional

import yaml

from .domain import ModelSelection
from .resource_paths import ResourceResolver
from .storage import RunStore


class ConfigurationError(ValueError):
    """Report configuration failures."""

    pass


def persist_default_provider(root: Path, provider_name: str) -> Path:
    """Persist the workspace's selected default provider atomically.

    Args:
        root (Path): Workspace root containing ``content-creator.yaml``.
        provider_name (str): Registered provider name selected by the author.

    Returns:
        Path: Workspace configuration path that was updated.

    Raises:
        ConfigurationError: If the workspace configuration is not a mapping.
    """
    path = root.resolve() / "content-creator.yaml"
    configuration = yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}
    if not isinstance(configuration, dict):
        raise ConfigurationError("content-creator.yaml must contain a mapping")
    provider_configuration = configuration.get("provider", {}) or {}
    if not isinstance(provider_configuration, dict):
        raise ConfigurationError("provider configuration must be a mapping")
    provider_configuration["default"] = provider_name
    configuration["provider"] = provider_configuration
    RunStore._atomic_text(path, yaml.safe_dump(configuration, sort_keys=False))
    return path


class Configuration:
    """Represent a configuration."""

    _ANTHROPIC_WEB_SEARCH_TOOLS = {
        "web_search_20250305",
        "web_search_20260209",
        "web_search_20260318",
    }

    def __init__(self, root: Path, model_config: Optional[Path] = None):
        """Initialize the configuration with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            model_config (Optional[Path]): The filesystem path containing the model config.
                Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.resources = ResourceResolver(self.root)
        path = model_config or self.resources.path("config/models.yaml")
        self.models = self._read_yaml(path)

    @staticmethod
    def _read_yaml(path: Path) -> Dict[str, Any]:
        """Read the yaml.

        Args:
            path (Path): The filesystem path to inspect or update.

        Returns:
            Dict[str, Any]: The structured loaded data for yaml.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
        if not path.exists():
            raise ConfigurationError("Missing configuration: {}".format(path))
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ConfigurationError("Expected a mapping in {}".format(path))
        return data

    @property
    def default_provider(self) -> str:
        """Return the default provider.

        Returns:
            str: The resulting text for default provider.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
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
        """Return the max output tokens.

        Returns:
            int: The resulting numeric value for max output tokens.
        """
        return int(self.models["defaults"].get("max_output_tokens", 6000))

    @property
    def anthropic_web_search_tool(self) -> str:
        """Return the configured Anthropic server-side web-search tool version.

        Returns:
            str: An Anthropic web-search tool identifier supported by Core.

        Raises:
            ConfigurationError: If the configured tool identifier is unsupported.
        """
        configured = self.models["providers"]["anthropic"].get(
            "web_search_tool", "web_search_20260318"
        )
        if configured not in self._ANTHROPIC_WEB_SEARCH_TOOLS:
            raise ConfigurationError(
                "providers.anthropic.web_search_tool must be one of: {}".format(
                    ", ".join(sorted(self._ANTHROPIC_WEB_SEARCH_TOOLS))
                )
            )
        return str(configured)

    def selection(
        self,
        role_key: str,
        provider: Optional[str] = None,
        profile: Optional[str] = None,
        required_capabilities: Optional[Collection[str]] = None,
    ) -> ModelSelection:
        """Return the selection.

        Args:
            role_key (str): The role key text processed when selection.
            provider (Optional[str]): The provider implementation used for generation.
                Defaults to ``None``.
            profile (Optional[str]): The resolved voice, perspective, or content profile.
                Defaults to ``None``.
            required_capabilities (Optional[Collection[str]]): The required capabilities
                value passed to selection. Defaults to ``None``.

        Returns:
            ModelSelection: The resulting model selection for selection.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
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
        """Return the rubric.

        Args:
            name (str): The stable or human-readable name for the domain object.

        Returns:
            Dict[str, Any]: The structured resulting data for rubric.
        """
        return self._read_yaml(self.resources.path("rubrics/{}.yaml".format(name)))

    @property
    def perspective_policy(self) -> Dict[str, Any]:
        """Return the perspective policy.

        Returns:
            Dict[str, Any]: The structured resulting data for perspective policy.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
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
    def publication_provenance_policy(self) -> Dict[str, Any]:
        """Return tracked publication provenance policy.

        Returns:
            Dict[str, Any]: Validated receipt and enforcement settings.

        Raises:
            ConfigurationError: If publication provenance configuration is invalid.
        """
        path = self.root / "content-creator.yaml"
        data = self._read_yaml(path) if path.exists() else {}
        configured = data.get("publication_provenance", {}) or {}
        if not isinstance(configured, dict):
            raise ConfigurationError("publication_provenance configuration must be a mapping")
        policy = {
            "policy": "advisory",
            "receipts_directory": "publication-receipts",
            "semantic_review": "selected-perspectives",
        }
        policy.update(configured)
        if policy["policy"] not in {
            "off",
            "advisory",
            "required-for-new-publications",
            "required",
        }:
            raise ConfigurationError(
                "publication_provenance.policy must be off, advisory, "
                "required-for-new-publications, or required"
            )
        receipts = Path(str(policy["receipts_directory"]))
        if receipts.is_absolute() or ".." in receipts.parts or receipts == Path("."):
            raise ConfigurationError(
                "publication_provenance.receipts_directory must stay inside the workspace"
            )
        if policy["semantic_review"] not in {"off", "selected-perspectives"}:
            raise ConfigurationError(
                "publication_provenance.semantic_review must be off or selected-perspectives"
            )
        return policy

    @property
    def coordinator_policy(self) -> Dict[str, Any]:
        """Return the coordinator policy.

        Returns:
            Dict[str, Any]: The structured resulting data for coordinator policy.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
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
        """Return the diagnostic policy.

        Returns:
            Dict[str, Any]: The structured resulting data for diagnostic policy.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
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
        if (
            isinstance(policy["max_attempts"], bool)
            or not isinstance(policy["max_attempts"], int)
            or not (1 <= policy["max_attempts"] <= 3)
        ):
            raise ConfigurationError("diagnostics.max_attempts must be an integer from 1 to 3")
        if policy["defer_recovered_until_publication"] is not True:
            raise ConfigurationError("diagnostics.defer_recovered_until_publication must be true")
        return policy

    @property
    def statistical_voice_score_policy(self) -> Dict[str, Any]:
        """Return the statistical voice score policy.

        Merge configured statistical-scoring thresholds with safe defaults while preserving
        compatibility with the earlier policy key.

        Returns:
            Dict[str, Any]: The structured resulting data for statistical voice score
                policy.

        Raises:
            ConfigurationError: If the configuration operation cannot complete.
        """
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
        """Return the voice assessment policy.

        Returns:
            Dict[str, Any]: The structured resulting data for voice assessment policy.
        """
        return self.statistical_voice_score_policy
