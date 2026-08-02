from __future__ import annotations

import hashlib
import re
from abc import ABC, abstractmethod
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

from .domain import RunStatus, utc_now
from .storage import RunStore, StorageError


class VisualError(RuntimeError):
    pass


class ExecutionClass(str, Enum):
    DETERMINISTIC = "deterministic"
    GENERATIVE = "generative"


class RightsStatus(str, Enum):
    OWNED = "owned"
    LICENSED = "licensed"
    PUBLIC_DOMAIN = "public_domain"
    PERMISSION_GRANTED = "permission_granted"
    UNVERIFIED = "unverified"


class VisualApprovalStatus(str, Enum):
    DRAFT = "draft"
    CRITIQUED = "critiqued"
    SELECTED = "selected"
    APPROVED = "approved"
    REJECTED = "rejected"
    PUBLISHED = "published"


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class BoundingBox(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)
    role: str = "content"

    @model_validator(mode="after")
    def remains_on_canvas(self):
        if self.x + self.width > 1 or self.y + self.height > 1:
            raise ValueError("Bounding boxes must remain within the normalised canvas")
        return self


class SafeAreaProfile(BaseModel):
    id: str
    left: float = Field(default=0, ge=0, lt=0.5)
    top: float = Field(default=0, ge=0, lt=0.5)
    right: float = Field(default=0, ge=0, lt=0.5)
    bottom: float = Field(default=0, ge=0, lt=0.5)
    applies_to_roles: List[str] = Field(default_factory=lambda: ["text", "headline"])


class CropProfile(BaseModel):
    id: str
    visible_area: BoundingBox
    protected_roles: List[str] = Field(default_factory=lambda: ["headline"])


class VisualPackProfile(BaseModel):
    supported: bool = False
    required: bool = False
    execution_classes: List[ExecutionClass] = Field(default_factory=list)
    aspect_ratios: List[str] = Field(default_factory=list)
    formats: List[str] = Field(default_factory=list)
    max_file_size_bytes: Optional[int] = Field(default=None, gt=0)
    safe_areas: List[SafeAreaProfile] = Field(default_factory=list)
    crop_profiles: List[CropProfile] = Field(default_factory=list)
    require_alt_text: bool = True
    require_provenance: bool = True
    destination: Optional[str] = None

    @field_validator("aspect_ratios")
    @classmethod
    def validate_ratios(cls, values):
        for value in values:
            if not re.fullmatch(r"[1-9]\d*:[1-9]\d*", value):
                raise ValueError("Aspect ratios must use positive WIDTH:HEIGHT values")
        return values

    @model_validator(mode="after")
    def validate_support(self):
        if self.required and not self.supported:
            raise ValueError("A required visual profile must also be supported")
        if self.supported and not self.execution_classes:
            raise ValueError("A supported visual profile needs an execution class")
        if self.supported and not self.destination:
            raise ValueError("A supported visual profile needs a publication destination")
        return self


class VisualSource(BaseModel):
    source_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    uri: str
    role: str = "reference"
    creator: Optional[str] = None
    attribution: Optional[str] = None
    rights_status: RightsStatus = RightsStatus.UNVERIFIED
    licence: Optional[str] = None


class VisualBrief(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    objective: str
    content_connection: str
    exact_copy: List[str] = Field(default_factory=list)
    platform_profile: str
    aspect_ratios: List[str] = Field(min_length=1)
    output_formats: List[str] = Field(min_length=1)
    safe_area_profiles: List[str] = Field(default_factory=list)
    crop_profiles: List[str] = Field(default_factory=list)
    hierarchy: List[str] = Field(default_factory=list)
    layout_constraints: List[str] = Field(default_factory=list)
    revision_invariants: List[str] = Field(default_factory=list)
    sources: List[VisualSource] = Field(default_factory=list)
    alt_text: str
    preferred_execution_class: Optional[ExecutionClass] = None
    preferred_adapter: Optional[str] = None
    author_approval: VisualApprovalStatus = VisualApprovalStatus.DRAFT
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Invalid run id")
        return value


class VisualOutput(BaseModel):
    content: bytes
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    extracted_copy: Optional[List[str]] = None
    content_boxes: List[BoundingBox] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class VisualDiagnostic(BaseModel):
    code: str
    severity: DiagnosticSeverity
    message: str
    profile: Optional[str] = None


class VisualValidation(BaseModel):
    passed: bool
    diagnostics: List[VisualDiagnostic] = Field(default_factory=list)
    validated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualCritique(BaseModel):
    summary: str
    strengths: List[str] = Field(default_factory=list)
    issues: List[str] = Field(default_factory=list)
    reviewer: str = "visual-critic"
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualAsset(BaseModel):
    asset_id: str = Field(default_factory=lambda: uuid4().hex[:12])
    parent_asset_id: Optional[str] = None
    revision: int = Field(default=1, ge=1)
    execution_class: ExecutionClass
    adapter: str
    provider: Optional[str] = None
    model_or_renderer: str
    prompt_or_template_version: Optional[str] = None
    source_ids: List[str] = Field(default_factory=list)
    sources: List[VisualSource] = Field(default_factory=list)
    alt_text: str
    relative_path: str
    sha256: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    format: str
    size_bytes: int = Field(ge=0)
    extracted_copy: Optional[List[str]] = None
    content_boxes: List[BoundingBox] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    validation: Optional[VisualValidation] = None
    critique: Optional[VisualCritique] = None
    status: VisualApprovalStatus = VisualApprovalStatus.DRAFT
    created_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualManifest(BaseModel):
    schema_version: str = "1.0"
    run_id: str
    assets: List[VisualAsset] = Field(default_factory=list)
    selected_asset_id: Optional[str] = None
    published_path: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: utc_now().isoformat())


class VisualAdapter(ABC):
    name: str
    execution_class: ExecutionClass
    model_or_renderer: str
    prompt_or_template_version: Optional[str] = None

    @abstractmethod
    def render(self, brief: VisualBrief, parent: Optional[VisualAsset] = None) -> VisualOutput:
        """Produce one visual without assuming a particular provider."""


class VisualAdapterRegistry:
    def __init__(self):
        self._adapters: Dict[str, VisualAdapter] = {}

    def register(self, adapter: VisualAdapter) -> None:
        if not adapter.name:
            raise VisualError("Visual adapters need a stable name")
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> VisualAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise VisualError("Unknown visual adapter: {}".format(name)) from exc

    def route(self, brief: VisualBrief) -> VisualAdapter:
        if brief.preferred_adapter:
            return self.get(brief.preferred_adapter)
        candidates = list(self._adapters.values())
        if brief.preferred_execution_class:
            candidates = [
                item
                for item in candidates
                if item.execution_class == brief.preferred_execution_class
            ]
        if not candidates:
            raise VisualError("No adapter supports the requested visual execution class")
        return sorted(candidates, key=lambda item: item.name)[0]


class VisualWorkflow:
    def __init__(self, root: Path, adapter_registry: Optional[VisualAdapterRegistry] = None):
        self.root = root.resolve()
        self.store = RunStore(self.root)
        self.adapters = adapter_registry or VisualAdapterRegistry()

    def create_brief(self, brief: VisualBrief, profile: VisualPackProfile) -> VisualBrief:
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
        self._save_manifest(VisualManifest(run_id=brief.run_id))
        return brief

    def execute(
        self,
        run_id: str,
        adapter_name: Optional[str] = None,
        parent_asset_id: Optional[str] = None,
    ) -> VisualAsset:
        brief = self._load_brief(run_id)
        manifest = self._load_manifest(run_id)
        adapter = self.adapters.get(adapter_name) if adapter_name else self.adapters.route(brief)
        parent = self._asset(manifest, parent_asset_id) if parent_asset_id else None
        output = adapter.render(brief, parent)
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
        )
        manifest.assets.append(asset)
        self._save_manifest(manifest)
        return asset

    def validate(
        self,
        run_id: str,
        asset_id: str,
        profile: VisualPackProfile,
    ) -> VisualValidation:
        brief = self._load_brief(run_id)
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        diagnostics: List[VisualDiagnostic] = []

        ratio = self._ratio(asset.width, asset.height)
        if ratio not in profile.aspect_ratios:
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
        crops = {item.id: item for item in profile.crop_profiles}
        for profile_id in brief.crop_profiles:
            crop = crops.get(profile_id)
            if crop is None:
                diagnostics.append(self._error("unknown-crop-profile", profile_id))
                continue
            for box in asset.content_boxes:
                if box.role in crop.protected_roles and not self._inside(box, crop.visible_area):
                    diagnostics.append(self._error("crop-risk", box.role, profile=profile_id))

        result = VisualValidation(
            passed=not any(item.severity == DiagnosticSeverity.ERROR for item in diagnostics),
            diagnostics=diagnostics,
        )
        asset.validation = result
        self._save_manifest(manifest)
        self.store.write_artifact(run_id, "visuals/validation.json", result)
        return result

    def record_critique(self, run_id: str, asset_id: str, critique: VisualCritique) -> VisualAsset:
        manifest = self._load_manifest(run_id)
        asset = self._asset(manifest, asset_id)
        asset.critique = critique
        asset.status = VisualApprovalStatus.CRITIQUED
        self._save_manifest(manifest)
        self.store.write_artifact(run_id, "visuals/critique.json", critique)
        return asset

    def select(self, run_id: str, asset_id: str) -> VisualAsset:
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
        return asset

    def approve(self, run_id: str, asset_id: str) -> VisualAsset:
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
        return asset

    def ensure_publication_ready(
        self, run_id: str, profile: VisualPackProfile
    ) -> Optional[VisualAsset]:
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
        asset = self.ensure_publication_ready(run_id, profile)
        if asset is None:
            return None
        source = self.store.run_dir(run_id) / asset.relative_path
        if not source.exists() or hashlib.sha256(source.read_bytes()).hexdigest() != asset.sha256:
            raise VisualError("Selected visual asset is missing or its hash has changed")
        destination = (self.root / str(profile.destination)).resolve()
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise VisualError("Visual publication destination leaves the workspace") from exc
        destination.mkdir(parents=True, exist_ok=True)
        target = destination / "{}-{}.{}".format(run_id, asset.asset_id, asset.format)
        if target.exists():
            raise StorageError("Refusing to overwrite {}".format(target))
        target.write_bytes(source.read_bytes())
        manifest = self._load_manifest(run_id)
        selected = self._asset(manifest, asset.asset_id)
        selected.status = VisualApprovalStatus.PUBLISHED
        manifest.published_path = str(target.relative_to(self.root))
        self._save_manifest(manifest)
        return target

    def _load_brief(self, run_id: str) -> VisualBrief:
        try:
            return VisualBrief.model_validate_json(
                self.store.read_artifact(run_id, "visual_brief.json")
            )
        except StorageError as exc:
            raise VisualError("Run has no visual brief") from exc

    def _load_manifest(self, run_id: str) -> VisualManifest:
        path = self.store.run_dir(run_id) / "visuals" / "manifest.json"
        if not path.exists():
            raise VisualError("Run has no visual manifest")
        return VisualManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: VisualManifest) -> None:
        manifest.updated_at = utc_now().isoformat()
        self.store.write_artifact(manifest.run_id, "visuals/manifest.json", manifest)

    @staticmethod
    def _asset(manifest: VisualManifest, asset_id: Optional[str]) -> VisualAsset:
        for asset in manifest.assets:
            if asset.asset_id == asset_id:
                return asset
        raise VisualError("Unknown visual asset: {}".format(asset_id))

    @staticmethod
    def _ratio(width: int, height: int) -> str:
        from math import gcd

        divisor = gcd(width, height)
        return "{}:{}".format(width // divisor, height // divisor)

    @staticmethod
    def _normalise_copy(lines: List[str]) -> List[str]:
        return [re.sub(r"\s+", " ", line).strip() for line in lines]

    @staticmethod
    def _inside(inner: BoundingBox, outer: BoundingBox) -> bool:
        epsilon = 1e-9
        return (
            inner.x + epsilon >= outer.x
            and inner.y + epsilon >= outer.y
            and inner.x + inner.width <= outer.x + outer.width + epsilon
            and inner.y + inner.height <= outer.y + outer.height + epsilon
        )

    @classmethod
    def _inside_safe_area(cls, box: BoundingBox, safe: SafeAreaProfile) -> bool:
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
        return VisualDiagnostic(
            code=code,
            severity=DiagnosticSeverity.ERROR,
            message=message,
            profile=profile,
        )
