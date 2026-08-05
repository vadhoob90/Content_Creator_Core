"""Provide voices capabilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import RunStore, slugify
from .versioned_artifacts import (
    hash_file,
    verify_components,
)
from .voice_models import (
    STARTER_TEMPLATE_ID as STARTER_TEMPLATE_ID,
)
from .voice_models import (
    AttributionResult as AttributionResult,
)
from .voice_models import (
    Authorisation as Authorisation,
)
from .voice_models import (
    SourceRecord as SourceRecord,
)
from .voice_models import (
    VoiceApprovalReceipt as VoiceApprovalReceipt,
)
from .voice_models import (
    VoiceError as VoiceError,
)
from .voice_models import (
    VoiceManifest as VoiceManifest,
)
from .voice_models import (
    VoiceOnboardingRecord as VoiceOnboardingRecord,
)
from .voice_models import (
    VoicePattern as VoicePattern,
)
from .voice_models import (
    VoiceStatus as VoiceStatus,
)
from .voice_models import (
    VoiceStrategy as VoiceStrategy,
)
from .voice_models import (
    VoiceWorkOrder as VoiceWorkOrder,
)
from .voice_models import (
    load_voice_onboarding as load_voice_onboarding,
)
from .voice_models import (
    onboarding_path as onboarding_path,
)
from .voice_models import (
    save_voice_onboarding as save_voice_onboarding,
)


class VoiceRegistry:
    """Manage voice records."""

    def __init__(self, root: Path):
        """Initialize the voice registry with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.path = self.root / "profiles" / "registry.json"

    def _read(self) -> Dict:
        """Read the voice registry workflow.

        Returns:
            Dict: The structured loaded data for value.
        """
        if not self.path.exists():
            return {"schema_version": "1.0", "profiles": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("schema_version", "1.0")
        data.setdefault("profiles", {})
        return data

    def list(self) -> Dict:
        """List the voice registry workflow.

        Returns:
            Dict: The structured available data for value.
        """
        return self._read()["profiles"]

    def get(self, voice_id: str) -> Dict:
        """Retrieve the voice registry managed by voice registry.

        Args:
            voice_id (str): The stable identifier for the selected voice.

        Returns:
            Dict: The structured resulting data for get.

        Raises:
            VoiceError: If the voice operation cannot complete.
        """
        item = self.list().get(voice_id)
        if not item:
            raise VoiceError("Unknown voice: {}".format(voice_id))
        return item

    def resolve(
        self,
        voice_id: str,
        version: Optional[str] = None,
        allow_inactive: bool = False,
    ) -> Dict:
        """Resolve the voice registry workflow.

        Resolve an active voice and immutable version, verify its artifact hashes, and
        reject inactive records unless explicitly allowed.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            version (Optional[str]): The immutable artifact or schema version identifier.
                Defaults to ``None``.
            allow_inactive (bool): Whether allow inactive behavior is enabled. Defaults to
                ``False``.

        Returns:
            Dict: The structured resolved data for value.

        Raises:
            VoiceError: If the voice operation cannot complete.
        """
        if voice_id == "default" and voice_id not in self.list():
            workspace_onboarding = sorted((self.root / "profiles").glob("*/onboarding.json"))
            if workspace_onboarding:
                intended = [
                    VoiceOnboardingRecord.model_validate_json(
                        path.read_text(encoding="utf-8")
                    ).voice_id
                    for path in workspace_onboarding
                ]
                raise VoiceError(
                    "The default test profile is unavailable in an author "
                    "workspace; complete onboarding and select: {}".format(", ".join(intended))
                )
            return {
                "id": "default",
                "version": "placeholder",
                "status": "active",
                "path": "profiles/default",
                "strategy": "legacy-placeholder",
                "evidence_status": "none",
                "perspectives_allowed": True,
            }
        onboarding = load_voice_onboarding(self.root, voice_id)
        if onboarding and onboarding.status == "undecided":
            raise VoiceError(
                "Voice onboarding decision required for {}: choose starter "
                "or source-derived".format(voice_id)
            )
        if onboarding and onboarding.status == "collecting-sources" and voice_id not in self.list():
            raise VoiceError(
                "Source-derived onboarding for {} is not complete; build, "
                "review, and approve the candidate voice".format(voice_id)
            )
        item = self.get(voice_id)
        resolved_version = version or item.get("active_version")
        if not resolved_version:
            raise VoiceError("Voice {} has no active version".format(voice_id))
        if item.get("status") != VoiceStatus.ACTIVE.value and not allow_inactive:
            raise VoiceError("Voice {} is not active".format(voice_id))
        path = self.root / "profiles" / voice_id / "versions" / resolved_version
        if not path.exists():
            raise VoiceError("Missing voice version {}@{}".format(voice_id, resolved_version))
        manifest_path = path / "manifest.json"
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        if item.get("status") == VoiceStatus.ACTIVE.value and manifest.status != VoiceStatus.ACTIVE:
            raise VoiceError(
                "Voice lifecycle mismatch: registry is active but version manifest is {}".format(
                    manifest.status.value
                )
            )
        mismatches = verify_components(path, manifest.components, manifest.component_hashes)
        if mismatches:
            raise VoiceError("Active voice component hash mismatch: {}".format(mismatches[0]))
        return {
            "id": voice_id,
            "version": resolved_version,
            "status": item.get("status"),
            "version_status": manifest.status.value,
            "lifecycle_authority": "version_manifest",
            "path": str(path.relative_to(self.root)),
            "manifest_hash": hash_file(manifest_path),
            "strategy": manifest.strategy.value,
            "evidence_status": manifest.evidence_status,
            "perspectives_allowed": manifest.perspectives_allowed,
            "template_id": manifest.template_id,
        }

    def activate_starter(
        self,
        voice_id: str,
        display_name: str,
        author_name: str,
        selected_by: str,
        intended_uses: List[str],
        template_id: str = STARTER_TEMPLATE_ID,
    ) -> Dict[str, Any]:
        """Activate the starter.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            display_name (str): The human-readable name shown to users.
            author_name (str): The author's display name.
            selected_by (str): The selected by text processed when activate starter.
            intended_uses (List[str]): The intended uses collection consumed while activate
                starter.
            template_id (str): The stable identifier for the template. Defaults to
                ``STARTER_TEMPLATE_ID``.

        Returns:
            Dict[str, Any]: The structured resulting data for activate starter.
        """
        from .starter_voice import StarterVoiceRequest, activate_starter

        request = StarterVoiceRequest(
            voice_id=voice_id,
            display_name=display_name,
            author_name=author_name,
            selected_by=selected_by,
            intended_uses=intended_uses,
            template_id=template_id,
        )
        return activate_starter(self, request)

    def activate(
        self,
        voice_id: str,
        approved_by: str,
        override_reason: Optional[str] = None,
    ) -> VoiceApprovalReceipt:
        """Activate the voice registry workflow.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            approved_by (str): The reviewer identity recorded with the approval.
            override_reason (Optional[str]): The override reason text processed when
                activate. Defaults to ``None``.

        Returns:
            VoiceApprovalReceipt: The resulting voice approval receipt for activate.
        """
        from .voice_activation import activate_candidate

        return activate_candidate(self, voice_id, approved_by, override_reason)

    def deactivate(self, voice_id: str, reason: str) -> Dict:
        """Deactivate the voice registry workflow.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            reason (str): The human-readable reason recorded for the decision.

        Returns:
            Dict: The structured resulting data for deactivate.

        Raises:
            VoiceError: If the voice operation cannot complete.
        """
        registry = self._read()
        item = registry["profiles"].get(voice_id)
        if not item:
            raise VoiceError("Unknown voice: {}".format(voice_id))
        item["status"] = VoiceStatus.INACTIVE.value
        item["deactivation_reason"] = reason
        item["deactivated_at"] = datetime.now(UTC).isoformat()
        RunStore._atomic_text(self.path, json.dumps(registry, indent=2))
        return item


def voice_id_for(name: str) -> str:
    """Return the voice id for.

    Args:
        name (str): The stable or human-readable name for the domain object.

    Returns:
        str: The resulting text for voice id for.
    """
    return slugify(name)
