"""Optional run capabilities kept outside the core orchestration lifecycle."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from .visuals import VisualAdapterRegistry, VisualWorkflow
from .voice_assessment import assess_voice_draft, resolve_score_policy


class RunCapabilities(Protocol):
    """Narrow seam for add-ons that may enrich, but never own, a run."""

    visuals: VisualWorkflow

    def assess_voice(
        self,
        voice_id: str,
        voice_version: Optional[str],
        draft: str,
        configured_policy: Dict[str, Any],
        eligible: bool,
    ) -> Optional[Dict[str, Any]]: ...


class DefaultRunCapabilities:
    """Built-in adapters for optional visual and statistical voice features."""

    def __init__(
        self,
        root: Path,
        visual_adapters: Optional[VisualAdapterRegistry] = None,
    ):
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
