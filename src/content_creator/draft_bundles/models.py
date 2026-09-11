"""Define versioned bundle membership and draft export evidence."""

from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator


def portable_identifier(value: str) -> str:
    """Reject reserved filenames in otherwise filesystem-safe identifiers.

    Args:
        value (str): Lowercase slug validated by the identifier pattern.

    Returns:
        str: Portable identifier suitable for a Markdown filename.

    Raises:
        ValueError: If the identifier is a reserved Windows device name.
    """
    reserved = {
        "con",
        "prn",
        "aux",
        "nul",
        *[f"com{i}" for i in range(10)],
        *[f"lpt{i}" for i in range(10)],
    }
    if value in reserved:
        raise ValueError("Bundle identifiers must not use reserved device names")
    return value


Identifier = Annotated[
    str,
    Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=64),
    AfterValidator(portable_identifier),
]
Digest = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]


class BundleVisual(BaseModel):
    """Record an exact governed visual selection and its review state."""

    slot_id: str | None = None
    anchor: str | None = None
    order: int = 0
    slot_sha256: Digest | None = None
    asset_id: str
    revision: int = Field(ge=1)
    parent_asset_id: str | None = None
    role: str
    source_path: str
    sha256: Digest
    format: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    alt_text: str
    approval_state: str
    validation_passed: bool | None = None
    record_sha256: Digest
    provenance_path: str


class BundleMember(BaseModel):
    """Record one named artifact without changing its originating run lineage."""

    name: Identifier
    run_id: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    revision: int = Field(ge=1)
    artifact_path: str
    sha256: Digest
    content_session_id: str
    parent_run_id: str | None = None
    content_pack: str
    content_pack_version: str | None = None
    voice_id: str
    voice_version: str | None = None
    run_status: str
    claim_review_required: bool = False
    validation_status: Literal["passed", "failed", "unavailable"] = "unavailable"
    publication_destinations: list[str] = Field(default_factory=list)
    evidence_hashes: dict[str, Digest] = Field(default_factory=dict)
    visuals: list[BundleVisual] = Field(default_factory=list)


class DraftBundle(BaseModel):
    """Represent ordered pinned members of a draft review bundle."""

    schema_version: Literal["1.0"] = "1.0"
    bundle_id: Identifier
    title: str = Field(min_length=1)
    revision: int = Field(default=1, ge=1)
    members: list[BundleMember] = Field(default_factory=list)

    @model_validator(mode="after")
    def unique_members(self) -> "DraftBundle":
        """Validate unique member names and source artifacts.

        Returns:
            DraftBundle: Validated bundle.

        Raises:
            ValueError: If names or source artifacts occur more than once.
        """
        names = [m.name for m in self.members]
        sources = [m.artifact_path for m in self.members]
        if len(names) != len(set(names)) or len(sources) != len(set(sources)):
            raise ValueError("Bundle members must have unique names and source artifacts")
        return self


class MemberReview(BaseModel):
    """Describe whether a pinned member still matches the current governed run."""

    member: BundleMember
    stale: bool = False
    findings: list[str] = Field(default_factory=list)


class BundleReview(BaseModel):
    """Provide per-member review states without transferring approvals."""

    schema_version: Literal["1.0"] = "1.0"
    bundle_id: str
    revision: int
    stale: bool
    members: list[MemberReview]


class ExportArtifact(BaseModel):
    """Map exported bytes to their pinned run artifact and current review state."""

    member_name: str
    run_id: str
    run_revision: int
    kind: Literal["markdown", "visual"]
    source_path: str
    source_sha256: Digest
    exported_path: str
    exported_sha256: Digest
    visual: BundleVisual | None = None


class DraftExportManifest(BaseModel):
    """Bind a portable draft package to a pinned bundle or a single run."""

    schema_version: Literal["1.0"] = "1.0"
    purpose: Literal["draft-review"] = "draft-review"
    bundle_id: str | None = None
    bundle_revision: int | None = None
    source_sha256: Digest
    members: list[BundleMember]
    artifacts: list[ExportArtifact]
