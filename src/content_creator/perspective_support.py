"""Provide perspective support capabilities."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol
from uuid import uuid4

from pydantic import BaseModel, Field

from .domain import PerspectiveMode, PerspectiveSelection, WorkOrder
from .runner_models import AgentRunOptions
from .storage import slugify


class PerspectiveRunner(Protocol):
    """Narrow application seam needed for automatic perspective resolution."""

    def run(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: AgentRunOptions | None = None,
    ) -> Any:
        """Run perspective runner."""
        raise NotImplementedError


class PerspectiveError(RuntimeError):
    """Report perspective failures."""

    pass


class PerspectiveStatus(str, Enum):
    """Enumerate supported perspective status values."""

    CANDIDATE = "candidate"
    AWAITING_APPROVAL = "awaiting_approval"
    ACTIVE = "active"
    INACTIVE = "inactive"


class PerspectiveEntryStatus(str, Enum):
    """Enumerate supported perspective entry status values."""

    APPROVED = "approved"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class PerspectiveChangeType(str, Enum):
    """Enumerate supported perspective change type values."""

    NEW = "new"
    QUALIFY = "qualify"
    REPLACE = "replace"
    SUPERSEDE = "supersede"


class PerspectiveProvenance(BaseModel):
    """Represent a perspective provenance."""

    kind: str
    reference: str
    excerpt: Optional[str] = None


class PerspectiveEntry(BaseModel):
    """Represent a perspective entry."""

    id: str = Field(default_factory=lambda: "perspective-" + uuid4().hex[:12])
    type: str = "position"
    statement: str
    topics: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    counterpositions: List[str] = Field(default_factory=list)
    provenance: List[PerspectiveProvenance] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0, le=1)
    status: PerspectiveEntryStatus = PerspectiveEntryStatus.APPROVED
    supersedes: Optional[str] = None


class PerspectiveManifest(BaseModel):
    """Represent a perspective manifest."""

    schema_version: str = "1.0"
    owner_voice_id: str
    context_id: str
    display_name: str
    version: str = "candidate"
    status: PerspectiveStatus
    candidate_hash: str
    components: Dict[str, str]
    component_hashes: Dict[str, str]


class PerspectiveApprovalReceipt(BaseModel):
    """Represent a perspective approval receipt."""

    owner_voice_id: str
    context_id: str
    activated_version: str
    approved_by: str
    approved_at: str
    candidate_hash: str


class PerspectiveProposalCandidate(BaseModel):
    """Represent a perspective proposal candidate."""

    change_type: PerspectiveChangeType = PerspectiveChangeType.NEW
    type: str = "position"
    statement: str
    topics: List[str] = Field(default_factory=list)
    qualifications: List[str] = Field(default_factory=list)
    counterpositions: List[str] = Field(default_factory=list)
    evidence: str
    confidence: float = Field(default=0.7, ge=0, le=1)
    target_entry_id: Optional[str] = None


class PerspectiveExtraction(BaseModel):
    """Represent a perspective extraction."""

    candidates: List[PerspectiveProposalCandidate] = Field(default_factory=list)
    author_signal: str = "publication_approval"


class PerspectiveCatalogueEntry(BaseModel):
    """Represent a perspective catalogue entry."""

    context_id: str
    display_name: str
    summary: str
    use_when: List[str] = Field(default_factory=list)
    avoid_when: List[str] = Field(default_factory=list)
    related_contexts: List[str] = Field(default_factory=list)


class PerspectiveCatalogue(BaseModel):
    """Represent a perspective catalogue."""

    schema_version: str = "1.0"
    routing_only: bool = True
    contexts: List[PerspectiveCatalogueEntry] = Field(default_factory=list)


class PerspectiveResolution(BaseModel):
    """Represent a perspective resolution."""

    mode: PerspectiveMode = PerspectiveMode.AUTOMATIC
    selected: List[PerspectiveSelection] = Field(default_factory=list)
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    disabled_reason: Optional[str] = None


class PerspectiveCatalogueStore:
    """Manage perspective catalogue records."""

    def __init__(self, root: Path, voice_id: str):
        """Initialize the perspective catalogue store."""
        self.root = root.resolve()
        self.voice_id = slugify(voice_id)
        if self.voice_id != voice_id:
            raise PerspectiveError("Voice ids must use lowercase letters, digits, and hyphens")
        self.path = self.root / "profiles" / self.voice_id / "perspectives" / "catalogue.json"

    def load(self) -> PerspectiveCatalogue:
        """Load perspective catalogue store."""
        if not self.path.exists():
            return PerspectiveCatalogue()
        catalogue = PerspectiveCatalogue.model_validate_json(self.path.read_text(encoding="utf-8"))
        context_ids = [item.context_id for item in catalogue.contexts]
        if len(context_ids) != len(set(context_ids)):
            raise PerspectiveError("Perspective catalogue context ids must be unique")
        invalid = sorted(
            context_id for context_id in context_ids if slugify(context_id) != context_id
        )
        if invalid:
            raise PerspectiveError(
                "Perspective catalogue contains invalid context ids: {}".format(", ".join(invalid))
            )
        return catalogue

    def _registry_contexts(self) -> Dict[str, Any]:
        """Return the registry contexts."""
        registry_path = self.path.parent / "registry.json"
        if not registry_path.exists():
            return {}
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
        return registry.get("contexts", {})

    def routing_payload(self) -> Dict[str, Any]:
        """Return the routing payload."""
        catalogue = self.load()
        active = self._registry_contexts()
        contexts = [
            item.model_dump(mode="json")
            for item in catalogue.contexts
            if active.get(item.context_id, {}).get("status") == PerspectiveStatus.ACTIVE.value
        ]
        return {
            "schema_version": catalogue.schema_version,
            "routing_only": True,
            "contexts": contexts,
        }

    def verify(self) -> Dict[str, Any]:
        """Verify perspective catalogue store."""
        catalogue = self.load()
        registry = self._registry_contexts()
        unknown = sorted(
            item.context_id for item in catalogue.contexts if item.context_id not in registry
        )
        inactive = sorted(
            item.context_id
            for item in catalogue.contexts
            if item.context_id in registry
            and registry[item.context_id].get("status") != PerspectiveStatus.ACTIVE.value
        )
        return {
            "voice_id": self.voice_id,
            "valid": not unknown and not inactive,
            "unknown_contexts": unknown,
            "inactive_contexts": inactive,
            "context_count": len(catalogue.contexts),
        }


class PerspectiveResolver:
    """Represent a perspective resolver."""

    def __init__(self, root: Path, runner: PerspectiveRunner):
        """Initialize the perspective resolver."""
        self.root = root.resolve()
        self.runner = runner

    def resolve(
        self,
        order: WorkOrder,
        policy: Dict[str, Any],
    ) -> PerspectiveResolution:
        """Resolve perspective resolver."""
        forced_disabled_reason = policy.get("force_disabled_reason")
        mode = (
            PerspectiveMode.DISABLED
            if forced_disabled_reason
            else order.perspective_mode or PerspectiveMode(policy["mode"])
        )
        if mode == PerspectiveMode.DISABLED:
            if order.perspective_selections:
                raise PerspectiveError(
                    "Perspective contexts cannot be supplied when perspective use "
                    "is disabled{}".format(
                        ": {}".format(forced_disabled_reason) if forced_disabled_reason else ""
                    )
                )
            return PerspectiveResolution(
                mode=mode,
                disabled_reason=forced_disabled_reason,
            )
        if order.perspective_selections:
            return PerspectiveResolution(
                mode=PerspectiveMode.EXPLICIT,
                selected=order.perspective_selections,
            )
        if mode == PerspectiveMode.EXPLICIT:
            return PerspectiveResolution(mode=mode)
        catalogue = PerspectiveCatalogueStore(self.root, order.voice_id).routing_payload()
        if not catalogue["contexts"]:
            return PerspectiveResolution(mode=mode)
        resolution = self.runner.run(
            role="briefing-agent",
            role_key="briefing-agent",
            instruction=(
                "Select zero, one, or more relevant perspective contexts from the "
                "routing-only catalogue. Use only listed context ids. Catalogue "
                "summaries are routing metadata, not author positions. Select no "
                "context for neutral content. Ask one focused question only when "
                "ambiguity would materially change the argument."
            ),
            payload={
                "work_order": order.model_dump(mode="json"),
                "perspective_catalogue": catalogue,
                "allow_multiple": bool(policy.get("allow_multiple")),
                "ask_when_ambiguous": bool(policy.get("ask_when_ambiguous")),
            },
            options=AgentRunOptions(
                order=order,
                output_model=PerspectiveResolution,
                provider=order.provider,
            ),
        )
        resolution.mode = mode
        allowed = {item["context_id"] for item in catalogue["contexts"]}
        selected_ids = [item.context_id for item in resolution.selected]
        if len(selected_ids) != len(set(selected_ids)):
            raise PerspectiveError("Perspective resolver selected duplicate contexts")
        invalid = sorted(
            item.context_id for item in resolution.selected if item.context_id not in allowed
        )
        if invalid:
            raise PerspectiveError(
                "Perspective resolver selected unavailable contexts: {}".format(", ".join(invalid))
            )
        if not policy.get("allow_multiple") and len(resolution.selected) > 1:
            raise PerspectiveError(
                "Perspective resolver selected multiple contexts but allow_multiple is false"
            )
        if resolution.needs_clarification and not policy.get("ask_when_ambiguous"):
            resolution.needs_clarification = False
            resolution.clarification_question = None
            resolution.selected = []
        return resolution


class PerspectiveProposal(PerspectiveProposalCandidate):
    """Represent a perspective proposal."""

    id: str = Field(default_factory=lambda: "proposal-" + uuid4().hex[:12])
    owner_voice_id: str
    context_id: str
    run_id: str
    status: str = "candidate"
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
