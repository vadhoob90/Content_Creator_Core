"""Update durable voice-upgrade state after deterministic candidate decisions."""

from __future__ import annotations

from pathlib import Path

from ..storage import RunStore
from .models import VoiceUpgradePlan, VoiceUpgradeState


def record_upgrade_decision(
    root: Path,
    voice_id: str,
    candidate_hash: str,
    state: VoiceUpgradeState,
    receipt_path: str,
) -> None:
    """Record activation or rejection only for the bound upgrade candidate.

    Args:
        root (Path): Workspace root.
        voice_id (str): Selected voice identifier.
        candidate_hash (str): Exact decided candidate hash.
        state (VoiceUpgradeState): Terminal durable workflow state.
        receipt_path (str): Workspace-relative decision receipt path.

    Returns:
        None: A matching upgrade plan is updated; unrelated candidates are ignored.
    """
    path = root / "profiles" / voice_id / "upgrade" / "voice-upgrade-plan.json"
    if not path.is_file():
        return
    plan = VoiceUpgradePlan.model_validate_json(path.read_text(encoding="utf-8"))
    if plan.candidate_hash != candidate_hash:
        return
    plan.state = state
    plan.decision_receipt = receipt_path
    RunStore._atomic_text(path, plan.model_dump_json(indent=2))
