"""Build read-only voice retirement inventories from persisted Core state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .lifecycle_models import LifecyclePlan, LifecycleReceipt
from .lifecycle_support import default_voice, utc_timestamp
from .versioned_artifacts import hash_file, hash_json
from .voice_models import VoiceError, VoiceManifest, VoiceStatus
from .voice_upgrade.epochs import epoch_hash, load_epoch


def _candidate(root: Path, voice_id: str) -> list[dict[str, Any]]:
    """Return the pending voice candidate and any exact-hash decision.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.

    Returns:
        list[dict[str, Any]]: Empty or single-item candidate inventory.
    """
    from .voice_rejection import candidate_decision

    path = root / "profiles" / voice_id / "candidate" / "manifest.json"
    if not path.exists():
        return []
    manifest = VoiceManifest.model_validate_json(path.read_text(encoding="utf-8"))
    decision = candidate_decision(root, voice_id)
    lifecycle_decision = (
        root
        / "profiles"
        / voice_id
        / "lifecycle"
        / "candidate-decisions"
        / f"voice-candidate-{manifest.candidate_hash.removeprefix('sha256:')}.json"
    )
    lifecycle_action = None
    if lifecycle_decision.exists():
        lifecycle_action = (
            LifecycleReceipt.model_validate_json(lifecycle_decision.read_text(encoding="utf-8"))
            .candidate_dispositions[0]
            .action
        )
    return [
        {
            "kind": "voice-candidate",
            "id": voice_id,
            "status": manifest.status.value,
            "candidate_hash": manifest.candidate_hash,
            "manifest_hash": hash_file(path),
            "decision": lifecycle_action or decision.get("status"),
            "decision_receipt": decision.get("rejection_receipt"),
        }
    ]


def _perspective_inventory(root: Path, voice_id: str) -> tuple[list[dict], list[dict], list[dict]]:
    """Return owned context, candidate, and proposal inventories.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.

    Returns:
        tuple[list[dict], list[dict], list[dict]]: Contexts, candidates, and proposals.
    """
    base = root / "profiles" / voice_id / "perspectives"
    registry_path = base / "registry.json"
    registry = (
        json.loads(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    )
    contexts = [
        {"context_id": context_id, **item}
        for context_id, item in sorted((registry.get("contexts") or {}).items())
    ]
    candidates = []
    proposals = []
    for path in sorted(base.glob("*/candidate/manifest.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        context_id = path.parents[1].name
        selected = (registry.get("contexts") or {}).get(context_id, {})
        if data.get("candidate_hash") == selected.get("candidate_hash"):
            continue
        candidates.append(
            {
                "context_id": context_id,
                "candidate_hash": data.get("candidate_hash"),
                "manifest_hash": hash_file(path),
                "status": data.get("status"),
            }
        )
    for path in sorted(base.glob("*/proposals/*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("status") in {"candidate", "staged"}:
            proposals.append(
                {
                    "context_id": path.parents[1].name,
                    "proposal_id": data.get("id", path.stem),
                    "status": data.get("status"),
                    "hash": hash_file(path),
                }
            )
    return contexts, candidates, proposals


def _read_json(path: Path) -> Optional[dict[str, Any]]:
    """Return a JSON mapping or ``None`` for unreadable historical inventory.

    Args:
        path (Path): JSON artifact path.

    Returns:
        Optional[dict[str, Any]]: Parsed mapping, or ``None`` when unreadable.
    """
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _run_inventory(root: Path, voice_id: str) -> list[dict[str, Any]]:
    """Return exact run states that selected the voice.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.

    Returns:
        list[dict[str, Any]]: Matching run status and publishability records.
    """
    result = []
    terminal = {"published", "failed", "abandoned"}
    for path in sorted((root / "runs").glob("*/state.json")):
        state = _read_json(path)
        if state is None:
            continue
        order = state.get("work_order") or {}
        if order.get("voice_id") != voice_id:
            continue
        status = str(state.get("status", "unknown"))
        result.append(
            {
                "run_id": path.parent.name,
                "status": status,
                "voice_version": order.get("voice_version"),
                "incomplete": status not in terminal,
                "publishable": status in {"ready", "needs_author"},
            }
        )
    return result


def _publications(root: Path, runs: list[dict[str, Any]]) -> dict[str, Any]:
    """Return historical publication evidence associated with selected runs.

    Args:
        root (Path): Workspace root directory.
        runs (list[dict[str, Any]]): Voice-associated run inventory.

    Returns:
        dict[str, Any]: Historical receipt count and destination directories.
    """
    run_ids = {item["run_id"] for item in runs}
    receipt_count = 0
    destinations = set()
    for path in sorted((root / "publication-receipts").glob("*.json")):
        receipt = _read_json(path)
        if receipt is None or receipt.get("run_id") not in run_ids:
            continue
        receipt_count += 1
        destination = receipt.get("artifact_path") or receipt.get("published_path")
        if destination:
            destinations.add(str(Path(destination).parent))
    return {"destinations": sorted(destinations), "historical_receipt_count": receipt_count}


def retirement_plan(registry: Any, voice_id: str) -> LifecyclePlan:
    """Build a read-only plan exclusively from persisted Core state.

    Inventory selected version evidence, learning, pending work, owned contexts,
    historical runs, publications, and associated model/cache artifacts.

    Args:
        registry (Any): Voice registry providing persisted-state access.
        voice_id (str): Stable selected voice identifier.

    Returns:
        LifecyclePlan: Hash-bound aggregate retirement preflight.

    Raises:
        VoiceError: If the voice has no selected immutable version.
    """
    root = registry.root.resolve()
    item = registry.get(voice_id)
    version = item.get("active_version")
    if not version:
        raise VoiceError(f"Voice {voice_id} has no selected version")
    resolved = registry.resolve(voice_id, version, allow_inactive=True)
    epoch = load_epoch(root, voice_id, version, migrate_legacy=False)
    contexts, perspective_candidates, proposals = _perspective_inventory(root, voice_id)
    candidates = [
        candidate
        for candidate in _candidate(root, voice_id)
        if candidate["candidate_hash"] != item.get("candidate_hash")
    ]
    runs = _run_inventory(root, voice_id)
    required = _required_decisions(
        root, voice_id, candidates, perspective_candidates, proposals, runs
    )
    associated: list[str] = []
    for pattern in (
        f"profiles/{voice_id}/versions/{version}/**/*",
        f".voice-cache/{voice_id}/**/*",
        f"profiles/{voice_id}/**/*model*",
    ):
        associated.extend(
            str(path.relative_to(root)) for path in root.glob(pattern) if path.is_file()
        )
    plan = LifecyclePlan(
        object_type="voice",
        object_id=voice_id,
        generated_at=utc_timestamp(),
        current_status=str(item.get("status")),
        selected_version=version,
        selected_manifest_hash=resolved.get("manifest_hash"),
        strategy=resolved.get("strategy"),
        is_default=default_voice(root) == voice_id,
        learning_epoch={
            "epoch_id": epoch.epoch_id,
            "status": epoch.status,
            "hash": epoch_hash(epoch),
            "record_count": len(epoch.records),
            "active_record_count": sum(
                record.get("status") == "active" for record in epoch.records
            ),
        },
        candidates=candidates,
        perspective_contexts=contexts,
        perspective_candidates=perspective_candidates,
        perspective_proposals=proposals,
        runs=runs,
        publications=_publications(root, runs),
        associated_artifacts=sorted(set(associated)),
        effects=_effects(),
        required_decisions=required,
        valid_next_actions=_valid_actions(str(item.get("status"))),
    )
    plan.binding_hash = hash_json(
        plan.model_dump(mode="json", exclude={"generated_at", "binding_hash"})
    )
    return plan


def _required_decisions(
    root: Path,
    voice_id: str,
    candidates: list[dict],
    perspective_candidates: list[dict],
    proposals: list[dict],
    runs: list[dict],
) -> list[str]:
    """Return explicit decisions required by the current aggregate inventory.

    Args:
        root (Path): Workspace root directory.
        voice_id (str): Stable selected voice identifier.
        candidates (list[dict]): Pending voice candidate inventory.
        perspective_candidates (list[dict]): Pending perspective candidates.
        proposals (list[dict]): Pending perspective proposals.
        runs (list[dict]): Voice-associated run inventory.

    Returns:
        list[str]: Human-readable required retirement decisions.
    """
    required = []
    if default_voice(root) == voice_id:
        required.append("clear or replace the configured default voice")
    if any(candidate.get("decision") == "pending" for candidate in candidates):
        required.append("choose an exact-hash disposition for the pending voice candidate")
    if perspective_candidates:
        required.append("choose exact-hash dispositions for pending perspective candidates")
    if proposals:
        required.append("choose dispositions for pending perspective proposals")
    if any(item["incomplete"] for item in runs):
        required.append("complete or abandon each incomplete run before retirement")
    return required


def _effects() -> dict[str, list[str]]:
    """Return author-visible effects for every aggregate lifecycle action.

    Returns:
        dict[str, list[str]]: Action-to-effect descriptions.
    """
    return {
        "deactivate": [
            "block new unpinned runs and automatic/default resolution",
            "freeze the current learning epoch and preserve all history",
            "preserve candidates and owned perspectives unchanged",
        ],
        "retire": [
            "block new runs, revisions, publication, learning, upgrades, and activation",
            "freeze and hash learning while preserving versions, runs, and publications",
            "make owned perspectives inaccessible without silently changing their states",
            "leave installed content packs and repository-wide learning unchanged",
        ],
        "reactivate": [
            "verify and reselect the unchanged immutable version",
            "open a new activation learning epoch without creating a voice version",
        ],
        "restore": [
            "require a hash-bound plan and explicit reviewer approval",
            "verify preserved artifacts and open a fresh learning epoch",
        ],
    }


def _valid_actions(status: str) -> list[str]:
    """Return lifecycle actions valid for one persisted voice status.

    Args:
        status (str): Persisted voice status.

    Returns:
        list[str]: Valid next lifecycle action identifiers.
    """
    if status == VoiceStatus.ACTIVE.value:
        return ["deactivate", "retire", "upgrade", "inspect-history"]
    if status == VoiceStatus.INACTIVE.value:
        return ["reactivate", "retire", "inspect-history"]
    if status == VoiceStatus.RETIRED.value:
        return ["restore-plan", "inspect-history", "verify"]
    return ["inspect-history", "verify"]
