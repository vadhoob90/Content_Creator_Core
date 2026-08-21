"""Provide visuals capabilities."""

from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path
from typing import List, Optional
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
from .visual_rendering import default_visual_adapters


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
        self._save_manifest(VisualManifest(run_id=brief.run_id, components=brief.components))
        return brief

    def execute(
        self,
        run_id: str,
        adapter_name: Optional[str] = None,
        parent_asset_id: Optional[str] = None,
        variant_name: Optional[str] = None,
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

        Returns:
            VisualAsset: The resulting visual asset for execute.
        """
        brief = self._load_brief(run_id)
        manifest = self._load_manifest(run_id)
        adapter = self.adapters.get(adapter_name) if adapter_name else self.adapters.route(brief)
        parent = self._asset(manifest, parent_asset_id) if parent_asset_id else None
        output = self._apply_locked_assets(adapter.render(brief, parent), brief)
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
            components=manifest.components,
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
        brief = self._load_brief(run_id)
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        diagnostics: List[VisualDiagnostic] = []
        self._validate_asset_basics(asset, brief, profile, diagnostics)
        self._validate_copy(asset, brief, diagnostics)
        self._validate_safe_areas(asset, brief, profile, diagnostics)
        self._validate_crops(asset, brief, profile, diagnostics)
        result = VisualValidation(
            passed=not any(item.severity == DiagnosticSeverity.ERROR for item in diagnostics),
            diagnostics=diagnostics,
        )
        asset.validation = result
        self._save_manifest(manifest)
        self.store.write_artifact(run_id, "visuals/validation.json", result)
        return result

    def _validate_asset_basics(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        profile: VisualPackProfile,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the asset basics.

        Args:
            asset (VisualAsset): The asset value passed to validate asset basics.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates asset basics state and returns no value.
        """
        ratio = self._ratio(asset.width, asset.height)
        if not any(
            self._ratio_matches(asset.width, asset.height, item) for item in profile.aspect_ratios
        ):
            diagnostics.append(self._error("unsupported-aspect-ratio", ratio))
        if asset.format not in [value.lower().lstrip(".") for value in profile.formats]:
            diagnostics.append(self._error("unsupported-format", asset.format))
        if asset.execution_class not in profile.execution_classes:
            diagnostics.append(
                self._error("unsupported-execution-class", asset.execution_class.value)
            )
        if profile.max_file_size_bytes and asset.size_bytes > profile.max_file_size_bytes:
            diagnostics.append(self._error("file-too-large", str(asset.size_bytes)))
        if profile.require_alt_text and not brief.alt_text.strip():
            diagnostics.append(self._error("missing-alt-text", "Alt text is required"))
        if profile.require_provenance:
            unresolved = [
                item.source_id
                for item in brief.sources
                if item.rights_status == RightsStatus.UNVERIFIED
            ]
            if unresolved:
                diagnostics.append(self._error("unresolved-reuse-rights", ", ".join(unresolved)))

    def _validate_copy(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the copy.

        Args:
            asset (VisualAsset): The asset value passed to validate copy.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates copy state and returns no value.
        """
        if brief.exact_copy:
            if asset.extracted_copy is None:
                diagnostics.append(
                    self._error(
                        "exact-copy-unverified",
                        "The adapter did not supply OCR or deterministic copy evidence",
                    )
                )
            elif self._normalise_copy(asset.extracted_copy) != self._normalise_copy(
                brief.exact_copy
            ):
                diagnostics.append(
                    self._error("exact-copy-mismatch", "Rendered copy differs from the brief")
                )

    def _validate_safe_areas(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        profile: VisualPackProfile,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the safe areas.

        Args:
            asset (VisualAsset): The asset value passed to validate safe areas.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates safe areas state and returns no value.
        """
        safe_areas = {item.id: item for item in profile.safe_areas}
        for profile_id in brief.safe_area_profiles:
            safe = safe_areas.get(profile_id)
            if safe is None:
                diagnostics.append(self._error("unknown-safe-area", profile_id))
                continue
            for box in asset.content_boxes:
                if box.role in safe.applies_to_roles and not self._inside_safe_area(box, safe):
                    diagnostics.append(
                        self._error("unsafe-placement", box.role, profile=profile_id)
                    )

    def _validate_crops(
        self,
        asset: VisualAsset,
        brief: VisualBrief,
        profile: VisualPackProfile,
        diagnostics: List[VisualDiagnostic],
    ) -> None:
        """Validate the crops.

        Args:
            asset (VisualAsset): The asset value passed to validate crops.
            brief (VisualBrief): The research or content brief that defines the requested
                work.
            profile (VisualPackProfile): The resolved voice, perspective, or content
                profile.
            diagnostics (List[VisualDiagnostic]): The runtime diagnostics service used to
                record safe evidence.

        Returns:
            None: The callable updates crops state and returns no value.
        """
        crops = {item.id: item for item in profile.crop_profiles}
        for profile_id in brief.crop_profiles:
            crop = crops.get(profile_id)
            if crop is None:
                diagnostics.append(self._error("unknown-crop-profile", profile_id))
                continue
            for box in asset.content_boxes:
                if box.role in crop.protected_roles and not self._inside(box, crop.visible_area):
                    diagnostics.append(self._error("crop-risk", box.role, profile=profile_id))

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
        self.store.write_artifact(run_id, "visuals/critique.json", critique)
        return asset

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
        manifest.published_path = str(target.relative_to(self.root))
        self._save_manifest(manifest)

    def _load_brief(self, run_id: str) -> VisualBrief:
        """Load the brief.

        Args:
            run_id (str): The stable identifier for the content run.

        Returns:
            VisualBrief: The loaded visual brief for brief.

        Raises:
            VisualError: If the visual operation cannot complete.
        """
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

    @staticmethod
    def _ratio(width: int, height: int) -> str:
        """Return the ratio.

        Args:
            width (int): The width value that controls ratio.
            height (int): The height value that controls ratio.

        Returns:
            str: The resulting text for ratio.
        """
        from math import gcd

        divisor = gcd(width, height)
        return "{}:{}".format(width // divisor, height // divisor)

    @staticmethod
    def _ratio_matches(width: int, height: int, expected: str) -> bool:
        """Return whether dimensions match a declared ratio within rounding tolerance.

        Args:
            width (int): Rendered width in pixels.
            height (int): Rendered height in pixels.
            expected (str): Pack ratio in positive ``WIDTH:HEIGHT`` form.

        Returns:
            bool: Whether the rendered and declared ratios differ by at most 0.5 percent.
        """
        expected_width, expected_height = (float(part) for part in expected.split(":"))
        expected_value = expected_width / expected_height
        return abs((width / height) - expected_value) / expected_value <= 0.005

    @staticmethod
    def _normalise_copy(lines: List[str]) -> List[str]:
        """Return the normalise copy.

        Args:
            lines (List[str]): The lines collection consumed while normalise copy.

        Returns:
            List[str]: The resulting normalise copy values in their documented order.
        """
        return [re.sub(r"\s+", " ", line).strip() for line in lines]

    @staticmethod
    def _inside(inner: BoundingBox, outer: BoundingBox) -> bool:
        """Return the inside.

        Args:
            inner (BoundingBox): The inner value passed to inside.
            outer (BoundingBox): The outer value passed to inside.

        Returns:
            bool: Whether inside satisfies the documented condition.
        """
        epsilon = 1e-9
        return (
            inner.x + epsilon >= outer.x
            and inner.y + epsilon >= outer.y
            and inner.x + inner.width <= outer.x + outer.width + epsilon
            and inner.y + inner.height <= outer.y + outer.height + epsilon
        )

    @classmethod
    def _inside_safe_area(cls, box: BoundingBox, safe: SafeAreaProfile) -> bool:
        """Return the inside safe area.

        Args:
            box (BoundingBox): The box value passed to inside safe area.
            safe (SafeAreaProfile): The safe value passed to inside safe area.

        Returns:
            bool: Whether inside safe area satisfies the documented condition.
        """
        return cls._inside(
            box,
            BoundingBox(
                x=safe.left,
                y=safe.top,
                width=1 - safe.left - safe.right,
                height=1 - safe.top - safe.bottom,
            ),
        )

    @staticmethod
    def _error(code: str, message: str, profile: Optional[str] = None) -> VisualDiagnostic:
        """Return the error.

        Args:
            code (str): The code text processed when error.
            message (str): The human-readable message associated with the operation.
            profile (Optional[str]): The resolved voice, perspective, or content profile.
                Defaults to ``None``.

        Returns:
            VisualDiagnostic: The resulting visual diagnostic for error.
        """
        return VisualDiagnostic(
            code=code,
            severity=DiagnosticSeverity.ERROR,
            message=message,
            profile=profile,
        )
