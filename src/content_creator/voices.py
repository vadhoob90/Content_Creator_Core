"""Provide voices capabilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import slugify
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
    VoiceRejectionReceipt as VoiceRejectionReceipt,
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
        epoch_id, learning_hash, epoch_status = _learning_epoch_metadata(
            self.root, voice_id, resolved_version
        )
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
            "evidence_baseline_hash": manifest.evidence_baseline_hash,
            "learning_epoch_id": epoch_id,
            "learning_epoch_hash": learning_hash,
            "learning_epoch_status": epoch_status,
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

    def reject(
        self,
        voice_id: str,
        candidate_hash: str,
        rejected_by: str,
        reason: str,
    ) -> VoiceRejectionReceipt:
        """Reject one exact candidate without changing the active voice.

        Args:
            voice_id (str): Stable selected voice identifier.
            candidate_hash (str): Reviewed candidate hash that must still be current.
            rejected_by (str): Human identity recorded with the rejection.
            reason (str): Human explanation for rejecting the candidate.

        Returns:
            VoiceRejectionReceipt: Immutable evidence of the rejection decision.
        """
        from .voice_rejection import reject_candidate

        return reject_candidate(self, voice_id, candidate_hash, rejected_by, reason)

    def deactivate(
        self,
        voice_id: str,
        reason: str,
        deactivated_by: str = "repository-owner",
        *,
        clear_default: bool = False,
        replacement_voice: Optional[str] = None,
    ) -> Dict:
        """Deactivate the voice registry workflow.

        Args:
            voice_id (str): The stable identifier for the selected voice.
            reason (str): The human-readable reason recorded for the decision.
            deactivated_by (str): Human identity recorded with the pause decision. Defaults to
                ``"repository-owner"``.
            clear_default (bool): Explicitly clear the workspace default. Defaults to ``False``.
            replacement_voice (Optional[str]): Reviewed replacement. Defaults to ``None``.

        Returns:
            Dict: The structured resulting data for deactivate.

        """
        from .voice_lifecycle import VoiceLifecycleService

        return (
            VoiceLifecycleService(self)
            .deactivate(
                voice_id,
                deactivated_by,
                reason,
                clear_default=clear_default,
                replacement_voice=replacement_voice,
            )
            .model_dump(mode="json")
        )

    def reactivate(
        self, voice_id: str, approved_by: str, reason: str = "author reactivation"
    ) -> Dict:
        """Restore an unchanged selected version with an immutable receipt.

        Args:
            voice_id (str): Stable selected voice identifier.
            approved_by (str): Human identity approving reactivation.
            reason (str): Human-readable explanation. Defaults to ``"author reactivation"``.

        Returns:
            Dict: Structured immutable reactivation receipt.
        """
        from .voice_lifecycle import VoiceLifecycleService

        return (
            VoiceLifecycleService(self)
            .reactivate(voice_id, approved_by, reason)
            .model_dump(mode="json")
        )

    def retirement_plan(self, voice_id: str) -> Dict:
        """Return a hash-bound read-only retirement inventory.

        Args:
            voice_id (str): Stable selected voice identifier.

        Returns:
            Dict: Persisted-state retirement inventory and binding hash.
        """
        from .voice_lifecycle import VoiceLifecycleService

        return VoiceLifecycleService(self).plan(voice_id).model_dump(mode="json")

    def retire(
        self,
        voice_id: str,
        retired_by: str,
        reason: str,
        plan_hash: str,
        **decisions: Any,
    ) -> Dict:
        """Retire a voice after validating the reviewed preflight and decisions.

        Args:
            voice_id (str): Stable selected voice identifier.
            retired_by (str): Human identity responsible for retirement.
            reason (str): Human-readable retirement explanation.
            plan_hash (str): Exact reviewed retirement plan hash.
            **decisions (dict[str, Any]): Explicit aggregate and default dispositions.

        Returns:
            Dict: Structured immutable retirement receipt.
        """
        from .voice_lifecycle import VoiceLifecycleService, VoiceRetirementDecisions

        return (
            VoiceLifecycleService(self)
            .retire(
                voice_id,
                retired_by,
                reason,
                plan_hash,
                VoiceRetirementDecisions(**decisions),
            )
            .model_dump(mode="json")
        )

    def restore(self, voice_id: str, requested_by: str, approved_by: str, plan_hash: str) -> Dict:
        """Restore a retired voice through a hash-bound reviewed path.

        Args:
            voice_id (str): Stable selected voice identifier.
            requested_by (str): Human identity requesting restoration.
            approved_by (str): Human identity approving restoration.
            plan_hash (str): Exact reviewed restoration plan hash.

        Returns:
            Dict: Structured immutable restoration receipt.
        """
        from .voice_lifecycle import VoiceLifecycleService

        return (
            VoiceLifecycleService(self)
            .restore(voice_id, requested_by, approved_by, plan_hash)
            .model_dump(mode="json")
        )

    def migrate_legacy_lifecycle(self, voice_id: str, migrated_by: str) -> Dict:
        """Record a reviewed receipt for a legacy registry-only inactive state.

        Args:
            voice_id (str): Stable selected voice identifier.
            migrated_by (str): Human identity reviewing the legacy state.

        Returns:
            Dict: Structured immutable legacy migration receipt.
        """
        from .voice_lifecycle import VoiceLifecycleService

        return (
            VoiceLifecycleService(self)
            .migrate_legacy(voice_id, migrated_by)
            .model_dump(mode="json")
        )

    def verify_lifecycle(self, voice_id: str) -> Dict:
        """Verify lifecycle receipts and the separate version catalogue offline.

        Args:
            voice_id (str): Stable selected voice identifier.

        Returns:
            Dict: Deterministic receipt and catalogue verification result.
        """
        from .voice_lifecycle import VoiceLifecycleService

        return VoiceLifecycleService(self).verify(voice_id)


def _learning_epoch_metadata(
    root: Path, voice_id: str, voice_version: str
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Return persisted epoch identity without synthesizing legacy history.

    Args:
        root (Path): Workspace root containing voice learning epochs.
        voice_id (str): Stable selected voice identifier.
        voice_version (str): Immutable selected voice version.

    Returns:
        tuple[Optional[str], Optional[str], Optional[str]]: Epoch ID, canonical hash,
            and status, or three ``None`` values when no version epoch was persisted.
    """
    from .voice_upgrade.epochs import epoch_hash, epoch_path, load_epoch

    path = epoch_path(root, voice_id, voice_version)
    if not path.is_file():
        return None, None, None
    epoch = load_epoch(root, voice_id, voice_version, migrate_legacy=False)
    return epoch.epoch_id, epoch_hash(epoch), epoch.status


def voice_id_for(name: str) -> str:
    """Return the voice id for.

    Args:
        name (str): The stable or human-readable name for the domain object.

    Returns:
        str: The resulting text for voice id for.
    """
    return slugify(name)
