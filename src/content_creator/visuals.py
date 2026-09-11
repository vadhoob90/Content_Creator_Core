"""Provide visuals capabilities."""

from __future__ import annotations

import base64
import hashlib
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .domain import RunStatus, utc_now
from .storage import RunStore, StorageError
from .versioned_artifacts import hash_file
from .visual_contracts import (
    BoundingBox as BoundingBox,
)
from .visual_contracts import (
    CropProfile as CropProfile,
)
from .visual_contracts import (
    DiagnosticSeverity as DiagnosticSeverity,
)
from .visual_contracts import (
    ExecutionClass as ExecutionClass,
)
from .visual_contracts import (
    RightsStatus as RightsStatus,
)
from .visual_contracts import (
    SafeAreaProfile as SafeAreaProfile,
)
from .visual_contracts import (
    VisualAdapter as VisualAdapter,
)
from .visual_contracts import (
    VisualAdapterRegistry as VisualAdapterRegistry,
)
from .visual_contracts import (
    VisualApprovalStatus as VisualApprovalStatus,
)
from .visual_contracts import (
    VisualAsset as VisualAsset,
)
from .visual_contracts import (
    VisualBrief as VisualBrief,
)
from .visual_contracts import (
    VisualCritique as VisualCritique,
)
from .visual_contracts import (
    VisualDecision as VisualDecision,
)
from .visual_contracts import (
    VisualDiagnostic as VisualDiagnostic,
)
from .visual_contracts import (
    VisualError as VisualError,
)
from .visual_contracts import (
    VisualManifest as VisualManifest,
)
from .visual_contracts import (
    VisualOutput as VisualOutput,
)
from .visual_contracts import (
    VisualPackProfile as VisualPackProfile,
)
from .visual_contracts import (
    VisualSource as VisualSource,
)
from .visual_contracts import (
    VisualValidation as VisualValidation,
)
from .visual_mutation import serialize_visual
from .visual_rendering import default_visual_adapters
from .visual_slots import brief_path, decide_slot, prepare_slot, selected_slots, slot_for
from .visual_validation import VisualValidator


class VisualWorkflow:
    """Represent a visual workflow."""

    def __init__(self, root: Path, adapter_registry: Optional[VisualAdapterRegistry] = None):
        """Initialize the visual workflow with its required state and collaborators.

        Args:
            root (Path): The workspace root directory.
            adapter_registry (Optional[VisualAdapterRegistry]): The adapter registry value
                passed to init. Defaults to ``None``.

        Returns:
            None: The instance is initialized in place and no value is returned.
        """
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.adapters = adapter_registry or default_visual_adapters()

    @serialize_visual
    def create_brief(self, brief: VisualBrief, profile: VisualPackProfile) -> VisualBrief:
        """Create the brief.

        Args:
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.

        Returns:
            VisualBrief: The created visual brief for brief.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        if brief.slot_id:
            return prepare_slot(self.store, brief, profile)
        existing = self.store.run_dir(brief.run_id) / "visuals/manifest.json"
        if existing.exists() and self._load_manifest(brief.run_id).slots:
            raise VisualError("Specify a slot for a multi-slot run")
        state = self.store.load(brief.run_id)
        if state.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR, RunStatus.PUBLISHED}:
            raise VisualError("Visual briefs require reviewed content")
        if not profile.supported:
            raise VisualError("The selected content pack does not support visual assets")
        unsupported_ratios = sorted(set(brief.aspect_ratios) - set(profile.aspect_ratios))
        unsupported_formats = sorted(
            value for value in set(brief.output_formats) - set(profile.formats)
        )
        if unsupported_ratios or unsupported_formats:
            raise VisualError(
                "Visual brief requests unsupported outputs: {}".format(
                    ", ".join(unsupported_ratios + unsupported_formats)
                )
            )
        if not brief.alt_text.strip() and profile.require_alt_text:
            raise VisualError("Visual brief requires accessibility alt text")
        visuals = self.store.run_dir(brief.run_id) / "visuals"
        for directory in ("concepts", "revisions", "selected", "previews"):
            (visuals / directory).mkdir(parents=True, exist_ok=True)
        self.store.write_artifact(brief.run_id, "visual_brief.json", brief)
        manifest = (
            self._load_manifest(brief.run_id)
            if existing.exists()
            else VisualManifest(run_id=brief.run_id)
        )
        manifest.components = brief.components
        manifest.selected_asset_id = None
        self._save_manifest(manifest)
        return brief

    @serialize_visual
    def execute(
        self,
        run_id: str,
        adapter_name: Optional[str] = None,
        parent_asset_id: Optional[str] = None,
        variant_name: Optional[str] = None,
        slot_id: Optional[str] = None,
    ) -> VisualAsset:
        """Execute the visual workflow workflow.

        Resolve the selected visual adapter, render the asset, validate pack constraints,
        and persist diagnostics and manifest state.

        Args:
            run_id (str): The stable identifier for the content run.
            adapter_name (Optional[str]): The adapter name text processed when execute.
                Defaults to ``None``.
            parent_asset_id (Optional[str]): The stable identifier for the parent asset.
                Defaults to ``None``.
            variant_name (Optional[str]): Stable review variant label. Defaults to ``None``.
            slot_id (Optional[str]): Explicit placement for multi-slot runs. Defaults to ``None``.

        Returns:
            VisualAsset: The resulting visual asset for execute.

        Raises:
            VisualError: If slot ownership or renderer capability is incompatible.
        """
        brief = self._load_brief(run_id, slot_id)
        manifest = self._load_manifest(run_id)
        adapter = self.adapters.get(adapter_name) if adapter_name else self.adapters.route(brief)
        parent = self._asset(manifest, parent_asset_id) if parent_asset_id else None
        if parent and parent.slot_id != slot_id:
            raise VisualError("A visual revision must remain in its original slot")
        if (
            brief.role in {"article-inline-diagram", "comparison", "facts-panel"}
            and adapter.name == "core-deterministic-svg"
        ):
            raise VisualError("This role requires a compatible adapter or governed import")
        rendered = adapter.render(brief, parent)
        output = (
            rendered
            if adapter.name == "governed-import"
            else self._apply_locked_assets(rendered, brief)
        )
        asset_id = uuid4().hex[:12]
        revision = parent.revision + 1 if parent else 1
        directory = "revisions" if parent else "concepts"
        suffix = output.format.lower().lstrip(".")
        relative = "visuals/{}/{}.{}".format(directory, asset_id, suffix)
        path = self.store.run_dir(run_id) / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(output.content)
        asset = VisualAsset(
            asset_id=asset_id,
            slot_id=brief.slot_id,
            brief_revision=brief.brief_revision,
            brief_sha256=hash_file(
                self.store.run_dir(run_id) / brief_path(brief.slot_id, brief.brief_revision)
            )
            if brief.slot_id
            else None,
            parent_asset_id=parent.asset_id if parent else None,
            revision=revision,
            variant_name=variant_name,
            role=brief.role,
            execution_class=adapter.execution_class,
            adapter=adapter.name,
            provider=str(output.metadata.get("provider") or "") or None,
            model_or_renderer=adapter.model_or_renderer,
            prompt_or_template_version=adapter.prompt_or_template_version,
            source_ids=[item.source_id for item in brief.sources],
            sources=brief.sources,
            alt_text=brief.alt_text,
            relative_path=relative,
            sha256=hashlib.sha256(output.content).hexdigest(),
            width=output.width,
            height=output.height,
            format=suffix,
            size_bytes=len(output.content),
            extracted_copy=output.extracted_copy,
            content_boxes=output.content_boxes,
            metadata=output.metadata,
            components=brief.components,
        )
        manifest.assets.append(asset)
        self._save_manifest(manifest)
        return asset

    def _apply_locked_assets(self, output: VisualOutput, brief: VisualBrief) -> VisualOutput:
        """Verify locked assets and overlay their exact bytes on SVG output.

        Args:
            output (VisualOutput): Newly rendered provider-neutral visual bytes.
            brief (VisualBrief): Reviewed brief containing immutable asset references.

        Returns:
            VisualOutput: Original output with verified provenance or exact SVG overlays.

        Raises:
            VisualError: If a locked asset is missing, changed, or outside the workspace.
        """
        if not brief.locked_assets:
            return output
        encoded_assets = []
        for reference in brief.locked_assets:
            path = (self.root / reference.path).resolve()
            try:
                path.relative_to(self.root)
            except ValueError as exc:
                raise VisualError("Locked brand asset path leaves the workspace") from exc
            if not path.is_file() or hash_file(path) != reference.sha256:
                raise VisualError(
                    "Locked brand asset is missing or changed: {}".format(reference.id)
                )
            encoded_assets.append((reference, base64.b64encode(path.read_bytes()).decode("ascii")))
        output.metadata["locked_asset_ids"] = [item.id for item, _ in encoded_assets]
        if output.format.lower().lstrip(".") != "svg":
            return output
        document = output.content.decode("utf-8")
        overlays = []
        for index, (reference, encoded) in enumerate(encoded_assets):
            overlays.append(
                '<image data-locked-asset="{}" x="{}" y="{}" width="160" height="64" '
                'preserveAspectRatio="xMidYMid meet" href="data:{};base64,{}"/>'.format(
                    reference.id,
                    max(0, output.width - 210),
                    max(0, output.height - 90 - (index * 76)),
                    reference.mime_type,
                    encoded,
                )
            )
        output.content = document.replace(
            "</svg>",
            "  {}\n</svg>".format("\n  ".join(overlays)),
        ).encode("utf-8")
        return output

    @serialize_visual
    def validate(
        self,
        run_id: str,
        asset_id: str,
        profile: VisualPackProfile,
    ) -> VisualValidation:
        """Validate the visual workflow workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            asset_id (str): The stable identifier for the asset.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.

        Returns:
            VisualValidation: The validated visual validation for value.
        """
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        brief = self._load_brief(run_id, asset.slot_id, asset.brief_revision)
        result = VisualValidator().validate(asset, brief, profile)
        asset.validation = result
        self._save_manifest(manifest)
        self.store.write_artifact(run_id, self._evidence_path(asset, "validation"), result)
        return result

    @serialize_visual
    def record_critique(self, run_id: str, asset_id: str, critique: VisualCritique) -> VisualAsset:
        """Record the critique.

        Args:
            run_id (str): The stable identifier for the content run.
            asset_id (str): The stable identifier for the asset.
            critique (VisualCritique): The critique value passed to record critique.

        Returns:
            VisualAsset: The resulting visual asset for record critique.
        """
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        asset.critique = critique
        asset.status = VisualApprovalStatus.CRITIQUED
        self._save_manifest(manifest)
        self.store.write_artifact(run_id, self._evidence_path(asset, "critique"), critique)
        return asset

    @serialize_visual
    def select(self, run_id: str, asset_id: str) -> VisualAsset:
        """Select the visual workflow workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            asset_id (str): The stable identifier for the asset.

        Returns:
            VisualAsset: The selected visual asset for value.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        if asset.slot_id:
            return decide_slot(self.store, manifest, asset, False)
        if manifest.slots:
            raise VisualError("Legacy assets must be migrated before slot selection")
        if not asset.validation or not asset.validation.passed:
            raise VisualError("Only a validated visual asset can be selected")
        if asset.critique is None:
            raise VisualError("Only a critiqued visual asset can be selected")
        for candidate in manifest.assets:
            if candidate.status == VisualApprovalStatus.SELECTED:
                candidate.status = VisualApprovalStatus.CRITIQUED
        asset.status = VisualApprovalStatus.SELECTED
        manifest.selected_asset_id = asset.asset_id
        self._save_manifest(manifest)
        self.store.write_artifact(
            run_id,
            "visuals/decision.json",
            VisualDecision(
                run_id=run_id,
                selected_asset_id=asset.asset_id,
                decision="selected",
                approval_state=asset.status,
            ),
        )
        return asset

    @serialize_visual
    def approve(self, run_id: str, asset_id: str) -> VisualAsset:
        """Approve the visual workflow workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            asset_id (str): The stable identifier for the asset.

        Returns:
            VisualAsset: The resulting visual asset for approve.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        if asset.slot_id:
            return decide_slot(self.store, manifest, asset, True)
        if manifest.slots:
            raise VisualError("Legacy assets must be migrated before slot selection")
        if manifest.selected_asset_id != asset.asset_id:
            raise VisualError("Author approval requires the selected asset")
        if not asset.validation or not asset.validation.passed:
            raise VisualError("Author approval requires a passing validation")
        asset.status = VisualApprovalStatus.APPROVED
        self._save_manifest(manifest)
        brief = self._load_brief(run_id)
        brief.author_approval = VisualApprovalStatus.APPROVED
        self.store.write_artifact(run_id, "visual_brief.json", brief)
        self.store.write_artifact(
            run_id,
            "visuals/decision.json",
            VisualDecision(
                run_id=run_id,
                selected_asset_id=asset.asset_id,
                decision="approved",
                approval_state=asset.status,
            ),
        )
        return asset

    def replacement_asset(
        self, run_id: str, asset_id: str, profile: VisualPackProfile
    ) -> VisualAsset:
        """Validate one approved replacement without changing other pending selections.

        Args:
            run_id (str): Published run identifier.
            asset_id (str): Explicit replacement candidate.
            profile (VisualPackProfile): Pack publication policy.

        Returns:
            VisualAsset: Selected approved replacement candidate.

        Raises:
            VisualError: If the candidate is not the selected approved replacement.
        """
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        if asset.slot_id:
            slot = slot_for(manifest, asset.slot_id)
            selection = selected_slots(
                self.store, manifest.model_copy(update={"slots": [slot]}), approved=True
            )
            if selection[0].asset_id == asset_id:
                return asset
        elif self.ensure_publication_ready(run_id, profile) == asset:
            return asset
        raise VisualError("Replacement requires the selected approved asset for its slot")

    def ensure_publication_assets(
        self, run_id: str, profile: VisualPackProfile
    ) -> list[VisualAsset]:
        """Return the complete approved visual collection for publication.

        Args:
            run_id (str): Reviewed run identifier.
            profile (VisualPackProfile): Pack publication policy.

        Returns:
            list[VisualAsset]: Every approved placement, including legacy singleton selection.

        Raises:
            VisualError: If selected slots have no publication destination.
        """
        path = self.store.run_dir(run_id) / "visuals/manifest.json"
        if path.exists():
            manifest = self._load_manifest(run_id)
            if manifest.slots:
                if not profile.destination:
                    raise VisualError("Visual slots have no publication destination")
                return selected_slots(self.store, manifest, approved=True)
        asset = self.ensure_publication_ready(run_id, profile)
        return [asset] if asset else []

    def ensure_publication_ready(
        self, run_id: str, profile: VisualPackProfile
    ) -> Optional[VisualAsset]:
        """Return the ensure publication ready.

        Args:
            run_id (str): The stable identifier for the content run.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.

        Returns:
            Optional[VisualAsset]: The resulting ensure publication ready when available;
                otherwise ``None``.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        manifest_path = self.store.run_dir(run_id) / "visuals" / "manifest.json"
        if not manifest_path.exists():
            if profile.required:
                raise VisualError("This content pack requires an approved visual asset")
            return None
        manifest = self._load_manifest(run_id)
        if manifest.slots:
            raise VisualError("Use the complete visual collection for a multi-slot run")
        if not manifest.selected_asset_id:
            raise VisualError("The visual manifest has no selected publication asset")
        asset = self._asset(manifest, manifest.selected_asset_id)
        if asset.status != VisualApprovalStatus.APPROVED:
            raise VisualError("The selected visual asset has not been approved by the author")
        if not asset.validation or not asset.validation.passed:
            raise VisualError("The selected visual asset has not passed validation")
        if not profile.destination:
            raise VisualError("The active visual asset has no known publication consumer")
        source = self.store.run_dir(run_id) / asset.relative_path
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != asset.sha256:
            raise VisualError("Selected visual asset is missing or its hash has changed")
        return asset

    @serialize_visual
    def publish(self, run_id: str, profile: VisualPackProfile) -> Optional[Path]:
        """Publish the visual workflow workflow.

        Args:
            run_id (str): The stable identifier for the content run.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.

        Returns:
            Optional[Path]: The resolved filesystem path for publish.

        Raises:
            StorageError: If the storage operation cannot complete.
            VisualError: If the visual operation cannot complete.
        """
        asset = self.ensure_publication_ready(run_id, profile)
        if asset is None:
            return None
        source = self.store.run_dir(run_id) / asset.relative_path
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != asset.sha256:
            raise VisualError("Selected visual asset is missing or its hash has changed")
        target = self.publication_target(run_id, asset, profile)
        if target.exists():
            raise StorageError("Refusing to overwrite {}".format(target))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        self.mark_published(run_id, asset.asset_id, target)
        return target

    def publication_target(
        self,
        run_id: str,
        asset: VisualAsset,
        profile: VisualPackProfile,
    ) -> Path:
        """Return the validated publication destination for one visual asset.

        Args:
            run_id (str): Run containing the selected visual asset.
            asset (VisualAsset): Selected visual lifecycle record.
            profile (VisualPackProfile): Resolved pack destination policy.

        Returns:
            Path: Immutable visual destination beneath the author workspace.

        Raises:
            VisualError: If the configured destination leaves the workspace.
        """
        destination = (self.root / str(profile.destination)).resolve()
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise VisualError("Visual publication destination leaves the workspace") from exc
        return destination / "{}-{}.{}".format(run_id, asset.asset_id, asset.format)

    def mark_published(self, run_id: str, asset_id: str, target: Path) -> None:
        """Record package-published media after all destination writes succeed.

        Args:
            run_id (str): Run containing the visual manifest.
            asset_id (str): Selected visual asset identifier.
            target (Path): Published immutable media destination.

        Returns:
            None: The selected asset and manifest are updated in place.
        """
        manifest = self._load_manifest(run_id)
        selected = self._asset(manifest, asset_id)
        selected.status = VisualApprovalStatus.PUBLISHED
        if selected.slot_id:
            slot_for(manifest, selected.slot_id).published_path = str(target.relative_to(self.root))
        else:
            manifest.published_path = str(target.relative_to(self.root))
        self._save_manifest(manifest)

    def _load_brief(
        self, run_id: str, slot_id: Optional[str] = None, revision: Optional[int] = None
    ) -> VisualBrief:
        """Load the brief.

        Args:
            run_id (str): The stable identifier for the content run.
            slot_id (Optional[str]): Explicit placement. Defaults to ``None``.
            revision (Optional[int]): Immutable brief revision. Defaults to ``None``.

        Returns:
            VisualBrief: The loaded visual brief for brief.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        manifest_path = self.store.run_dir(run_id) / "visuals/manifest.json"
        if slot_id:
            slot = slot_for(self._load_manifest(run_id), slot_id)
            return VisualBrief.model_validate_json(
                self.store.read_artifact(
                    run_id, brief_path(slot.slot_id, revision or slot.brief_revision)
                )
            )
        if manifest_path.exists() and self._load_manifest(run_id).slots:
            raise VisualError("Specify a slot for a multi-slot run")
        try:
            return VisualBrief.model_validate_json(
                self.store.read_artifact(run_id, "visual_brief.json")
            )
        except StorageError as exc:
            raise VisualError("Run has no visual brief") from exc

    def _load_manifest(self, run_id: str) -> VisualManifest:
        """Load the manifest.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            VisualManifest: The loaded visual manifest for manifest.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        path = self.store.run_dir(run_id) / "visuals" / "manifest.json"
        if not path.exists():
            raise VisualError("Run has no visual manifest")
        return VisualManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def asset(self, run_id: str, asset_id: str) -> VisualAsset:
        """Return one persisted visual asset with its latest lifecycle evidence.

        Args:
            run_id (str): Stable content run identifier.
            asset_id (str): Stable visual asset identifier.

        Returns:
            VisualAsset: Current persisted asset state.

        """
        return self._asset(self._load_manifest(run_id), asset_id)

    def _save_manifest(self, manifest: VisualManifest) -> None:
        """Save the manifest.

        Args:
            manifest (VisualManifest): The manifest that records the artifact contract.

        Returns:
            None: The callable updates manifest state and returns no value.
        """
        manifest.updated_at = utc_now().isoformat()
        self.store.write_artifact(manifest.run_id, "visuals/manifest.json", manifest)

    @staticmethod
    def _evidence_path(asset: VisualAsset, kind: str) -> str:
        """Return candidate-specific review evidence paths for slot assets.

        Args:
            asset (VisualAsset): Candidate being validated or critiqued.
            kind (str): Evidence kind.

        Returns:
            str: Run-relative evidence path.
        """
        if asset.slot_id:
            directory = f"visuals/slots/{asset.slot_id}/r{asset.brief_revision:04d}"
            return f"{directory}/{asset.asset_id}-{kind}.json"
        return f"visuals/{kind}.json"

    @staticmethod
    def _asset(manifest: VisualManifest, asset_id: Optional[str]) -> VisualAsset:
        """Return the asset.

        Args:
            manifest (VisualManifest): The manifest that records the artifact contract.
            asset_id (Optional[str]): The stable identifier for the asset.

        Returns:
            VisualAsset: The resulting visual asset for asset.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
        for asset in manifest.assets:
            if asset.asset_id == asset_id:
                return asset
        raise VisualError("Unknown visual asset: {}".format(asset_id))
