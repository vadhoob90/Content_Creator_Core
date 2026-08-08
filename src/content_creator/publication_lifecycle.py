"""Coordinate deterministic and human-governed publication gates."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional, Type

from pydantic import BaseModel

from .domain import RunEvent, RunState, RunStatus
from .perspective_semantic_review import (
    PerspectiveSemanticReview,
    SemanticReviewEvidence,
    SemanticReviewReceipt,
)
from .publication_provenance import PublicationProvenance
from .storage import RunStore
from .versioned_artifacts import hash_file


class PublicationReviewRequired(RuntimeError):
    """Report semantic findings that require an author decision."""

    def __init__(self, report: Dict[str, Any]):
        """Initialize the review-required signal.

        Args:
            report (Dict[str, Any]): Privacy-safe review summary for the caller.

        Returns:
            None: The exception is initialized in place.
        """
        super().__init__("Perspective semantic review requires an author decision")
        self.report = report


class PublicationGateEvidence(BaseModel):
    """Represent complete evidence returned by the publication boundary."""

    perspective_evaluation: Dict[str, Any]
    evaluation_artifact_hash: str
    semantic_review: SemanticReviewReceipt


class PublicationLifecycle:
    """Manage publication gate ordering without writing destination content."""

    def __init__(
        self,
        root: Path,
        store: RunStore,
        provenance: PublicationProvenance,
        semantic_review: PerspectiveSemanticReview,
        policy: Dict[str, Any],
        error_type: Type[RuntimeError],
    ):
        """Initialize publication gate collaborators.

        Args:
            root (Path): Workspace root.
            store (RunStore): Run artifact store.
            provenance (PublicationProvenance): Deterministic provenance service.
            semantic_review (PerspectiveSemanticReview): Model-assisted review service.
            policy (Dict[str, Any]): Validated publication provenance policy.
            error_type (Type[RuntimeError]): Public orchestration error type.

        Returns:
            None: The lifecycle is initialized in place.
        """
        self.root = root.resolve()
        self.store = store
        self.provenance = provenance
        self.semantic_review = semantic_review
        self.policy = policy
        self.error_type = error_type

    def prepare(
        self,
        state: RunState,
        draft: str,
        approved_by: Optional[str] = None,
        review_notes: Optional[str] = None,
    ) -> PublicationGateEvidence:
        """Prepare exact-draft evidence before any publication destination write.

        Args:
            state (RunState): Reviewed run proposed for publication.
            draft (str): Exact publication draft.
            approved_by (Optional[str]): Author reviewer resolving persisted findings.
                Defaults to ``None``.
            review_notes (Optional[str]): Optional author review notes. Defaults to ``None``.

        Returns:
            PublicationGateEvidence: Deterministic and semantic evidence for the receipt.

        """
        evaluation, evaluation_hash = self._deterministic(state, draft)
        semantic = self._semantic(state, draft, approved_by, review_notes)
        return PublicationGateEvidence(
            perspective_evaluation=evaluation,
            evaluation_artifact_hash=evaluation_hash,
            semantic_review=semantic.receipt,
        )

    def _deterministic(self, state: RunState, draft: str) -> tuple[Dict[str, Any], str]:
        """Return exact-draft deterministic evidence or fail the run visibly.

        Args:
            state (RunState): Reviewed run proposed for publication.
            draft (str): Exact publication draft.

        Returns:
            tuple[Dict[str, Any], str]: Evaluation mapping and artifact hash.

        Raises:
            self.error_type: If publication provenance cannot be verified.
        """
        try:
            evaluation = self.provenance.evaluate(state, draft)
            artifact = self.store.write_artifact(
                state.id, "publication-perspective-evaluation.json", evaluation
            )
            return evaluation, hash_file(artifact)
        except Exception as exc:
            self._record_failure(state, "publication_provenance_failed", str(exc))
            raise self.error_type(str(exc)) from exc

    def _semantic(
        self,
        state: RunState,
        draft: str,
        approved_by: Optional[str],
        review_notes: Optional[str],
    ) -> SemanticReviewEvidence:
        """Return semantic evidence or pause for an explicit author decision.

        Skip model work when no perspective is selected, preserve explicit opt-out policy,
        and persist review-required state before returning control to the author.

        Args:
            state (RunState): Reviewed run proposed for publication.
            draft (str): Exact publication draft.
            approved_by (Optional[str]): Reviewer resolving persisted findings.
            review_notes (Optional[str]): Optional reviewer notes.

        Returns:
            SemanticReviewEvidence: Passed, approved, disabled, or inapplicable evidence.

        Raises:
            PublicationReviewRequired: If findings require author review.
            self.error_type: If semantic evaluation or approval cannot be completed.
        """
        if not state.work_order.perspective_selections:
            return self.semantic_review.skipped("not_applicable")
        if self.policy["semantic_review"] == "off":
            return self.semantic_review.skipped("disabled")
        try:
            evidence = (
                self.semantic_review.approve(state, draft, approved_by, review_notes)
                if approved_by is not None
                else self.semantic_review.assess(state, draft)
            )
        except Exception as exc:
            self._record_failure(state, "publication_semantic_review_failed", str(exc))
            raise self.error_type(str(exc)) from exc
        if evidence.receipt.status != "review_required":
            return evidence
        state.status = RunStatus.NEEDS_AUTHOR
        state.events.append(
            RunEvent(
                name="publication_review_required",
                detail=",".join(evidence.receipt.review_required_codes),
            )
        )
        self.store.save_state(state)
        raise PublicationReviewRequired(
            {
                "schema_version": "1.0",
                "status": "review_required",
                "run_id": state.id,
                "artifact": evidence.artifact_path,
                "review_required_codes": evidence.receipt.review_required_codes,
                "informational_codes": evidence.receipt.informational_codes,
                "next_action": (
                    "Review the semantic findings, revise the draft, or repeat publish with "
                    "--perspective-review-approved-by <reviewer>."
                ),
            }
        )

    def _record_failure(self, state: RunState, event: str, detail: str) -> None:
        """Record a visible pre-publication failure without touching destinations.

        Args:
            state (RunState): Run being paused for author attention.
            event (str): Stable failure event name.
            detail (str): Human-readable failure detail.

        Returns:
            None: State is updated and persisted in place.
        """
        state.status = RunStatus.NEEDS_AUTHOR
        state.events.append(RunEvent(name=event, detail=detail))
        self.store.save_state(state)
