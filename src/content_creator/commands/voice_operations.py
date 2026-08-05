"""Lifecycle, assessment, learning, and inspection handlers for voices."""

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
from ..voices import VoiceManifest, hash_file, load_voice_onboarding
from .shared import print_json
from .voice_context import VoiceCommandContext
from .voice_sources import documents, source_lines

VoiceHandler = Callable[[VoiceCommandContext], int]


def build(context: VoiceCommandContext) -> int:
    """Build voice operations."""
    print_json(context.builder.build(context.arguments.voice_id))
    return 0


def list_voices(context: VoiceCommandContext) -> int:
    """List voices."""
    print_json(context.registry.list())
    return 0


def _verify_voice(context: VoiceCommandContext, voice_id: str) -> dict[str, object]:
    """Verify voice."""
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
    """Verify all."""
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
    """Approve voice operations."""
    arguments = context.arguments
    if arguments.override_evaluation and not arguments.reason:
        raise ValueError("--override-evaluation requires --reason")
    override_reason = arguments.reason if arguments.override_evaluation else None
    print_json(
        context.registry.activate(arguments.voice_id, arguments.approved_by, override_reason)
    )
    return 0


def deactivate(context: VoiceCommandContext) -> int:
    """Deactivate voice operations."""
    print_json(context.registry.deactivate(context.arguments.voice_id, context.arguments.reason))
    return 0


def reactivate(context: VoiceCommandContext) -> int:
    """Return the reactivate."""
    arguments = context.arguments
    print_json(context.registry.activate(arguments.voice_id, arguments.approved_by, "reactivation"))
    return 0


def add_sources(context: VoiceCommandContext) -> int:
    """Add sources."""
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
    """Return the consolidate learnings."""
    path = LearningMemory(context.root, context.arguments.voice_id).consolidate_candidate()
    print_json(
        {
            "voice_id": context.arguments.voice_id,
            "status": "candidate",
            "path": str(path.relative_to(context.root)),
        }
    )
    return 0


def assess(context: VoiceCommandContext) -> int:
    """Assess voice operations."""
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
    """Return the configure score."""
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
    """Train model."""
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
    """Return the profile lines."""
    voice_root = context.root / "profiles" / context.arguments.voice_id
    directory = (
        voice_root / "candidate" if version == "candidate" else voice_root / "versions" / version
    )
    return (directory / "profile.md").read_text(encoding="utf-8").splitlines()


def show_diff(context: VoiceCommandContext) -> int:
    """Show diff."""
    arguments = context.arguments
    print(
        "\n".join(
            difflib.unified_diff(
                _profile_lines(context, arguments.from_version),
                _profile_lines(context, arguments.to_version),
                fromfile=arguments.from_version,
                tofile=arguments.to_version,
                lineterm="",
            )
        )
    )
    return 0


def show_status(context: VoiceCommandContext) -> int:
    """Show status."""
    voice_id = context.arguments.voice_id
    manifest_path = context.root / "profiles" / voice_id / "candidate" / "manifest.json"
    onboarding = load_voice_onboarding(context.root, voice_id)
    candidate_status = (
        VoiceManifest.model_validate_json(manifest_path.read_text()).status.value
        if manifest_path.exists()
        else None
    )
    print_json(
        {
            "voice_id": voice_id,
            "onboarding": onboarding.model_dump(mode="json") if onboarding else None,
            "candidate": candidate_status,
            "active": context.registry.list().get(voice_id),
            "statistical_voice_score": load_score_preference(context.root, voice_id),
        }
    )
    return 0


def _profile_directory(context: VoiceCommandContext) -> Path:
    """Return the profile directory."""
    candidate = context.root / "profiles" / context.arguments.voice_id / "candidate"
    if candidate.exists():
        return candidate
    resolved = context.registry.resolve(context.arguments.voice_id)
    return context.root / resolved["path"]


def show_profile(context: VoiceCommandContext) -> int:
    """Show profile."""
    print((_profile_directory(context) / "profile.md").read_text(encoding="utf-8"))
    return 0


def show_signature(context: VoiceCommandContext) -> int:
    """Show signature."""
    signature = (_profile_directory(context) / "linguistic-signature.json").read_text(
        encoding="utf-8"
    )
    print_json(json.loads(signature))
    return 0


def verify(context: VoiceCommandContext) -> int:
    """Verify voice operations."""
    report = _verify_voice(context, context.arguments.voice_id)
    print_json(report)
    return 0 if report["valid"] else 6
