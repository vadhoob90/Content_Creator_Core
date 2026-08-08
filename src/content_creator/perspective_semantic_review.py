"""Run human-governed semantic review for selected perspectives."""

from __future__ import annotations

import json
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Protocol

from pydantic import BaseModel, Field

from .domain import RunState, utc_now
from .perspectives import PerspectiveRegistry
from .runner_models import AgentRunOptions
from .storage import RunStore
from .versioned_artifacts import hash_file, hash_json


class PerspectiveSemanticRunner(Protocol):
    """Represent the agent runner needed for semantic review."""

    def run(
        self,
        role: str,
        role_key: str,
        instruction: str,
        payload: Dict[str, Any],
        options: AgentRunOptions | None = None,
    ) -> Any:
        """Run one structured semantic review request.

        Args:
            role (str): Repository-owned role identifier.
            role_key (str): Model-selection role key.
            instruction (str): Task-specific instruction.
            payload (Dict[str, Any]): Structured review evidence.
            options (AgentRunOptions | None): Provider and schema options. Defaults to ``None``.

        Returns:
            Any: Parsed provider response.

        Raises:
            NotImplementedError: Protocol implementations must provide the runner behavior.
        """
        raise NotImplementedError


class SemanticFindingCategory(str, Enum):
    """Enumerate model findings that cannot directly reject publication."""

    REVIEW_REQUIRED = "review_required"
    INFORMATIONAL = "informational"


class PerspectiveSemanticFinding(BaseModel):
    """Represent one bounded semantic perspective finding."""

    category: SemanticFindingCategory
    code: str
    context_id: str
    entry_id: Optional[str] = None
    detail: str
    confidence: float = Field(default=0.5, ge=0, le=1)


class PerspectiveSemanticAssessment(BaseModel):
    """Represent model-assisted findings without a publication decision."""

    schema_version: str = "1.0"
    findings: list[PerspectiveSemanticFinding] = Field(default_factory=list)
    summary: str = "Semantic perspective review completed"


class PerspectiveSemanticArtifact(BaseModel):
    """Represent ignored run evidence for one exact-draft semantic review."""

    schema_version: str = "1.0"
    run_id: str
    draft_hash: str
    assessment: PerspectiveSemanticAssessment


class PerspectiveReviewDecision(BaseModel):
    """Represent an explicit author resolution of review-required findings."""

    schema_version: str = "1.0"
    run_id: str
    draft_hash: str
    assessment_artifact_hash: str
    decision: str = "approve"
    approved_by: str
    notes: Optional[str] = None
    decided_at: str


class SemanticReviewReceipt(BaseModel):
    """Represent the privacy-safe semantic result copied into a receipt."""

    status: str = "not_applicable"
    assessment_artifact_hash: Optional[str] = None
    decision_artifact_hash: Optional[str] = None
    review_required_codes: list[str] = Field(default_factory=list)
    informational_codes: list[str] = Field(default_factory=list)


class SemanticReviewEvidence(BaseModel):
    """Represent semantic receipt evidence and its ignored artifact path."""

    receipt: SemanticReviewReceipt
    artifact_path: Optional[str] = None


class PerspectiveSemanticReview:
    """Manage model-assisted review while reserving decisions for the author."""

    artifact_name = "publication-semantic-review.json"
    decision_name = "publication-semantic-review-decision.json"

    def __init__(
        self,
        root: Path,
        runner: PerspectiveSemanticRunner,
        store: RunStore,
    ):
        """Initialize semantic review services.

        Args:
            root (Path): Workspace root.
            runner (PerspectiveSemanticRunner): Structured-output agent runner.
            store (RunStore): Run artifact store.

        Returns:
            None: The service is initialized in place.
        """
        self.root = root.resolve()
        self.runner = runner
        self.store = store

    def assess(self, state: RunState, draft: str) -> SemanticReviewEvidence:
        """Assess selected perspectives against the exact publication draft.

        Args:
            state (RunState): Reviewed run proposed for publication.
            draft (str): Exact publication draft.

        Returns:
            SemanticReviewEvidence: Privacy-safe receipt summary and ignored artifact path.

        """
        assessment = self.runner.run(
            role="perspective-evaluator",
            role_key="perspective-evaluator",
            instruction=self._instruction(),
            payload=self._payload(state, draft),
            options=AgentRunOptions(
                order=state.work_order,
                output_model=PerspectiveSemanticAssessment,
                provider=state.work_order.provider,
            ),
        )
        self._validate_findings(state, assessment)
        artifact = PerspectiveSemanticArtifact(
            run_id=state.id,
            draft_hash=hash_json(draft),
            assessment=assessment,
        )
        artifact_path = self.store.write_artifact(state.id, self.artifact_name, artifact)
        return SemanticReviewEvidence(
            receipt=self._receipt(assessment, hash_file(artifact_path)),
            artifact_path=str(artifact_path.relative_to(self.root)),
        )

    def approve(
        self,
        state: RunState,
        draft: str,
        approved_by: str,
        notes: Optional[str] = None,
    ) -> SemanticReviewEvidence:
        """Record explicit author approval for unchanged review-required evidence.

        Args:
            state (RunState): Run containing persisted semantic findings.
            draft (str): Exact unchanged publication draft.
            approved_by (str): Reviewer identity recorded in ignored run evidence.
            notes (Optional[str]): Optional review notes. Defaults to ``None``.

        Returns:
            SemanticReviewEvidence: Author-approved privacy-safe receipt summary.

        Raises:
            ValueError: If approval is empty, stale, or lacks review-required findings.
        """
        reviewer = approved_by.strip()
        if not reviewer:
            raise ValueError("Perspective review approval requires a reviewer identity")
        artifact_path = self.store.run_dir(state.id) / self.artifact_name
        if not artifact_path.is_file():
            raise ValueError("No pending perspective semantic review exists")
        artifact = PerspectiveSemanticArtifact.model_validate_json(
            artifact_path.read_text(encoding="utf-8")
        )
        if artifact.draft_hash != hash_json(draft):
            raise ValueError("Perspective review approval does not match the current final draft")
        receipt = self._receipt(artifact.assessment, hash_file(artifact_path))
        if not receipt.review_required_codes:
            raise ValueError("Perspective semantic review has no findings requiring approval")
        decision = PerspectiveReviewDecision(
            run_id=state.id,
            draft_hash=artifact.draft_hash,
            assessment_artifact_hash=hash_file(artifact_path),
            approved_by=reviewer,
            notes=notes,
            decided_at=utc_now().isoformat(),
        )
        decision_path = self.store.write_artifact(state.id, self.decision_name, decision)
        receipt.status = "author_approved"
        receipt.decision_artifact_hash = hash_file(decision_path)
        return SemanticReviewEvidence(
            receipt=receipt,
            artifact_path=str(artifact_path.relative_to(self.root)),
        )

    @staticmethod
    def skipped(status: str) -> SemanticReviewEvidence:
        """Return evidence for a disabled or inapplicable semantic review.

        Args:
            status (str): Stable disabled or not-applicable status.

        Returns:
            SemanticReviewEvidence: Empty semantic review evidence.
        """
        return SemanticReviewEvidence(receipt=SemanticReviewReceipt(status=status))

    def _validate_findings(
        self,
        state: RunState,
        assessment: PerspectiveSemanticAssessment,
    ) -> None:
        """Validate that model findings remain inside resolved perspective context.

        Args:
            state (RunState): Run defining selected contexts and entries.
            assessment (PerspectiveSemanticAssessment): Model-assisted findings.

        Returns:
            None: Findings are accepted without mutation.

        Raises:
            ValueError: If a finding references unavailable perspective evidence.
        """
        allowed: Dict[str, set[str]] = {}
        order = state.work_order
        requested = (
            order.author_contribution.reusable_perspective_entry_ids
            if order.author_contribution
            else []
        )
        for index, selection in enumerate(order.perspective_selections):
            resolved = PerspectiveRegistry(self.root, order.voice_id).resolve(
                selection.context_id,
                selection.version,
                allow_inactive=True,
            )
            selected_ids = requested if index == 0 and requested else resolved["active_entry_ids"]
            allowed[selection.context_id] = set(selected_ids)
        for finding in assessment.findings:
            if finding.context_id not in allowed:
                raise ValueError(
                    f"Perspective evaluator referenced unknown context: {finding.context_id}"
                )
            if finding.entry_id and finding.entry_id not in allowed[finding.context_id]:
                raise ValueError(
                    f"Perspective evaluator referenced unavailable entry: {finding.entry_id}"
                )

    def _payload(self, state: RunState, draft: str) -> Dict[str, Any]:
        """Return bounded run evidence for semantic perspective review.

        Args:
            state (RunState): Reviewed run supplying resolved context.
            draft (str): Exact publication draft.

        Returns:
            Dict[str, Any]: Work order, draft, and optional research evidence.
        """
        research_path = self.store.run_dir(state.id) / "research.json"
        return {
            "work_order": state.work_order.model_dump(mode="json"),
            "draft": draft,
            "research": (
                json.loads(research_path.read_text(encoding="utf-8"))
                if research_path.is_file()
                else None
            ),
        }

    @staticmethod
    def _instruction() -> str:
        """Return the bounded semantic review instruction.

        Returns:
            str: Human-governed evaluator task contract.
        """
        return (
            "Compare only the selected approved perspective entries with the exact draft. "
            "Report possible omitted material qualifications, possible counterpositions "
            "asserted as the author's view, and ambiguous attribution as review_required. "
            "Report a possible new author position as informational. Never decide whether "
            "to publish, never create deterministic failures, and do not treat a perspective "
            "as factual authority. Return concise structured findings only."
        )

    @staticmethod
    def _receipt(
        assessment: PerspectiveSemanticAssessment,
        artifact_hash: str,
    ) -> SemanticReviewReceipt:
        """Return a privacy-safe tracked summary of ignored assessment evidence.

        Args:
            assessment (PerspectiveSemanticAssessment): Full ignored semantic result.
            artifact_hash (str): Hash binding the summary to ignored run evidence.

        Returns:
            SemanticReviewReceipt: Finding codes without draft excerpts or rationale.
        """
        review_codes = sorted(
            {
                item.code
                for item in assessment.findings
                if item.category == SemanticFindingCategory.REVIEW_REQUIRED
            }
        )
        information_codes = sorted(
            {
                item.code
                for item in assessment.findings
                if item.category == SemanticFindingCategory.INFORMATIONAL
            }
        )
        return SemanticReviewReceipt(
            status="review_required" if review_codes else "passed",
            assessment_artifact_hash=artifact_hash,
            review_required_codes=review_codes,
            informational_codes=information_codes,
        )
