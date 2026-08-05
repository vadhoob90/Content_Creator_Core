"""Provide capabilities contracts and behavior."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from .visuals import VisualAdapterRegistry, VisualWorkflow
from .voice_assessment import assess_voice_draft, resolve_score_policy


class RunCapabilities(Protocol):
    """Represent the run capabilities contract."""

    visuals: VisualWorkflow

    def assess_voice(
        self,
        voice_id: str,
        voice_version: Optional[str],
        draft: str,
        configured_policy: Dict[str, Any],
        eligible: bool,
    ) -> Optional[Dict[str, Any]]:
        """Assess the voice.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            voice_version (Optional[str]): The immutable version of the selected voice
                profile.
            draft (str): The draft content to evaluate or transform.
            configured_policy (Dict[str, Any]): The configured policy collection consumed
                while assess voice.
            eligible (bool): Whether eligible behavior is enabled.

        Returns:
            Optional[Dict[str, Any]]: The assessment voice when available; otherwise
                ``None``.

        Raises:
            NotImplementedError: If the not implemented operation cannot complete.
        """
        raise NotImplementedError


class DefaultRunCapabilities:
    """Represent the default run capabilities contract."""

    def __init__(
        self,
        root: Path,
        visual_adapters: Optional[VisualAdapterRegistry] = None,
    ):
        """Initialize the default run capabilities.

        Args:
            root (Path): The workspace root directory.
            visual_adapters (Optional[VisualAdapterRegistry]): The visual adapters value
                passed to init. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.visuals = VisualWorkflow(self.root, visual_adapters)

    def assess_voice(
        self,
        voice_id: str,
        voice_version: Optional[str],
        draft: str,
        configured_policy: Dict[str, Any],
        eligible: bool,
    ) -> Optional[Dict[str, Any]]:
        """Assess the voice.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            voice_version (Optional[str]): The immutable version of the selected voice
                profile.
            draft (str): The draft content to evaluate or transform.
            configured_policy (Dict[str, Any]): The configured policy collection consumed
                while assess voice.
            eligible (bool): Whether eligible behavior is enabled.

        Returns:
            Optional[Dict[str, Any]]: The assessment voice when available; otherwise
                ``None``.
        """
        policy = resolve_score_policy(self.root, voice_id, configured_policy)
        if not policy["enabled"] or not eligible:
            return None
        return assess_voice_draft(
            self.root,
            voice_id,
            voice_version,
            draft,
            policy,
        )
