"""Bind reviewed text and claim decisions to immutable revision evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from .domain import RunState, RunStatus
from .edit_transaction import JOURNAL
from .storage import RunStore, StateWriter, StorageError
from .versioned_artifacts import hash_file


class DraftIntegrity(BaseModel):
    """Record which exact draft and research carry a claim-review decision."""

    schema_version: Literal["1.0"] = "1.0"
    revision: int
    draft_sha256: str
    research_sha256: str | None = None
    baseline_sha256: str | None = None
    claim_review_status: Literal["not_required", "required", "approved"] = "not_required"
    change_kind: Literal["generated", "trailing-newlines", "needs_review"] = "generated"
    approved_by: str | None = None
    notes: str | None = None
    quality_evidence: Literal["current", "historical"] = "current"


def text_hash(text: str) -> str:
    """Hash exact UTF-8 text without Markdown or whitespace normalization.

    Args:
        text (str): Exact artifact text.

    Returns:
        str: Prefixed SHA-256 digest.
    """
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def research_hash(run: Path) -> str | None:
    """Read the digest of the current research artifact when present.

    Args:
        run (Path): Validated run directory.

    Returns:
        str | None: Prefixed artifact digest or absent research.
    """
    path = run / "research.json"
    return hash_file(path) if path.is_file() else None


def read_integrity(run: Path) -> DraftIntegrity | None:
    """Read a draft binding without manufacturing legacy evidence.

    Args:
        run (Path): Validated run directory.

    Returns:
        DraftIntegrity | None: Persisted binding or absent legacy evidence.
    """
    path = run / "draft-integrity.json"
    return DraftIntegrity.model_validate_json(path.read_text()) if path.exists() else None


def assess_edit(
    previous: DraftIntegrity | None,
    baseline: str,
    draft: str,
    revision: int,
    evidence_hash: str | None,
) -> DraftIntegrity:
    """Evaluate claim changes conservatively except for final newline changes.

    Args:
        previous (DraftIntegrity | None): Earlier binding, if available.
        baseline (str): Verified accepted predecessor text.
        draft (str): Exact adopted text.
        revision (int): New revision number.
        evidence_hash (str | None): Digest of research supporting the new revision.

    Returns:
        DraftIntegrity: New binding with any inherited review requirement retained.
    """
    unchanged = baseline.rstrip("\r\n") == draft.rstrip("\r\n")
    same_research = previous is not None and previous.research_sha256 == evidence_hash
    cleared = previous is not None and previous.claim_review_status != "required"
    safe = unchanged and same_research and cleared
    return DraftIntegrity(
        revision=revision,
        draft_sha256=text_hash(draft),
        research_sha256=evidence_hash,
        baseline_sha256=text_hash(baseline),
        claim_review_status="not_required" if safe else "required",
        change_kind="trailing-newlines" if safe else "needs_review",
        quality_evidence="historical",
    )


def capture_accepted(root: Path, state: RunState, write: StateWriter) -> None:
    """Preserve accepted revisions and prevent later saves from blessing file edits.

    Args:
        root (Path): Workspace root.
        state (RunState): State about to be persisted by the application.
        write (StateWriter): Atomic text persistence callback.

    Returns:
        None: New accepted snapshots are written when justified by revision evidence.

    Raises:
        StorageError: If a legacy draft differs from its recorded final hash.
    """
    run = root / "runs" / state.id
    final = run / "final.md"
    if not final.is_file() or state.status not in {RunStatus.READY, RunStatus.NEEDS_AUTHOR}:
        return
    previous = read_integrity(run)
    if previous and previous.revision >= state.revision:
        state.claim_review_required = previous.claim_review_status == "required"
        if previous.claim_review_status == "required":
            state.status = RunStatus.NEEDS_AUTHOR
        return
    draft = final.read_bytes().decode("utf-8")
    snapshot = run / "accepted" / f"r{state.revision:04d}.md"
    if previous:
        baseline = verified_baseline(run, previous.draft_sha256)
        binding = assess_edit(previous, baseline, draft, state.revision, research_hash(run))
        binding.quality_evidence = "current"
    elif not _legacy_hash_matches(run, text_hash(draft)):
        raise StorageError("Draft hash changed; adopt the author edit before refreshing evidence")
    else:
        binding = DraftIntegrity(
            revision=state.revision,
            draft_sha256=text_hash(draft),
            research_sha256=research_hash(run),
        )
    state.claim_review_required = binding.claim_review_status == "required"
    if state.claim_review_required:
        state.status = RunStatus.NEEDS_AUTHOR
    if not snapshot.exists():
        RunStore.atomic_bytes(snapshot, draft.encode("utf-8"))
    write(run / "draft-integrity.json", binding.model_dump_json(indent=2))
    record_claim_binding(run, binding, write)


def archive_manifest(root: Path, state: RunState) -> None:
    """Preserve the first production manifest for each accepted revision.

    Args:
        root (Path): Workspace root.
        state (RunState): State whose production manifest was refreshed.

    Returns:
        None: An immutable manifest snapshot is created when its text exists.
    """
    run = root / "runs" / state.id
    destination = run / "accepted" / f"r{state.revision:04d}.manifest.json"
    if destination.with_name(f"r{state.revision:04d}.md").is_file() and not destination.exists():
        RunStore.atomic_bytes(destination, (run / "production-manifest.json").read_bytes())


def verified_baseline(run: Path, expected: str, supplied: str | None = None) -> str:
    """Return a predecessor only from exact hash-matching evidence.

    Args:
        run (Path): Validated run directory.
        expected (str): Recorded predecessor SHA-256 digest.
        supplied (str | None): Optional author-supplied original. Defaults to ``None``.

    Returns:
        str: Exact verified predecessor text.

    Raises:
        StorageError: If no retained or supplied text matches the recorded digest.
    """
    if supplied is not None and text_hash(supplied) == expected:
        return supplied
    candidates = [run / "final.md", *sorted((run / "accepted").glob("r*.md"))]
    candidates.extend(sorted(run.glob("draft-*.md")))
    for path in candidates:
        if path.is_file() and hash_file(path) == expected:
            return path.read_bytes().decode("utf-8")
    raise StorageError("Missing verified baseline; supply the original matching the recorded hash")


def ensure_draft_integrity(run: Path, draft: str) -> None:
    """Reject stale draft, research, or claim decisions before publication.

    Args:
        run (Path): Validated run directory.
        draft (str): Exact candidate publication text.

    Returns:
        None: A present binding passes all integrity checks.

    Raises:
        StorageError: If text, research, or claim approval is stale.
    """
    if (run / JOURNAL).exists():
        raise StorageError("Interrupted author edit; run recover-edit before publication")
    binding = read_integrity(run)
    if binding is None:
        if not _legacy_hash_matches(run, text_hash(draft)):
            raise StorageError("Draft hash changed; adopt the author edit before publication")
        return
    if binding.draft_sha256 != text_hash(draft):
        raise StorageError("Draft hash changed; adopt the author edit before publication")
    if binding.research_sha256 != research_hash(run):
        raise StorageError("Research hash changed; adopt and review the new evidence")
    if binding.claim_review_status == "required":
        raise StorageError("Changed claims require author review before publication")
    if binding.quality_evidence == "historical":
        validation = json.loads((run / f"validation-{binding.revision:02d}.json").read_text())
        if validation["errors"]:
            raise StorageError("Adopted draft has unresolved deterministic validation errors")


def _legacy_hash_matches(run: Path, digest: str) -> bool:
    """Compare legacy text to recorded final metadata when it exists.

    Args:
        run (Path): Validated run directory.
        digest (str): Candidate text digest.

    Returns:
        bool: Whether existing final metadata agrees, or no final hash was recorded.
    """
    path = run / "production-manifest.json"
    if not path.is_file():
        return True
    manifest = json.loads(path.read_text(encoding="utf-8"))
    hashes = [
        a["content_hash"] for a in manifest.get("artifacts", []) if a["kind"] == "final-draft"
    ]
    return not hashes or hashes == [digest]


def record_claim_binding(run: Path, binding: DraftIntegrity, write: StateWriter) -> None:
    """Update claim and research provenance with the current exact-content review state.

    Args:
        run (Path): Validated run directory.
        binding (DraftIntegrity): Current revision and claim-review evidence.
        write (StateWriter): Atomic text persistence callback.

    Returns:
        None: Prior provenance is retained with explicit current draft/research status.
    """
    path = run / "claim-provenance.json"
    payload = json.loads(path.read_text()) if path.is_file() else {}
    payload["final_draft_revision"] = binding.revision
    payload["claim_review_status"] = binding.claim_review_status
    payload["draft_integrity"] = binding.model_dump(mode="json")
    if binding.change_kind != "generated" and binding.research_sha256 is not None:
        payload["research_record"] = {
            "status": "review_required"
            if binding.claim_review_status == "required"
            else "completed",
            "research_sha256": binding.research_sha256,
            "draft_sha256": binding.draft_sha256,
        }
    write(path, json.dumps(payload, indent=2, ensure_ascii=False))
