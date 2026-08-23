"""Resolve, migrate, freeze, and transition version-scoped learning epochs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Optional

from ..storage import RunStore
from ..versioned_artifacts import hash_json
from .models import (
    LearningDispositionAction,
    LearningEpoch,
    LearningEpochTransitionReceipt,
    LearningSelection,
)


def epoch_path(root: Path, voice_id: str, voice_version: str) -> Path:
    """Return the canonical memory path for one immutable voice version.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.
        voice_version (str): Immutable voice version.

    Returns:
        Path: Version-scoped learning-memory path.
    """
    return root / "profiles" / voice_id / "learnings" / voice_version / "memory.json"


def load_epoch(
    root: Path,
    voice_id: str,
    voice_version: str,
    *,
    migrate_legacy: bool = False,
) -> LearningEpoch:
    """Load learning records with immutable voice-version provenance.

    Legacy records are admitted only when their provenance names the requested version
    or when they have no version and explicit migration targets the current version.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.
        voice_version (str): Immutable voice version.
        migrate_legacy (bool): Persist an explicit legacy assignment. Defaults to ``False``.

    Returns:
        LearningEpoch: Exact version-scoped learning memory.
    """
    path = epoch_path(root, voice_id, voice_version)
    if path.is_file():
        stored = json.loads(path.read_text(encoding="utf-8"))
        if stored.get("voice_id") and stored.get("voice_version"):
            return LearningEpoch.model_validate(stored)
        epoch = LearningEpoch(
            voice_id=voice_id,
            voice_version=voice_version,
            created_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC).isoformat(),
            records=stored.get("records", []),
        )
        if migrate_legacy:
            RunStore._atomic_text(path, epoch.model_dump_json(indent=2))
        return epoch
    legacy = root / "profiles" / voice_id / "learnings" / "memory.json"
    records: list[dict[str, Any]] = []
    if legacy.is_file():
        data = json.loads(legacy.read_text(encoding="utf-8"))
        admitted_versions = {voice_version}
        if migrate_legacy:
            admitted_versions.add(None)
        records = [
            record
            for record in data.get("records", [])
            if record.get("voice_version") in admitted_versions
        ]
    epoch = LearningEpoch(
        voice_id=voice_id,
        voice_version=voice_version,
        created_at=datetime.now(UTC).isoformat(),
        records=records,
    )
    if migrate_legacy:
        RunStore._atomic_text(path, epoch.model_dump_json(indent=2))
    return epoch


def epoch_hash(epoch: LearningEpoch) -> str:
    """Return a canonical hash for one complete learning epoch.

    Args:
        epoch (LearningEpoch): Version-scoped memory to hash.

    Returns:
        str: Canonical JSON hash.
    """
    return hash_json(epoch.model_dump(mode="json"))


def active_learning_records(epoch: LearningEpoch) -> list[dict[str, Any]]:
    """Return active learning records from one exact epoch.

    Args:
        epoch (LearningEpoch): Version-scoped memory to inspect.

    Returns:
        list[dict[str, Any]]: Active records in persisted order.
    """
    return [record for record in epoch.records if record.get("status") == "active"]


@dataclass
class LearningEpochTransition:
    """Apply and compensate one version-scoped learning transition."""

    prior_path: Optional[Path]
    resulting_path: Path
    prior_epoch: Optional[LearningEpoch]
    frozen_epoch: Optional[LearningEpoch]
    resulting_epoch: LearningEpoch
    receipt: LearningEpochTransitionReceipt
    prior_original: Optional[str]
    resulting_original: Optional[str]

    def apply(self) -> None:
        """Persist the frozen and new epochs atomically per file.

        Returns:
            None: Epoch files and the transition receipt are written.
        """
        try:
            if self.prior_path and self.frozen_epoch:
                RunStore._atomic_text(self.prior_path, self.frozen_epoch.model_dump_json(indent=2))
            RunStore._atomic_text(
                self.resulting_path, self.resulting_epoch.model_dump_json(indent=2)
            )
            RunStore._atomic_text(
                self.resulting_path.parent / "epoch-transition-receipt.json",
                self.receipt.model_dump_json(indent=2),
            )
        except Exception:
            self.rollback()
            raise

    def rollback(self) -> None:
        """Restore the exact pre-transition epoch state.

        Returns:
            None: Prior contents are restored and newly created files are removed.
        """
        if self.prior_path:
            if self.prior_original is None:
                self.prior_path.unlink(missing_ok=True)
            else:
                RunStore._atomic_text(self.prior_path, self.prior_original)
        if self.resulting_original is None:
            self.resulting_path.unlink(missing_ok=True)
            (self.resulting_path.parent / "epoch-transition-receipt.json").unlink(missing_ok=True)
        else:
            RunStore._atomic_text(self.resulting_path, self.resulting_original)


def prepare_epoch_transition(
    root: Path,
    voice_id: str,
    baseline_version: Optional[str],
    resulting_version: str,
    candidate_hash: str,
    selection: Optional[LearningSelection],
) -> LearningEpochTransition:
    """Prepare a deterministic freeze-and-create transition for activation.

    Carry forward only explicitly selected learning, record incorporated and discarded
    identifiers, and retain the original file contents for activation compensation.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.
        baseline_version (Optional[str]): Superseded immutable version, when present.
        resulting_version (str): Newly allocated immutable version.
        candidate_hash (str): Exact candidate being activated.
        selection (Optional[LearningSelection]): Reviewed prior-epoch dispositions.

    Returns:
        LearningEpochTransition: Prepared compensating transition.
    """
    now = datetime.now(UTC).isoformat()
    prior_path = epoch_path(root, voice_id, baseline_version) if baseline_version else None
    prior_epoch = (
        load_epoch(root, voice_id, baseline_version, migrate_legacy=False)
        if baseline_version
        else None
    )
    frozen_epoch = prior_epoch.model_copy(deep=True) if prior_epoch else None
    if frozen_epoch:
        frozen_epoch.status = "frozen"
        frozen_epoch.frozen_at = now
        frozen_epoch.frozen_by_candidate_hash = candidate_hash
    carried_ids = (
        {
            item.learning_id
            for item in selection.dispositions
            if item.disposition == LearningDispositionAction.CARRY_FORWARD
        }
        if selection
        else set()
    )
    prior_records = prior_epoch.records if prior_epoch else []
    resulting_epoch = LearningEpoch(
        voice_id=voice_id,
        voice_version=resulting_version,
        created_at=now,
        records=[record for record in prior_records if record.get("id") in carried_ids],
    )
    incorporated = (
        [
            item.learning_id
            for item in selection.dispositions
            if item.disposition == LearningDispositionAction.INCORPORATE
        ]
        if selection
        else []
    )
    dispositions_hash = hash_json(selection.model_dump(mode="json")) if selection else None
    receipt = LearningEpochTransitionReceipt(
        voice_id=voice_id,
        baseline_version=baseline_version,
        resulting_version=resulting_version,
        prior_epoch_hash=epoch_hash(prior_epoch) if prior_epoch else None,
        resulting_epoch_hash=epoch_hash(resulting_epoch),
        incorporated_learning_ids=incorporated,
        carried_forward_learning_ids=sorted(carried_ids),
        dispositions_hash=dispositions_hash,
        activated_at=now,
    )
    resulting_path = epoch_path(root, voice_id, resulting_version)
    return LearningEpochTransition(
        prior_path=prior_path,
        resulting_path=resulting_path,
        prior_epoch=prior_epoch,
        frozen_epoch=frozen_epoch,
        resulting_epoch=resulting_epoch,
        receipt=receipt,
        prior_original=prior_path.read_text(encoding="utf-8")
        if prior_path and prior_path.exists()
        else None,
        resulting_original=(
            resulting_path.read_text(encoding="utf-8") if resulting_path.exists() else None
        ),
    )
