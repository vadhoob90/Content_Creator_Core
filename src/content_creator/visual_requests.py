"""Route reviewed content requests into the governed visual workflow."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from .domain import utc_now
from .storage import RunStore, StorageError
from .version import VERSION
from .visual_components import VisualComponent, VisualComponentRegistry
from .visual_contracts import (
    ExecutionClass,
    VisualAsset,
    VisualBrief,
    VisualComponentRef,
    VisualError,
    VisualManifest,
    VisualPackProfile,
    VisualRoleProfile,
)
from .visuals import VisualWorkflow


class VisualInvocation(BaseModel):
    """Record an explicit host decision to enter the visual workflow."""

    schema_version: str = "1.0"
    run_id: str
    request: str
    decision: str = "visual-workflow"
    pack_id: str
    pack_version: str
    core_version: str = VERSION
    role: str
    components: List[VisualComponentRef] = Field(default_factory=list)
    routed_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualRenderResult(BaseModel):
    """Return the routed request, brief, and rendered review variants."""

    invocation: VisualInvocation
    brief: VisualBrief
    assets: List[VisualAsset]


class VisualRenderRequest(BaseModel):
    """Collect one natural-language render operation and its optional controls."""

    run_id: str
    pack_id: str
    pack_version: str
    request: str
    role: Optional[str] = None
    variants: int = 1
    adapter_name: Optional[str] = None
    parent_asset_id: Optional[str] = None
    objective: Optional[str] = None
    alt_text: Optional[str] = None


class VisualRequestWorkflow:
    """Resolve components and render natural-language visual requests."""

    def __init__(
        self,
        root: Path,
        components: Optional[VisualComponentRegistry] = None,
        workflow: Optional[VisualWorkflow] = None,
    ):
        """Initialize a request workflow from installed Core capabilities.

        Args:
            root (Path): Author workspace root.
            components (Optional[VisualComponentRegistry]): Component registry override.
                Defaults to ``None``.
            workflow (Optional[VisualWorkflow]): Visual lifecycle override. Defaults to
                ``None``.

        Returns:
            None: The workflow is initialized in place.
        """
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.components_registry = components or VisualComponentRegistry.from_core()
        self.workflow = workflow or VisualWorkflow(self.root)

    def components(
        self, profile: VisualPackProfile, role: Optional[str] = None
    ) -> List[VisualComponent]:
        """Return compatible installed components for one pack role.

        Args:
            profile (VisualPackProfile): Resolved pack visual profile.
            role (Optional[str]): Requested visual role. Defaults to ``None``.

        Returns:
            List[VisualComponent]: Compatible components in stable order.

        """
        self._require_support(profile)
        role_id = role or profile.default_role or "default"
        role_profile = profile.role(role)
        return self._resolve_components(profile, role_id, role_profile)

    def render(
        self,
        profile: VisualPackProfile,
        request: VisualRenderRequest,
    ) -> VisualRenderResult:
        """Render validated review variants through installed Core components.

        The request is persisted before renderer execution so the host routing decision,
        pinned versions, selected role, and component provenance remain inspectable even
        when rendering later fails.

        Args:
            profile (VisualPackProfile): Resolved pack visual profile.
            request (VisualRenderRequest): Routed request and optional render controls.

        Returns:
            VisualRenderResult: Persisted routing decision, brief, and validated variants.

        Raises:
            VisualError: If support, role, components, run evidence, or variants are invalid.
        """
        self._require_support(profile)
        if request.variants < 1 or request.variants > 6:
            raise VisualError("Visual rendering requires between 1 and 6 variants")
        role_id = request.role or profile.default_role or "default"
        role_profile = profile.role(request.role)
        components = self._resolve_components(profile, role_id, role_profile)
        references = [component.reference() for component in components]
        brief = self._brief(
            request.run_id,
            request.pack_id,
            role_id,
            role_profile,
            references,
            request.objective,
            request.alt_text,
        )
        invocation = VisualInvocation(
            run_id=request.run_id,
            request=request.request,
            pack_id=request.pack_id,
            pack_version=request.pack_version,
            role=role_id,
            components=references,
        )
        self.store.write_artifact(request.run_id, "visuals/invocation.json", invocation)
        assets = []
        for index in range(request.variants):
            asset = self.workflow.execute(
                request.run_id,
                adapter_name=request.adapter_name,
                parent_asset_id=request.parent_asset_id,
                variant_name="concept-{}".format(index + 1),
            )
            self.workflow.validate(request.run_id, asset.asset_id, profile)
            assets.append(self.workflow.asset(request.run_id, asset.asset_id))
        return VisualRenderResult(invocation=invocation, brief=brief, assets=assets)

    @staticmethod
    def _require_support(profile: VisualPackProfile) -> None:
        """Reject packs that do not opt into visual output.

        Args:
            profile (VisualPackProfile): Resolved pack visual profile.

        Returns:
            None: Supported profiles continue without a value.

        Raises:
            VisualError: If the selected pack does not support visuals.
        """
        if not profile.supported:
            raise VisualError("The selected content pack does not support visual assets")

    def _resolve_components(
        self,
        profile: VisualPackProfile,
        role_id: str,
        role_profile: VisualRoleProfile,
    ) -> List[VisualComponent]:
        """Resolve the first complete supported execution and format combination.

        Args:
            profile (VisualPackProfile): Resolved pack visual profile.
            role_id (str): Selected pack-owned visual role.
            role_profile (VisualRoleProfile): Role output requirements.

        Returns:
            List[VisualComponent]: Complete compatible component set.

        Raises:
            VisualError: If no declared combination has all required components.
        """
        failures = []
        execution_classes = sorted(
            profile.execution_classes,
            key=lambda item: item != ExecutionClass.DETERMINISTIC,
        )
        formats = sorted(role_profile.formats, key=lambda item: item.lower() != "svg")
        for execution_class in execution_classes:
            for output_format in formats:
                try:
                    return self.components_registry.resolve(
                        role=role_id,
                        execution_class=execution_class,
                        output_format=output_format.lower().lstrip("."),
                        aspect_ratio=role_profile.aspect_ratio,
                    )
                except VisualError as exc:
                    failures.append(str(exc))
        detail = failures[-1] if failures else "the pack declares no execution class or format"
        raise VisualError("Required Core visual components could not be resolved: " + detail)

    def _brief(
        self,
        run_id: str,
        pack_id: str,
        role_id: str,
        role_profile: VisualRoleProfile,
        components: List[VisualComponentRef],
        objective: Optional[str],
        alt_text: Optional[str],
    ) -> VisualBrief:
        """Load or create the durable brief without resetting existing lineage.

        Existing briefs retain their content and asset history while component
        references are refreshed. New briefs derive exact copy only from the reviewed
        final artifact and layer workspace-owned tokens over pack-owned output policy.

        Args:
            run_id (str): Reviewed content run identifier.
            pack_id (str): Resolved content pack identifier.
            role_id (str): Selected pack-owned visual role.
            role_profile (VisualRoleProfile): Role output requirements.
            components (List[VisualComponentRef]): Resolved immutable component references.
            objective (Optional[str]): Optional visual objective.
            alt_text (Optional[str]): Optional accessibility text.

        Returns:
            VisualBrief: Existing compatible brief or newly persisted brief.

        Raises:
            VisualError: If an existing brief targets a different role.
        """
        path = self.store.run_dir(run_id) / "visual_brief.json"
        if path.exists():
            brief = VisualBrief.model_validate_json(path.read_text(encoding="utf-8"))
            if brief.role and brief.role != role_id:
                raise VisualError(
                    "The existing visual brief targets role '{}' rather than '{}'".format(
                        brief.role, role_id
                    )
                )
            return self._refresh_components(brief, components)
        headline = self._reviewed_headline(run_id)
        brief = VisualBrief(
            run_id=run_id,
            objective=objective or "Create a clear editorial visual for the reviewed content",
            content_connection="Represents the reviewed final content without adding claims",
            exact_copy=[headline],
            platform_profile="{}:{}".format(pack_id, role_id),
            role=role_id,
            aspect_ratios=[role_profile.aspect_ratio],
            output_formats=[self._component_format(components)],
            output_width=role_profile.recommended_width,
            output_height=role_profile.recommended_height,
            safe_area_profiles=role_profile.safe_area_profiles,
            crop_profiles=role_profile.crop_profiles,
            hierarchy=["headline", "accent"],
            revision_invariants=["Preserve reviewed headline copy", "Preserve alt text"],
            alt_text=alt_text or "Editorial visual for: {}".format(headline),
            brand_tokens=self._brand_tokens(),
            components=components,
            preferred_execution_class=ExecutionClass.DETERMINISTIC,
            preferred_adapter="core-deterministic-svg",
        )
        self.workflow.create_brief(brief, self._profile_for_role(role_profile))
        return brief

    def _refresh_components(
        self, brief: VisualBrief, components: List[VisualComponentRef]
    ) -> VisualBrief:
        """Return an existing brief with current component references backfilled.

        Args:
            brief (VisualBrief): Existing persisted brief.
            components (List[VisualComponentRef]): Current resolved component references.

        Returns:
            VisualBrief: Updated in-memory and persisted brief.
        """
        brief.components = components
        self.store.write_artifact(brief.run_id, "visual_brief.json", brief)
        manifest_path = self.store.run_dir(brief.run_id) / "visuals/manifest.json"
        manifest = VisualManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        manifest.components = components
        self.store.write_artifact(brief.run_id, "visuals/manifest.json", manifest)
        return brief

    @staticmethod
    def _profile_for_role(role: VisualRoleProfile) -> VisualPackProfile:
        """Build the bounded profile used while creating a role-specific brief.

        Args:
            role (VisualRoleProfile): Selected pack role.

        Returns:
            VisualPackProfile: Minimal supported profile for brief validation.
        """
        return VisualPackProfile(
            supported=True,
            execution_classes=[ExecutionClass.DETERMINISTIC],
            aspect_ratios=[role.aspect_ratio],
            formats=role.formats,
            destination="visuals",
        )

    def _reviewed_headline(self, run_id: str) -> str:
        """Extract bounded exact copy from reviewed final content.

        Args:
            run_id (str): Reviewed content run identifier.

        Returns:
            str: First meaningful reviewed line without Markdown decoration.

        Raises:
            VisualError: If reviewed final content is missing or empty.
        """
        try:
            content = self.store.read_artifact(run_id, "final.md")
        except StorageError as exc:
            raise VisualError("The selected run has no reviewed final content") from exc
        for line in content.splitlines():
            cleaned = re.sub(r"^[#>*_`\-\s]+", "", line).strip()
            if cleaned:
                return cleaned[:96].rstrip()
        raise VisualError("The selected run has no reviewed final content")

    def _brand_tokens(self) -> dict[str, str]:
        """Load optional workspace-owned visual tokens without copying them into Core.

        Returns:
            dict[str, str]: Valid string tokens or an empty mapping.

        Raises:
            VisualError: If ``visual-brand.json`` is not a string mapping.
        """
        path = self.root / "visual-brand.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise VisualError("Workspace visual-brand.json is not valid JSON") from exc
        if not isinstance(payload, dict) or not all(
            isinstance(key, str) and isinstance(value, str) for key, value in payload.items()
        ):
            raise VisualError("Workspace visual-brand.json must contain string tokens")
        return payload

    @staticmethod
    def _component_format(components: List[VisualComponentRef]) -> str:
        """Return the output format implemented by the Core renderer component.

        Args:
            components (List[VisualComponentRef]): Resolved component references.

        Returns:
            str: Renderer output format.
        """
        return "svg"
