"""Calculate voice-upgrade eligibility without provider or network work."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..ingestion import content_hash, read_source
from ..voice_models import VoiceManifest, VoiceWorkOrder
from .epochs import active_learning_records, load_epoch
from .evidence import load_evidence_baseline


def inspect_upgrade_eligibility(
    root: Path, voice_id: str, active: dict[str, Any]
) -> dict[str, Any]:
    """Return advisory local evidence and learning eligibility for one active voice.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.
        active (dict[str, Any]): Active registry record.

    Returns:
        dict[str, Any]: Counts, recommendation, and exact planning command.
    """
    version = active.get("active_version")
    if active.get("status") != "active" or not version:
        return {"eligible": False, "reason": "voice-not-active"}
    directory = root / "profiles" / voice_id / "versions" / str(version)
    manifest = VoiceManifest.model_validate_json(
        (directory / "manifest.json").read_text(encoding="utf-8")
    )
    baseline = load_evidence_baseline(root, voice_id, directory, manifest)
    represented = {record.content_hash for record in baseline.records}
    epoch = load_epoch(root, voice_id, str(version))
    learning_count = len(active_learning_records(epoch))
    new_hashes = _local_evidence_hashes(root, voice_id) - represented
    eligible = bool(new_hashes or learning_count)
    return {
        "eligible": eligible,
        "active_version": str(version),
        "strategy": (
            "starter-neutral" if manifest.strategy.value == "starter" else manifest.strategy.value
        ),
        "new_local_evidence_count": len(new_hashes),
        "unconsolidated_active_learning_count": learning_count,
        "recommendation": (
            "Plan an incremental voice upgrade" if eligible else "No material local change detected"
        ),
        "command": ["voice", "upgrade-plan", voice_id, "--mode", "incremental"],
    }


def _local_evidence_hashes(root: Path, voice_id: str) -> set[str]:
    """Return canonical hashes for locally available authorised evidence.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.

    Returns:
        set[str]: Canonical normalized content hashes.
    """
    hashes = set()
    order_path = root / "profiles" / voice_id / "work-order.json"
    if order_path.is_file():
        order = VoiceWorkOrder.model_validate_json(order_path.read_text(encoding="utf-8"))
        for locator in order.documents:
            path = Path(locator)
            if path.is_file():
                _, _, text = read_source(locator)
                hashes.add(content_hash(text))
    receipts = root / "publication-receipts"
    for path in receipts.rglob("*.receipt.json"):
        receipt = json.loads(path.read_text(encoding="utf-8"))
        artifact = root / str(receipt.get("artifact_path", ""))
        if receipt.get("voice_id") == voice_id and artifact.is_file():
            _, _, text = read_source(str(artifact))
            hashes.add(content_hash(text))
    return hashes
