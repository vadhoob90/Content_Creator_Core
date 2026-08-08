"""Record and explain privacy-safe runtime context composition provenance."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .domain import utc_now
from .storage import RunStore, StorageError

LayerStatus = Literal["loaded", "skipped"]
LayerOwner = Literal["core", "workspace", "voice", "perspective", "pack", "runtime"]


class ContextLayer(BaseModel):
    """Describe one loaded or deliberately skipped instruction source."""

    order: int
    category: str
    label: str
    owner: LayerOwner
    source: str
    status: LayerStatus
    reason: Optional[str] = None
    version: Optional[str] = None
    content_hash: Optional[str] = None
    record_ids: list[str] = Field(default_factory=list)


class ContextPayloadReference(BaseModel):
    """Record private task input without copying its contents."""

    kind: str
    source: str
    content_hash: Optional[str] = None
    keys: list[str] = Field(default_factory=list)


class ContextInvocation(BaseModel):
    """Capture the exact composition used by one provider invocation."""

    invocation_id: str = "pending"
    sequence: int = 0
    role: str
    role_key: str
    phase: str
    provider: str
    model: str
    created_at: datetime = Field(default_factory=utc_now)
    instruction_layers: list[ContextLayer] = Field(default_factory=list)
    task_payloads: list[ContextPayloadReference] = Field(default_factory=list)


class ContextInvocationIdentity(BaseModel):
    """Collect public routing metadata for one model invocation."""

    role: str
    role_key: str
    phase: str
    provider: str
    model: str


class ContextCompositionManifest(BaseModel):
    """Collect ordered context provenance for one persisted content run."""

    schema_version: str = "1.0"
    run_id: str
    invocations: list[ContextInvocation] = Field(default_factory=list)


class ContextCompositionStore:
    """Persist context provenance beside the run without prompt duplication."""

    artifact_name = "context-composition.json"

    def __init__(self, root: Path):
        """Initialize the store for one workspace.

        Args:
            root (Path): Workspace root directory.

        Returns:
            None: The resolved root is stored in place.
        """
        self.root = root.resolve()

    def append(self, run_id: str, invocation: ContextInvocation) -> ContextInvocation:
        """Append one invocation with a stable run-local sequence.

        Args:
            run_id (str): Stable content run identifier.
            invocation (ContextInvocation): Unsequenced invocation provenance.

        Returns:
            ContextInvocation: Persisted invocation with its final identifier.
        """
        path = self.path(run_id)
        manifest = (
            self.read(run_id) if path.is_file() else ContextCompositionManifest(run_id=run_id)
        )
        sequence = len(manifest.invocations) + 1
        persisted = invocation.model_copy(
            update={
                "sequence": sequence,
                "invocation_id": f"{sequence:04d}-{invocation.role}",
            }
        )
        manifest.invocations.append(persisted)
        RunStore._atomic_text(path, manifest.model_dump_json(indent=2))
        return persisted

    def read(self, run_id: str) -> ContextCompositionManifest:
        """Read composition provenance for a historical run.

        Args:
            run_id (str): Stable content run identifier.

        Returns:
            ContextCompositionManifest: Validated historical composition evidence.

        Raises:
            StorageError: If the run identifier or composition artifact is unavailable.
        """
        path = self.path(run_id)
        if not path.is_file():
            raise StorageError(
                f"Run {run_id} has no context-composition artifact; it may predate v1.6.0"
            )
        return ContextCompositionManifest.model_validate_json(path.read_text(encoding="utf-8"))

    def path(self, run_id: str) -> Path:
        """Return the validated composition artifact path.

        Args:
            run_id (str): Stable content run identifier.

        Returns:
            Path: Run-local composition artifact path.

        Raises:
            StorageError: If the run identifier is not filesystem-safe.
        """
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", run_id):
            raise StorageError("Invalid run id")
        return self.root / "runs" / run_id / self.artifact_name


def invocation_record(
    identity: ContextInvocationIdentity,
    layers: list[ContextLayer],
    instruction: str,
    payload: dict[str, Any],
    payload_sources: list[str],
) -> ContextInvocation:
    """Build privacy-safe provenance for one exact model request.

    Args:
        identity (ContextInvocationIdentity): Public role and model routing metadata.
        layers (list[ContextLayer]): Ordered instruction composition.
        instruction (str): Private runtime task instruction.
        payload (dict[str, Any]): Private structured task payload.
        payload_sources (list[str]): Run-local or runtime source locators.

    Returns:
        ContextInvocation: Unsequenced invocation ready for persistence or display.
    """
    references = [
        ContextPayloadReference(
            kind="task-instruction",
            source="runtime:instruction",
            content_hash=hash_private(instruction),
        ),
        ContextPayloadReference(
            kind="task-payload",
            source="runtime:payload",
            content_hash=hash_private(payload),
            keys=sorted(str(key) for key in payload),
        ),
    ]
    references.extend(
        ContextPayloadReference(
            kind="run-artifact-reference",
            source=source,
        )
        for source in payload_sources
    )
    return ContextInvocation(
        role=identity.role,
        role_key=identity.role_key,
        phase=identity.phase,
        provider=identity.provider,
        model=identity.model,
        instruction_layers=layers,
        task_payloads=references,
    )


def hash_private(value: Any) -> str:
    """Hash private runtime input without retaining its contents.

    Args:
        value (Any): Private instruction or structured payload.

    Returns:
        str: Stable SHA-256 identifier for the serialized value.
    """
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def render_context_manifest(manifest: ContextCompositionManifest) -> str:
    """Render historical context provenance for an author.

    Args:
        manifest (ContextCompositionManifest): Persisted composition evidence.

    Returns:
        str: Human-readable invocation and layer trace.
    """
    lines = [f"Runtime context composition for run {manifest.run_id}"]
    for invocation in manifest.invocations:
        lines.extend(["", *_render_invocation(invocation)])
    return "\n".join(lines)


def render_live_context(invocation: ContextInvocation) -> str:
    """Render concise stderr lines before one provider invocation.

    Args:
        invocation (ContextInvocation): Runtime composition evidence.

    Returns:
        str: Concise load and skip trace without private prompt content.
    """
    return "\n".join(f"[context] {line}" for line in _render_invocation(invocation))


def render_preflight(role: str, layers: list[ContextLayer]) -> str:
    """Render a read-only expected composition for one role.

    Args:
        role (str): Repository-owned agent role.
        layers (list[ContextLayer]): Expected ordered instruction layers.

    Returns:
        str: Human-readable preflight trace.
    """
    lines = [f"Expected runtime context for {role}"]
    lines.extend(_render_layer(layer) for layer in layers)
    return "\n".join(lines)


def _render_invocation(invocation: ContextInvocation) -> list[str]:
    """Return readable lines for one invocation.

    Args:
        invocation (ContextInvocation): Runtime composition evidence.

    Returns:
        list[str]: Invocation heading, layers, and private payload references.
    """
    heading = (
        f"Invocation {invocation.invocation_id}: {invocation.role} "
        f"({invocation.phase}) via {invocation.provider}/{invocation.model}"
    )
    lines = [heading]
    lines.extend(_render_layer(layer) for layer in invocation.instruction_layers)
    for payload in invocation.task_payloads:
        keys = f"; keys={','.join(payload.keys)}" if payload.keys else ""
        digest = f"; {payload.content_hash}" if payload.content_hash else ""
        lines.append(f"  payload {payload.kind}: {payload.source}{digest}{keys}")
    return lines


def _render_layer(layer: ContextLayer) -> str:
    """Return one concise loaded or skipped layer line.

    Args:
        layer (ContextLayer): Instruction-layer provenance.

    Returns:
        str: Human-readable source, version, hash, and decision.
    """
    action = "load" if layer.status == "loaded" else "skip"
    suffix = f"; reason={layer.reason}" if layer.reason else ""
    if layer.version:
        suffix += f"; version={layer.version}"
    if layer.content_hash:
        suffix += f"; hash={layer.content_hash}"
    if layer.record_ids:
        suffix += f"; records={','.join(layer.record_ids)}"
    return f"  {layer.order}. {action} {layer.label} from {layer.source}{suffix}"
