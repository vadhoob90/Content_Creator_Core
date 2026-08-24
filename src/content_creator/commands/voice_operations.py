"""Implement the voice operations command family."""

from __future__ import annotations

import difflib
import json
from pathlib import Path
from typing import Callable

from ..configuration import Configuration
from ..learning import LearningMemory
from ..storage import StorageError
from ..voice_assessment import (
    assess_voice_draft,
    load_score_preference,
    save_score_preference,
)
from ..voice_ml import train_voice_ml_model
from ..voice_rejection import candidate_decision, list_rejections
from ..voice_upgrade.models import VoiceUpgradeMode, VoiceUpgradePlan, VoiceUpgradeState
from ..voice_upgrade.service import VoiceUpgradeError, VoiceUpgradeService
from ..voice_upgrade.state import record_upgrade_decision
from ..voices import VoiceManifest, hash_file, load_voice_onboarding
from .shared import print_json
from .voice_context import VoiceCommandContext
from .voice_sources import documents, source_lines
from .voice_status_rendering import render_voice_status

VoiceHandler = Callable[[VoiceCommandContext], int]


def build(context: VoiceCommandContext) -> int:
    """Build the voice operations workflow.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The constructed numeric value for value.
    """
    change_set = getattr(context.arguments, "change_set", None)
    print_json(
        context.builder.build(
            context.arguments.voice_id,
            full_regenerate=getattr(context.arguments, "full_regenerate", False),
            change_set=Path(change_set) if change_set else None,
        )
    )
    return 0


def list_voices(context: VoiceCommandContext) -> int:
    """List the voices.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The available numeric value for voices.
    """
    print_json(context.registry.list())
    return 0


def _verify_voice(context: VoiceCommandContext, voice_id: str) -> dict[str, object]:
    """Verify the voice.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.
        voice_id (str): The stable identifier for the selected voice.

    Returns:
        dict[str, object]: The structured verified data for voice.
    """
    directory = context.root / "profiles" / voice_id / "candidate"
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        resolved = context.registry.resolve(voice_id)
        directory = context.root / resolved["path"]
        manifest_path = directory / "manifest.json"
    manifest = VoiceManifest.model_validate_json(manifest_path.read_text())
    mismatches = [
        component_name
        for component_name, filename in manifest.components.items()
        if not (directory / filename).exists()
        or hash_file(directory / filename) != manifest.component_hashes[component_name]
    ]
    return {"voice_id": voice_id, "valid": not mismatches, "mismatches": mismatches}


def verify_all(context: VoiceCommandContext) -> int:
    """Verify the all.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The verified numeric value for all.
    """
    voice_ids = set(context.registry.list())
    voice_ids.update(
        path.parent.parent.name
        for path in (context.root / "profiles").glob("*/candidate/manifest.json")
    )
    reports = [_verify_voice(context, voice_id) for voice_id in sorted(voice_ids)]
    valid = all(report["valid"] for report in reports)
    print_json({"valid": valid, "voices": reports})
    return 0 if valid else 6


def approve(context: VoiceCommandContext) -> int:
    """Approve the voice operations workflow.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for approve.

    Raises:
        ValueError: If an input value violates the supported domain constraints.
    """
    arguments = context.arguments
    if arguments.override_evaluation and not arguments.reason:
        raise ValueError("--override-evaluation requires --reason")
    override_reason = arguments.reason if arguments.override_evaluation else None
    print_json(
        context.registry.activate(arguments.voice_id, arguments.approved_by, override_reason)
    )
    return 0


def deactivate(context: VoiceCommandContext) -> int:
    """Deactivate the voice operations workflow.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for deactivate.
    """
    arguments = context.arguments
    print_json(
        context.registry.deactivate(
            arguments.voice_id,
            arguments.reason,
            arguments.deactivated_by,
            clear_default=arguments.clear_default,
            replacement_voice=arguments.replacement_voice,
        )
    )
    return 0


def reject(context: VoiceCommandContext) -> int:
    """Reject the exact candidate reviewed by an author.

    Args:
        context (VoiceCommandContext): Voice command dependencies and arguments.

    Returns:
        int: Zero after the rejection receipt is persisted or found.
    """
    arguments = context.arguments
    receipt = context.registry.reject(
        arguments.voice_id,
        arguments.candidate_hash,
        arguments.rejected_by,
        arguments.reason,
    )
    record_upgrade_decision(
        context.root,
        arguments.voice_id,
        arguments.candidate_hash,
        VoiceUpgradeState.REJECTED,
        receipt.snapshot_path + "/rejection-receipt.json",
    )
    print_json(receipt)
    return 0


def reactivate(context: VoiceCommandContext) -> int:
    """Return the reactivate.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for reactivate.
    """
    arguments = context.arguments
    print_json(
        context.registry.reactivate(arguments.voice_id, arguments.approved_by, arguments.reason)
    )
    return 0


def retirement_plan(context: VoiceCommandContext) -> int:
    """Render persisted-state retirement effects without changing the workspace.

    Args:
        context (VoiceCommandContext): The resolved voice command context.

    Returns:
        int: Zero after printing the retirement preflight.
    """
    print_json(context.registry.retirement_plan(context.arguments.voice_id))
    return 0


def retire_voice(context: VoiceCommandContext) -> int:
    """Retire a voice using one exact reviewed plan.

    Args:
        context (VoiceCommandContext): The resolved voice command context.

    Returns:
        int: Zero after persisting the retirement decision.
    """
    arguments = context.arguments
    print_json(
        context.registry.retire(
            arguments.voice_id,
            arguments.retired_by,
            arguments.reason,
            arguments.plan_hash,
            clear_default=arguments.clear_default,
            replacement_voice=arguments.replacement_voice,
            candidate_disposition=arguments.candidate_disposition,
            perspective_candidate_disposition=arguments.perspective_candidate_disposition,
            proposal_disposition=arguments.proposal_disposition,
            run_disposition=arguments.run_disposition,
        )
    )
    return 0


def restore_voice(context: VoiceCommandContext) -> int:
    """Restore a retired voice after an explicit hash-bound review.

    Args:
        context (VoiceCommandContext): The resolved voice command context.

    Returns:
        int: Zero after persisting the reviewed restoration.
    """
    arguments = context.arguments
    print_json(
        context.registry.restore(
            arguments.voice_id,
            arguments.requested_by,
            arguments.approved_by,
            arguments.plan_hash,
        )
    )
    return 0


def verify_lifecycle(context: VoiceCommandContext) -> int:
    """Verify lifecycle receipts and catalogue hashes offline.

    Args:
        context (VoiceCommandContext): The resolved voice command context.

    Returns:
        int: Zero for valid evidence or six for verification failures.
    """
    result = context.registry.verify_lifecycle(context.arguments.voice_id)
    print_json(result)
    return 0 if result["valid"] else 6


def migrate_lifecycle(context: VoiceCommandContext) -> int:
    """Create an explicitly legacy-labelled receipt for registry-only inactivity.

    Args:
        context (VoiceCommandContext): The resolved voice command context.

    Returns:
        int: Zero after persisting the migration receipt.
    """
    print_json(
        context.registry.migrate_legacy_lifecycle(
            context.arguments.voice_id, context.arguments.migrated_by
        )
    )
    return 0


def add_sources(context: VoiceCommandContext) -> int:
    """Add the sources.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for add sources.
    """
    arguments = context.arguments
    order = context.builder.load_work_order(arguments.voice_id)
    order.urls.extend(
        source for source in source_lines(arguments.sources) if source not in order.urls
    )
    order.documents.extend(
        document for document in documents(arguments.documents) if document not in order.documents
    )
    context.builder.save_work_order(order)
    print_json(order)
    return 0


def consolidate_learnings(context: VoiceCommandContext) -> int:
    """Return the consolidate learnings.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for consolidate learnings.
    """
    active_version = context.registry.get(context.arguments.voice_id).get("active_version")
    path = LearningMemory(
        context.root,
        context.arguments.voice_id,
        active_version,
    ).consolidate_candidate()
    print_json(
        {
            "voice_id": context.arguments.voice_id,
            "status": "candidate",
            "path": str(path.relative_to(context.root)),
        }
    )
    return 0


def upgrade_plan(context: VoiceCommandContext) -> int:
    """Persist and render a read-only governed voice-upgrade inventory.

    Args:
        context (VoiceCommandContext): Voice command dependencies and arguments.

    Returns:
        int: Zero after the plan and review template are persisted.
    """
    arguments = context.arguments
    plan = VoiceUpgradeService(context.root, context.builder).plan(
        arguments.voice_id,
        VoiceUpgradeMode(arguments.mode),
        provider=arguments.provider,
        offline_analysis=arguments.offline_analysis,
    )
    print_json(plan)
    return 0


def upgrade(context: VoiceCommandContext) -> int:
    """Build a candidate from a fresh plan and explicit learning dispositions.

    Args:
        context (VoiceCommandContext): Voice command dependencies and arguments.

    Returns:
        int: Zero after a candidate is built or an equivalent retry is returned.

    Raises:
        VoiceUpgradeError: If the requested mode differs from the persisted plan.
    """
    arguments = context.arguments
    plan_path = (
        context.root / "profiles" / arguments.voice_id / "upgrade" / "voice-upgrade-plan.json"
    )
    plan = VoiceUpgradePlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    if plan.mode != VoiceUpgradeMode(arguments.mode):
        raise VoiceUpgradeError("Requested mode does not match the persisted upgrade plan")
    planned_offline = plan.execution_mode == "offline-deterministic"
    if planned_offline != arguments.offline_analysis:
        raise VoiceUpgradeError("Requested execution mode does not match the persisted plan")
    if plan.provider != arguments.provider:
        raise VoiceUpgradeError("Requested provider does not match the persisted upgrade plan")
    selection = Path(arguments.learning_selection) if arguments.learning_selection else None
    change_set = Path(arguments.change_set) if arguments.change_set else None
    if selection and not selection.is_absolute():
        selection = context.root / selection
    if change_set and not change_set.is_absolute():
        change_set = context.root / change_set
    print_json(
        VoiceUpgradeService(context.root, context.builder).build(
            arguments.voice_id,
            selection,
            idempotency_key=arguments.idempotency_key,
            provider_sharing_approved=arguments.approve_provider_sharing,
            explicit_change_set=change_set,
        )
    )
    return 0


def assess(context: VoiceCommandContext) -> int:
    """Assess the voice operations workflow.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The assessment numeric value for value.

    Raises:
        StorageError: If the storage operation cannot complete.
    """
    arguments = context.arguments
    draft_path = Path(arguments.draft).expanduser()
    if not draft_path.is_absolute():
        draft_path = context.root / draft_path
    if not draft_path.is_file():
        raise StorageError(f"Draft does not exist: {draft_path}")
    policy = Configuration(context.root).statistical_voice_score_policy
    policy["method"] = "deterministic" if arguments.voice_command == "assess" else arguments.method
    print_json(
        assess_voice_draft(
            context.root,
            arguments.voice_id,
            arguments.voice_version,
            draft_path.read_text(encoding="utf-8"),
            policy,
        )
    )
    return 0


def configure_score(context: VoiceCommandContext) -> int:
    """Return the configure score.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for configure score.

    Raises:
        StorageError: If the storage operation cannot complete.
    """
    arguments = context.arguments
    if not (context.root / "profiles" / arguments.voice_id).is_dir():
        raise StorageError(f"Unknown voice: {arguments.voice_id}")
    existing_preference = load_score_preference(context.root, arguments.voice_id) or {}
    preference = save_score_preference(
        context.root,
        arguments.voice_id,
        enabled=arguments.enable,
        method=arguments.method or existing_preference.get("method", "deterministic"),
        selected_by=arguments.selected_by,
    )
    print_json(preference)
    return 0


def train_model(context: VoiceCommandContext) -> int:
    """Train the model.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The trained numeric value for model.
    """
    arguments = context.arguments
    training_result = train_voice_ml_model(
        context.root,
        arguments.voice_id,
        arguments.voice_version,
        [Path(document) for document in documents(arguments.comparison_documents)],
        accept_low_confidence=arguments.accept_low_confidence,
        replace=arguments.replace,
    )
    print_json(training_result)
    return 0 if training_result["trained"] else 5


def _profile_lines(context: VoiceCommandContext, version: str) -> list[str]:
    """Return the profile lines.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.
        version (str): The immutable artifact or schema version identifier.

    Returns:
        list[str]: The resulting profile lines values in their documented order.
    """
    voice_root = context.root / "profiles" / context.arguments.voice_id
    if version == "active":
        version = context.registry.get(context.arguments.voice_id)["active_version"]
    directory = (
        voice_root / "candidate" if version == "candidate" else voice_root / "versions" / version
    )
    return (directory / "profile.md").read_text(encoding="utf-8").splitlines()


def show_diff(context: VoiceCommandContext) -> int:
    """Show the diff.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for show diff.
    """
    arguments = context.arguments
    profile_diff = list(
        difflib.unified_diff(
            _profile_lines(context, arguments.from_version),
            _profile_lines(context, arguments.to_version),
            fromfile=arguments.from_version,
            tofile=arguments.to_version,
            lineterm="",
        )
    )
    evolution_path = (
        context.root / "profiles" / arguments.voice_id / "candidate" / "voice-evolution.json"
    )
    delta = (
        json.loads(evolution_path.read_text(encoding="utf-8")) if evolution_path.is_file() else {}
    )
    semantic_baseline = {"active", str(delta.get("baseline_version"))}
    if (
        delta
        and arguments.to_version == "candidate"
        and arguments.from_version in semantic_baseline
    ):
        print_json(
            {
                "from": arguments.from_version,
                "to": arguments.to_version,
                "semantic_delta": delta,
                "profile_diff": profile_diff,
            }
        )
    else:
        print("\n".join(profile_diff))
    return 0


def show_status(context: VoiceCommandContext) -> int:
    """Show the status.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for show status.
    """
    voice_id = context.arguments.voice_id
    manifest_path = context.root / "profiles" / voice_id / "candidate" / "manifest.json"
    onboarding = load_voice_onboarding(context.root, voice_id)
    candidate_status = (
        VoiceManifest.model_validate_json(manifest_path.read_text()).status.value
        if manifest_path.exists()
        else None
    )
    active = context.registry.list().get(voice_id)
    result = {
        "voice_id": voice_id,
        "onboarding": onboarding.model_dump(mode="json") if onboarding else None,
        "candidate": candidate_status,
        "active": active,
        "candidate_decision": candidate_decision(context.root, voice_id, active),
        "rejections": list_rejections(context.root, voice_id),
        "statistical_voice_score": load_score_preference(context.root, voice_id),
    }
    print(render_voice_status(result)) if context.arguments.human else print_json(result)
    return 0


def _profile_directory(context: VoiceCommandContext) -> Path:
    """Return the profile directory.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        Path: The resolved filesystem path for profile directory.
    """
    candidate = context.root / "profiles" / context.arguments.voice_id / "candidate"
    if candidate.exists():
        return candidate
    resolved = context.registry.resolve(context.arguments.voice_id)
    return context.root / resolved["path"]


def show_profile(context: VoiceCommandContext) -> int:
    """Show the profile.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for show profile.
    """
    print((_profile_directory(context) / "profile.md").read_text(encoding="utf-8"))
    return 0


def show_signature(context: VoiceCommandContext) -> int:
    """Show the signature.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The resulting numeric value for show signature.
    """
    signature = (_profile_directory(context) / "linguistic-signature.json").read_text(
        encoding="utf-8"
    )
    print_json(json.loads(signature))
    return 0


def verify(context: VoiceCommandContext) -> int:
    """Verify the voice operations workflow.

    Args:
        context (VoiceCommandContext): The operation context and its resolved
            dependencies.

    Returns:
        int: The verified numeric value for value.
    """
    report = _verify_voice(context, context.arguments.voice_id)
    print_json(report)
    return 0 if report["valid"] else 6
