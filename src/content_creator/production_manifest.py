"""Create privacy-safe production manifests and review copies for content runs."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .context_composition import ContextCompositionManifest
from .domain import PublishedMediaArtifact, RunState
from .packs import PackError, PackRegistry
from .production_governance import (
    ProductionGovernance,
    ProductionPerspective,
    ProductionVoice,
    governance_hash,
    production_governance,
)
from .versioned_artifacts import hash_file


class ProductionPack(BaseModel):
    """Represent the resolved content pack used by a run."""

    id: str
    version: str
    format: str
    destination: str
    effective_options: dict[str, Any] = Field(default_factory=dict)


class ProductionResearch(BaseModel):
    """Represent the research and citation route used by a run."""

    depth: str
    source: str
    citation_style: str


class ProductionInvocation(BaseModel):
    """Represent privacy-safe provider routing for one model invocation."""

    invocation_id: str
    role: str
    phase: str
    provider: str
    model: str
    created_at: datetime


class ProductionArtifact(BaseModel):
    """Represent a run or publication artifact without copying its contents."""

    kind: str
    path: str
    content_hash: str


class ProductionPublication(BaseModel):
    """Represent repository-local publication state when available."""

    path: str
    content_hash: str
    published_at: Optional[datetime] = None
    media: list[PublishedMediaArtifact] = Field(default_factory=list)
    receipt_path: Optional[str] = None
    receipt_hash: Optional[str] = None


class ProductionManifest(BaseModel):
    """Represent the unified, privacy-safe provenance for one content run."""

    schema_version: str = "1.0"
    run_id: str
    content_session_id: str
    parent_run_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    status: str
    revision: int
    previous_revision_manifest_hash: Optional[str] = None
    core_version: Optional[str] = None
    core_version_status: Literal["captured", "unavailable"] = "unavailable"
    governance_hash: Optional[str] = None
    content_pack: ProductionPack
    voice: ProductionVoice
    perspectives: list[ProductionPerspective] = Field(default_factory=list)
    research: ProductionResearch
    audience: str
    objective: str
    format: str
    author_contribution_provenance: str
    invocations: list[ProductionInvocation] = Field(default_factory=list)
    artifacts: list[ProductionArtifact] = Field(default_factory=list)
    publication: Optional[ProductionPublication] = None


def refresh_production_manifest(
    root: Path,
    state: RunState,
    write_text: Callable[[Path, str], None],
) -> ProductionManifest:
    """Write the current JSON manifest, table, and reviewed content copy.

    Args:
        root (Path): Workspace root containing the persisted run.
        state (RunState): Current run state used as the source of truth.
        write_text (Callable[[Path, str], None]): Atomic text writer supplied by storage.

    Returns:
        ProductionManifest: The refreshed production manifest.
    """
    root = root.resolve()
    run_dir = root / "runs" / state.id
    manifest_path = run_dir / "production-manifest.json"
    previous_revision_hash = _previous_revision_hash(manifest_path, state.revision)
    manifest = build_production_manifest(
        root,
        state,
        previous_revision_manifest_hash=previous_revision_hash,
    )
    summary_path = run_dir / "production-manifest.md"
    write_text(manifest_path, manifest.model_dump_json(indent=2))
    write_text(summary_path, render_production_table(manifest))
    state.production_manifest_path = str(manifest_path.relative_to(root))
    final_path = run_dir / "final.md"
    if final_path.is_file():
        review_path = run_dir / "review.md"
        write_text(
            review_path,
            render_review_copy(manifest, final_path.read_text(encoding="utf-8")),
        )
        state.review_draft_path = str(review_path.relative_to(root))
    else:
        state.review_draft_path = None
    return manifest


def build_production_manifest(
    root: Path,
    state: RunState,
    previous_revision_manifest_hash: Optional[str] = None,
) -> ProductionManifest:
    """Build a production manifest from persisted, privacy-safe run evidence.

    Resolve current pack metadata while preserving the run's recorded effective
    options, then combine it with bounded lifecycle, routing, and artifact data.

    Args:
        root (Path): Workspace root containing the run.
        state (RunState): Current persisted lifecycle state.
        previous_revision_manifest_hash (Optional[str]): Immediate predecessor digest
            when the run revision changed. Defaults to ``None``.

    Returns:
        ProductionManifest: Unified production metadata for the run.
    """
    order = state.work_order
    run_dir = root / "runs" / state.id
    governance = production_governance(root, state)
    return ProductionManifest(
        run_id=state.id,
        content_session_id=order.content_session_id,
        parent_run_id=order.parent_run_id,
        created_at=state.created_at,
        updated_at=state.updated_at,
        status=state.status.value,
        revision=state.revision,
        previous_revision_manifest_hash=previous_revision_manifest_hash,
        core_version=governance.core_version,
        core_version_status=governance.core_version_status,
        governance_hash=governance_hash(governance),
        content_pack=_pack(root, state),
        voice=governance.voice,
        perspectives=governance.perspectives,
        research=_research(state),
        audience=order.audience,
        objective=order.objective,
        format=order.format,
        author_contribution_provenance=_author_provenance(state),
        invocations=_invocations(run_dir),
        artifacts=_artifacts(root, state),
        publication=_publication(root, state),
    )


def render_production_table(manifest: ProductionManifest) -> str:
    """Render a compact human-readable production summary.

    Args:
        manifest (ProductionManifest): Manifest to render.

    Returns:
        str: Markdown table suitable for draft and review surfaces.
    """
    perspectives = ", ".join(_perspective_summary(item) for item in manifest.perspectives) or "None"
    routes = []
    for item in manifest.invocations:
        route = f"{item.provider}/{item.model}"
        if route not in routes:
            routes.append(route)
    rows = [
        ("Content/run ID", manifest.run_id),
        ("Core", _core_summary(manifest)),
        ("Content pack", f"{manifest.content_pack.id} v{manifest.content_pack.version}"),
        ("Voice", _voice_summary(manifest.voice)),
        ("Voice governance", _voice_governance_summary(manifest.voice)),
        ("Perspectives", perspectives),
        ("Research", f"{manifest.research.depth} / {manifest.research.source}"),
        ("Audience", manifest.audience),
        ("Provider/model", ", ".join(routes) or "Not invoked"),
        ("Revision", str(manifest.revision)),
        ("Created", manifest.created_at.isoformat()),
        ("Status", manifest.status),
    ]
    lines = ["## Production details", "", "| Field | Value |", "|---|---|"]
    lines.extend(f"| {_cell(key)} | {_cell(value)} |" for key, value in rows)
    return "\n".join(lines)


def render_review_copy(manifest: ProductionManifest, draft: str) -> str:
    """Render a review-only copy with production details above clean content.

    Args:
        manifest (ProductionManifest): Manifest used for the visible summary.
        draft (str): Exact clean draft content.

    Returns:
        str: Review copy containing metadata and draft content.
    """
    return "{}\n\n---\n\n{}".format(render_production_table(manifest).rstrip(), draft.strip())


def _author_provenance(state: RunState) -> str:
    """Return a bounded author-contribution provenance label.

    Args:
        state (RunState): Run whose author contribution is classified.

    Returns:
        str: Privacy-safe provenance classification.
    """
    contribution = state.work_order.author_contribution
    if contribution is None:
        return "none"
    if contribution.supplied_by_author:
        return "direct-author-contribution"
    if contribution.reusable_perspective_entry_ids:
        return "approved-reusable-perspective"
    return "none"


def _invocations(run_dir: Path) -> list[ProductionInvocation]:
    """Load public provider routing without prompt or payload contents.

    Args:
        run_dir (Path): Directory containing optional context-composition evidence.

    Returns:
        list[ProductionInvocation]: Validated public invocation routing, or an empty
            list when historical evidence is unavailable or invalid.
    """
    path = run_dir / "context-composition.json"
    if not path.is_file():
        return []
    try:
        manifest = ContextCompositionManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [
        ProductionInvocation(
            invocation_id=item.invocation_id,
            role=item.role,
            phase=item.phase,
            provider=item.provider,
            model=item.model,
            created_at=item.created_at,
        )
        for item in manifest.invocations
    ]


def _artifacts(root: Path, state: RunState) -> list[ProductionArtifact]:
    """Return stable references and hashes for relevant run evidence.

    Args:
        root (Path): Workspace root used to create relative artifact paths.
        state (RunState): Run whose current revision selects quality evidence.

    Returns:
        list[ProductionArtifact]: Available privacy-safe artifact references.
    """
    run_dir = root / "runs" / state.id
    candidates = [
        ("final-draft", run_dir / "final.md"),
        ("resolved-context", run_dir / "resolved-context.json"),
        ("context-composition", run_dir / "context-composition.json"),
        ("quality", run_dir / f"quality-{state.revision:02d}.json"),
        ("validation", run_dir / f"validation-{state.revision:02d}.json"),
    ]
    return [
        ProductionArtifact(
            kind=kind,
            path=str(path.relative_to(root)),
            content_hash=hash_file(path),
        )
        for kind, path in candidates
        if path.is_file()
    ]


def _publication(root: Path, state: RunState) -> Optional[ProductionPublication]:
    """Return publication evidence without copying published content.

    Args:
        root (Path): Workspace root containing the publication destination.
        state (RunState): Run whose publication state is inspected.

    Returns:
        Optional[ProductionPublication]: Publication reference when the file exists.
    """
    if not state.published_path:
        return None
    path = root / state.published_path
    if not path.is_file():
        return None
    published_events = [event.at for event in state.events if event.name == "published"]
    receipt_events = [
        event.detail for event in state.events if event.name == "publication_receipt_written"
    ]
    receipt_path = receipt_events[-1] if receipt_events else None
    receipt = root / receipt_path if receipt_path else None
    return ProductionPublication(
        path=state.published_path,
        content_hash=hash_file(path),
        published_at=published_events[-1] if published_events else None,
        media=list(state.published_media),
        receipt_path=receipt_path,
        receipt_hash=hash_file(receipt) if receipt and receipt.is_file() else None,
    )


def _cell(value: str) -> str:
    """Return one escaped value for a compact Markdown table cell.

    Args:
        value (str): Unescaped table value.

    Returns:
        str: Single-line Markdown-safe cell value.
    """
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _pack(root: Path, state: RunState) -> ProductionPack:
    """Return resolved pack identity while tolerating legacy option conflicts.

    Args:
        root (Path): Workspace root containing pack resources.
        state (RunState): Run whose pack and recorded options are inspected.

    Returns:
        ProductionPack: Pack identity plus the run's effective recorded options.
    """
    order = state.work_order
    registry = PackRegistry(root)
    try:
        pack = registry.resolve(order.content_pack, order.pack_options)
    except PackError:
        pack = registry.get(order.content_pack)
    return ProductionPack(
        id=pack.id,
        version=pack.version,
        format=pack.format,
        destination=pack.destination,
        effective_options=dict(order.pack_options),
    )


def manifest_governance_hash(manifest: ProductionManifest) -> str:
    """Return the recomputed governance digest represented by a manifest.

    Args:
        manifest (ProductionManifest): Persisted production manifest.

    Returns:
        str: Canonical SHA-256 digest independent of mutable run lifecycle fields.
    """
    return governance_hash(
        ProductionGovernance(
            core_version=manifest.core_version,
            core_version_status=manifest.core_version_status,
            voice=manifest.voice,
            perspectives=manifest.perspectives,
        )
    )


def _previous_revision_hash(path: Path, revision: int) -> Optional[str]:
    """Return or preserve the immediate prior revision manifest digest.

    Args:
        path (Path): Current production-manifest path.
        revision (int): Revision about to be written.

    Returns:
        Optional[str]: Immediate predecessor hash, preserved lineage hash, or ``None``.
    """
    if not path.is_file():
        return None
    try:
        prior = json.loads(path.read_text(encoding="utf-8"))
        prior_revision = int(prior.get("revision", 0))
    except (OSError, TypeError, ValueError):
        return None
    if prior_revision < revision:
        return hash_file(path)
    value = prior.get("previous_revision_manifest_hash")
    text = str(value).strip() if value is not None else ""
    return text or None


def _digest_summary(value: Optional[str]) -> str:
    """Return a concise human digest while JSON retains the complete value.

    Args:
        value (Optional[str]): Full optional digest to abbreviate.

    Returns:
        str: Readable digest or explicit unavailable label.
    """
    if not value:
        return "digest unavailable"
    return value if len(value) <= 24 else value[:20] + "…"


def _core_summary(manifest: ProductionManifest) -> str:
    """Render the captured Core version or an explicit unavailable label.

    Args:
        manifest (ProductionManifest): Manifest containing generation-time Core identity.

    Returns:
        str: Human-readable Core version provenance.
    """
    return f"v{manifest.core_version}" if manifest.core_version else "Unavailable (legacy run)"


def _voice_summary(voice: ProductionVoice) -> str:
    """Render concise immutable voice identity and artifact provenance.

    Args:
        voice (ProductionVoice): Governed voice snapshot to summarize.

    Returns:
        str: Human-readable voice identity and digest.
    """
    version = f"v{voice.version}" if voice.version else "version unavailable"
    return f"{voice.id} {version}; {voice.source_kind}; {_digest_summary(voice.artifact_digest)}"


def _voice_governance_summary(voice: ProductionVoice) -> str:
    """Render concise lifecycle, epoch, and evidence-baseline provenance.

    Args:
        voice (ProductionVoice): Governed voice snapshot to summarize.

    Returns:
        str: Human-readable lifecycle and epoch state.
    """
    lifecycle = voice.lifecycle_status_at_generation or "status unavailable"
    if voice.learning_epoch:
        epoch = "epoch {} {} {}".format(
            voice.learning_epoch.id,
            voice.learning_epoch.status,
            _digest_summary(voice.learning_epoch.digest),
        )
    else:
        epoch = "epoch unavailable"
    baseline = _digest_summary(voice.evidence_baseline_digest)
    return f"{lifecycle}; {epoch}; evidence {baseline}"


def _perspective_summary(item: ProductionPerspective) -> str:
    """Render one concise pinned perspective identity and digest.

    Args:
        item (ProductionPerspective): Pinned perspective snapshot to summarize.

    Returns:
        str: Human-readable perspective identity and digest.
    """
    version = f"v{item.version}" if item.version else "version unavailable"
    return f"{item.context_id} {version} {_digest_summary(item.manifest_digest)}"


def _research(state: RunState) -> ProductionResearch:
    """Return the research and citation route recorded by the work order.

    Args:
        state (RunState): Run containing the effective research route.

    Returns:
        ProductionResearch: Research depth, source, and citation presentation.
    """
    order = state.work_order
    return ProductionResearch(
        depth=order.research_depth.value,
        source=order.research_source.value,
        citation_style=str(order.pack_options.get("citation_style", "inline-links")),
    )
