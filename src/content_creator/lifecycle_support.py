"""Provide persistence, hashing, epoch, default, and verification helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable, Optional

import yaml

from .lifecycle_models import (
    LifecycleReceipt,
    LifecycleVerification,
    VersionLifecycleCatalogue,
    VersionLifecycleRecord,
)
from .storage import RunStore
from .versioned_artifacts import hash_file, hash_json
from .voice_models import VoiceManifest
from .voice_upgrade.epochs import epoch_hash, epoch_path, load_epoch
from .voice_upgrade.models import LearningEpoch


def utc_timestamp() -> str:
    """Return an ISO timestamp suitable for a persisted author decision.

    Returns:
        str: Current timezone-aware UTC timestamp.
    """
    return datetime.now(UTC).isoformat()


def validate_decision_text(actor: str, reason: str) -> tuple[str, str]:
    """Validate the human identity and explanation bound into a receipt.

    Args:
        actor (str): Human identity responsible for the decision.
        reason (str): Human-readable explanation for the decision.

    Returns:
        tuple[str, str]: Stripped actor and reason values.

    Raises:
        ValueError: If either required decision value is empty.
    """
    actor = actor.strip()
    reason = reason.strip()
    if not actor:
        raise ValueError("Lifecycle decisions require a non-empty actor")
    if not reason:
        raise ValueError("Lifecycle decisions require a non-empty reason")
    return actor, reason


def receipt_relative_path(root: Path, receipt_path: Path) -> str:
    """Return a stable workspace-relative receipt reference.

    Args:
        root (Path): Workspace root used as the reference base.
        receipt_path (Path): Absolute receipt artifact path.

    Returns:
        str: Workspace-relative receipt path.
    """
    return str(receipt_path.relative_to(root.resolve()))


def receipt_path_for(base: Path, receipt: LifecycleReceipt) -> Path:
    """Return the immutable content-addressed path for a lifecycle receipt.

    Args:
        base (Path): Lifecycle aggregate root.
        receipt (LifecycleReceipt): Receipt to address by its content hash.

    Returns:
        Path: Timestamped and content-addressed receipt path.
    """
    payload = receipt.model_dump(mode="json")
    digest = hash_json(payload).removeprefix("sha256:")
    stamp = receipt.decided_at.replace(":", "-").replace("+", "_")
    return base / "lifecycle" / "receipts" / f"{stamp}-{receipt.action}-{digest[:12]}.json"


def voice_withdrawal_updates(
    root: Path,
    voice_root: Path,
    receipt: LifecycleReceipt,
    transition: Any,
    evidence: Any,
    archive: Optional[Path],
    config_text: Optional[str],
) -> list[tuple[Path, str]]:
    """Build the atomic epoch, decision, default, and run withdrawal updates.

    Args:
        root (Path): Workspace root directory.
        voice_root (Path): Aggregate root for the selected voice.
        receipt (LifecycleReceipt): Immutable transition receipt.
        transition (Any): Validated voice transition decisions.
        evidence (Any): Selected version and learning-epoch evidence.
        archive (Optional[Path]): Optional epoch archive path.
        config_text (Optional[str]): Optional reviewed default configuration text.

    Returns:
        list[tuple[Path, str]]: Atomic artifact path and content replacements.
    """
    updates = epoch_updates(
        evidence.epoch,
        epoch_path(root, receipt.object_id, evidence.version),
        archive,
    )
    if config_text is not None:
        updates.append((root / "content-creator.yaml", config_text))
    for disposition in transition.dispositions:
        if disposition.action not in {"reject", "abandon"}:
            continue
        decision_name = "{}-{}.json".format(
            disposition.kind,
            disposition.artifact_hash.removeprefix("sha256:"),
        )
        updates.append(
            (
                voice_root / "lifecycle" / "candidate-decisions" / decision_name,
                receipt.model_dump_json(indent=2),
            )
        )
    if transition.run_disposition == "abandon":
        updates.extend(_abandoned_run_updates(root, transition))
    return updates


def _abandoned_run_updates(root: Path, transition: Any) -> list[tuple[Path, str]]:
    """Return state updates for explicitly abandoned in-flight runs.

    Args:
        root (Path): Workspace root directory.
        transition (Any): Validated transition with exact affected run identifiers.

    Returns:
        list[tuple[Path, str]]: Run-state artifact replacements.
    """
    updates: list[tuple[Path, str]] = []
    for run_id in transition.affected_runs:
        state_path = root / "runs" / run_id / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["status"] = "abandoned"
        state.setdefault("events", []).append(
            {
                "at": utc_timestamp(),
                "name": "abandoned_for_voice_retirement",
                "detail": f"{transition.actor}: {transition.reason}",
            }
        )
        updates.append((state_path, json.dumps(state, indent=2)))
    return updates


@dataclass
class AtomicArtifactTransaction:
    """Apply several atomic file replacements with whole-operation compensation."""

    updates: list[tuple[Path, str]]

    def commit(self) -> None:
        """Persist all replacements or restore every original byte sequence.

        Returns:
            None: Replacements are committed in place.
        """
        originals = {
            path: path.read_text(encoding="utf-8") if path.exists() else None
            for path, _ in self.updates
        }
        try:
            for path, content in self.updates:
                RunStore._atomic_text(path, content)
        except Exception:
            for path, original in reversed(list(originals.items())):
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    RunStore._atomic_text(path, original)
            raise


def default_voice(root: Path) -> Optional[str]:
    """Read the configured default voice without choosing a replacement.

    Args:
        root (Path): Workspace root containing the configuration.

    Returns:
        Optional[str]: Configured default voice identifier, when present.
    """
    path = root.resolve() / "content-creator.yaml"
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return (data.get("coordinator", {}) or {}).get("default_voice")


def updated_default_configuration(
    root: Path, voice_id: str, replacement: Optional[str], clear_default: bool
) -> Optional[str]:
    """Return reviewed default configuration text for a withdrawn default voice.

    Args:
        root (Path): Workspace root containing the configuration.
        voice_id (str): Voice being withdrawn.
        replacement (Optional[str]): Explicit replacement identifier, or ``None``.
        clear_default (bool): Whether to explicitly clear the current default.

    Returns:
        Optional[str]: Updated YAML text, or ``None`` when the voice is not default.

    Raises:
        ValueError: If a default decision is missing or refers to the withdrawn voice.
    """
    path = root.resolve() / "content-creator.yaml"
    if default_voice(root) != voice_id:
        return None
    if replacement is None and not clear_default:
        raise ValueError(
            "The selected voice is the default; pass --clear-default or --replacement-voice"
        )
    if replacement == voice_id:
        raise ValueError("A withdrawn voice cannot remain its own default replacement")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    coordinator = data.setdefault("coordinator", {})
    coordinator["default_voice"] = replacement
    return yaml.safe_dump(data, sort_keys=False)


def _next_epoch_id(base: Path) -> str:
    """Return the next monotonic activation epoch identifier.

    Args:
        base (Path): Directory containing archived activation epochs.

    Returns:
        str: Next ``activation-N`` identifier.
    """
    suffixes = [
        path.stem.removeprefix("activation-")
        for path in (base / "epochs").glob("activation-*.json")
    ]
    existing = [int(suffix) for suffix in suffixes if suffix.isdigit()]
    return f"activation-{max(existing, default=0) + 1}"


def freeze_epoch(
    root: Path, voice_id: str, version: str, actor: str, reason: str
) -> tuple[LearningEpoch, Path]:
    """Preserve the exact current activation epoch as frozen evidence.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable voice identifier.
        version (str): Selected immutable voice version.
        actor (str): Human identity responsible for the withdrawal.
        reason (str): Human-readable withdrawal explanation.

    Returns:
        tuple[LearningEpoch, Path]: Frozen epoch model and archive path.
    """
    path = epoch_path(root, voice_id, version)
    epoch = load_epoch(root, voice_id, version, migrate_legacy=True).model_copy(deep=True)
    epoch.epoch_id = epoch.epoch_id or _next_epoch_id(path.parent)
    if epoch.status != "frozen":
        epoch.status = "frozen"
        epoch.frozen_at = utc_timestamp()
        epoch.frozen_by_candidate_hash = hash_json({"actor": actor, "reason": reason})
    archive = path.parent / "epochs" / f"{epoch.epoch_id}.json"
    return epoch, archive


def open_epoch(root: Path, voice_id: str, version: str) -> tuple[LearningEpoch, Path]:
    """Create a new activation epoch for an unchanged immutable voice version.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable voice identifier.
        version (str): Selected immutable voice version.

    Returns:
        tuple[LearningEpoch, Path]: Active epoch model and canonical path.
    """
    prior = load_epoch(root, voice_id, version, migrate_legacy=True)
    path = epoch_path(root, voice_id, version)
    epoch = LearningEpoch(
        voice_id=voice_id,
        voice_version=version,
        epoch_id=_next_epoch_id(path.parent),
        status="active",
        created_at=utc_timestamp(),
        records=prior.records,
    )
    return epoch, path


def epoch_updates(
    epoch: LearningEpoch, path: Path, archive: Optional[Path] = None
) -> list[tuple[Path, str]]:
    """Render epoch state into transaction-ready file replacements.

    Args:
        epoch (LearningEpoch): Learning epoch to serialize.
        path (Path): Canonical learning epoch path.
        archive (Optional[Path]): Optional archive path. Defaults to ``None``.

    Returns:
        list[tuple[Path, str]]: Canonical and optional archive replacements.
    """
    text = epoch.model_dump_json(indent=2)
    updates = [(path, text)]
    if archive is not None:
        updates.append((archive, text))
    return updates


def version_catalogue(
    root: Path, voice_id: str, selected_version: Optional[str]
) -> VersionLifecycleCatalogue:
    """Load or deterministically reconstruct a voice-version lifecycle catalogue.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable voice identifier.
        selected_version (Optional[str]): Currently selected version, or ``None``.

    Returns:
        VersionLifecycleCatalogue: Complete deterministic version catalogue.
    """
    root = root.resolve()
    path = root / "profiles" / voice_id / "lifecycle" / "catalogue.json"
    stored: dict[str, VersionLifecycleRecord] = {}
    if path.exists():
        catalogue = VersionLifecycleCatalogue.model_validate_json(path.read_text(encoding="utf-8"))
        stored = {record.version: record for record in catalogue.records}
    versions_root = root / "profiles" / voice_id / "versions"
    versions: list[VersionLifecycleRecord] = []
    for manifest_path in sorted(versions_root.glob("*/manifest.json")):
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        receipt_path = manifest_path.parent / "approval-receipt.json"
        receipt = (
            json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.exists() else {}
        )
        epoch = load_epoch(root, voice_id, manifest.version, migrate_legacy=False)
        record = stored.get(manifest.version) or VersionLifecycleRecord(
            version=manifest.version,
            manifest_hash=hash_file(manifest_path),
            strategy=manifest.strategy.value,
            evidence_baseline_hash=manifest.evidence_baseline_hash,
            approval_receipt=(
                str(receipt_path.relative_to(root)) if receipt_path.exists() else None
            ),
            approved_at=receipt.get("approved_at"),
            reconstructed=True,
        )
        record.manifest_hash = hash_file(manifest_path)
        record.learning_epoch_id = epoch.epoch_id
        record.learning_epoch_hash = epoch_hash(epoch)
        record.relationship = "selected" if manifest.version == selected_version else "superseded"
        versions.append(record)
    for index, record in enumerate(versions[:-1]):
        if record.relationship == "superseded":
            record.successor_version = versions[index + 1].version
    return VersionLifecycleCatalogue(voice_id=voice_id, records=versions)


def catalogue_text(catalogue: VersionLifecycleCatalogue) -> str:
    """Render a lifecycle catalogue for atomic persistence.

    Args:
        catalogue (VersionLifecycleCatalogue): Catalogue to serialize.

    Returns:
        str: Pretty-printed catalogue JSON.
    """
    return catalogue.model_dump_json(indent=2)


def append_catalogue_receipt(
    catalogue: VersionLifecycleCatalogue,
    selected_version: str,
    relationship: str,
    receipt_path: str,
    epoch: Optional[LearningEpoch] = None,
) -> None:
    """Update selected-version lifecycle metadata without touching its manifest.

    Args:
        catalogue (VersionLifecycleCatalogue): Mutable lifecycle catalogue.
        selected_version (str): Selected immutable version identifier.
        relationship (str): Lifecycle relationship to record.
        receipt_path (str): Workspace-relative lifecycle receipt path.
        epoch (Optional[LearningEpoch]): Optional current epoch. Defaults to ``None``.

    Returns:
        None: The matching catalogue record is updated in place.
    """
    for record in catalogue.records:
        if record.version != selected_version:
            continue
        record.relationship = relationship
        if receipt_path not in record.lifecycle_receipts:
            record.lifecycle_receipts.append(receipt_path)
        if epoch is not None:
            record.learning_epoch_id = epoch.epoch_id
            record.learning_epoch_hash = epoch_hash(epoch)
        return


def latest_receipt(base: Path) -> Optional[str]:
    """Return the most recent receipt path relative to a lifecycle aggregate root.

    Args:
        base (Path): Lifecycle aggregate root.

    Returns:
        Optional[str]: Latest receipt path, when any receipt exists.
    """
    paths = sorted((base / "lifecycle" / "receipts").glob("*.json"))
    return str(paths[-1]) if paths else None


def verify_receipts(root: Path, bases: Iterable[Path]) -> LifecycleVerification:
    """Verify registry hashes, manifest hashes, and receipt schemas offline.

    Args:
        root (Path): Workspace root directory.
        bases (Iterable[Path]): Lifecycle aggregate roots to inspect.

    Returns:
        LifecycleVerification: Deterministic offline verification result.
    """
    root = root.resolve()
    failures: list[str] = []
    checked = 0
    paths = [
        path for base in bases for path in sorted((base / "lifecycle" / "receipts").glob("*.json"))
    ]
    for path in paths:
        checked += 1
        failure = _receipt_failure(root, path)
        if failure:
            failures.append(failure)
    return LifecycleVerification(valid=not failures, checked_receipts=checked, failures=failures)


def _receipt_failure(root: Path, path: Path) -> Optional[str]:
    """Return one deterministic verification failure, when present.

    Args:
        root (Path): Workspace root directory.
        path (Path): Receipt artifact to verify.

    Returns:
        Optional[str]: Failure detail, or ``None`` when the receipt is valid.
    """
    try:
        receipt = LifecycleReceipt.model_validate_json(path.read_text(encoding="utf-8"))
        receipt_digest = hash_json(receipt.model_dump(mode="json")).removeprefix("sha256:")
        if not path.stem.endswith(receipt_digest[:12]):
            return f"{path.relative_to(root)}: receipt content hash mismatch"
        if not receipt.selected_version or not receipt.selected_manifest_hash:
            return None
        if receipt.object_type == "voice":
            manifest = (
                root
                / "profiles"
                / receipt.object_id
                / "versions"
                / receipt.selected_version
                / "manifest.json"
            )
        else:
            manifest = path.parents[2] / "versions" / receipt.selected_version / "manifest.json"
        if not manifest.exists() or hash_file(manifest) != receipt.selected_manifest_hash:
            return f"{path.relative_to(root)}: selected manifest hash mismatch"
    except Exception as exc:
        return f"{path.relative_to(root)}: {exc}"
    return None
