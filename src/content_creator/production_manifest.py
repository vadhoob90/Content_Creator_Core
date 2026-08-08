"""Create privacy-safe production manifests and review copies for content runs."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from .context_composition import ContextCompositionManifest
from .domain import RunState
from .packs import PackError, PackRegistry
from .versioned_artifacts import hash_file


class ProductionPack(BaseModel):
    """Represent the resolved content pack used by a run."""

    id: str
    version: str
    format: str
    destination: str
    effective_options: dict[str, Any] = Field(default_factory=dict)


class ProductionVoice(BaseModel):
    """Represent the immutable voice selection used by a run."""

    id: str
    version: str


class ProductionPerspective(BaseModel):
    """Represent one pinned perspective selection used by a run."""

    context_id: str
    version: str
    reason: str
    confidence: float


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
    manifest = build_production_manifest(root, state)
    manifest_path = run_dir / "production-manifest.json"
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


def build_production_manifest(root: Path, state: RunState) -> ProductionManifest:
    """Build a production manifest from persisted, privacy-safe run evidence.

    Resolve current pack metadata while preserving the run's recorded effective
    options, then combine it with bounded lifecycle, routing, and artifact data.

    Args:
        root (Path): Workspace root containing the run.
        state (RunState): Current persisted lifecycle state.

    Returns:
        ProductionManifest: Unified production metadata for the run.
    """
    order = state.work_order
    run_dir = root / "runs" / state.id
    return ProductionManifest(
        run_id=state.id,
        content_session_id=order.content_session_id,
        parent_run_id=order.parent_run_id,
        created_at=state.created_at,
        updated_at=state.updated_at,
        status=state.status.value,
        revision=state.revision,
        content_pack=_pack(root, state),
        voice=ProductionVoice(
            id=order.voice_id,
            version=str(order.voice_version or "unresolved"),
        ),
        perspectives=_perspectives(state),
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
    perspectives = (
        ", ".join(f"{item.context_id} v{item.version}" for item in manifest.perspectives) or "None"
    )
    routes = []
    for item in manifest.invocations:
        route = f"{item.provider}/{item.model}"
        if route not in routes:
            routes.append(route)
    rows = [
        ("Content/run ID", manifest.run_id),
        ("Content pack", f"{manifest.content_pack.id} v{manifest.content_pack.version}"),
        ("Voice", f"{manifest.voice.id} v{manifest.voice.version}"),
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
    return ProductionPublication(
        path=state.published_path,
        content_hash=hash_file(path),
        published_at=published_events[-1] if published_events else None,
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


def _perspectives(state: RunState) -> list[ProductionPerspective]:
    """Return all pinned perspective selections in work-order order.

    Args:
        state (RunState): Run containing resolved perspective selections.

    Returns:
        list[ProductionPerspective]: Bounded perspective identities and reasons.
    """
    return [
        ProductionPerspective(
            context_id=item.context_id,
            version=str(item.version or "unresolved"),
            reason=item.reason,
            confidence=item.confidence,
        )
        for item in state.work_order.perspective_selections
    ]


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
