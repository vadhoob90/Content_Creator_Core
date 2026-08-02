"""Onboard and create source-derived or starter voices."""

from __future__ import annotations

from datetime import UTC, datetime

from ..voice_assessment import save_score_preference
from ..voices import (
    Authorisation,
    VoiceOnboardingRecord,
    VoiceStrategy,
    VoiceWorkOrder,
    save_voice_onboarding,
    voice_id_for,
)
from .shared import print_json
from .voice_context import VoiceCommandContext
from .voice_sources import documents, source_lines


def _score_method(selected_method: str) -> str:
    return "deterministic" if selected_method == "disabled" else selected_method


def _activate_starter(context: VoiceCommandContext, voice_id: str, display_name: str) -> int:
    arguments = context.arguments
    if arguments.statistical_voice_score != "disabled":
        raise ValueError(
            "Starter voices cannot use statistical voice scoring because "
            "they have no author evidence"
        )
    intended_uses = arguments.use or ["general-text"]
    resolved = context.registry.activate_starter(
        voice_id=voice_id,
        display_name=display_name,
        author_name=arguments.author_name,
        selected_by=arguments.selected_by,
        intended_uses=intended_uses,
    )
    score_preference = save_score_preference(
        context.root,
        voice_id,
        enabled=False,
        method="deterministic",
        selected_by=arguments.selected_by,
    )
    print_json(
        {
            "status": "starter-active",
            "voice": resolved,
            "perspective_mode": "disabled",
            "statistical_voice_score": score_preference,
            "perspective_disabled_reason": "starter-voice-without-author-evidence",
            "next_step": (
                f"Create content with --voice {voice_id}. Re-run voice onboard "
                "with --strategy source-derived when author evidence is available."
            ),
        }
    )
    return 0


def _stage_source_derived(
    context: VoiceCommandContext,
    voice_id: str,
    display_name: str,
) -> int:
    arguments = context.arguments
    intended_uses = arguments.use or ["general-text"]
    order = VoiceWorkOrder(
        display_name=display_name,
        voice_id=voice_id,
        author_name=arguments.author_name,
        authorisation=Authorisation(
            confirmed=True,
            attested_by=arguments.selected_by,
            intended_uses=intended_uses,
        ),
        strategy=VoiceStrategy.SOURCE_DERIVED,
    )
    context.builder.save_work_order(order)
    record = VoiceOnboardingRecord(
        voice_id=voice_id,
        display_name=display_name,
        author_name=arguments.author_name,
        status="collecting-sources",
        strategy=VoiceStrategy.SOURCE_DERIVED,
        selected_by=arguments.selected_by,
        selected_at=datetime.now(UTC).isoformat(),
        perspective_mode="pending-source-derived-activation",
    )
    save_voice_onboarding(context.root, record)
    score_preference = save_score_preference(
        context.root,
        voice_id,
        enabled=arguments.statistical_voice_score != "disabled",
        method=_score_method(arguments.statistical_voice_score),
        selected_by=arguments.selected_by,
    )
    print_json(
        {
            "status": record.status,
            "voice_id": voice_id,
            "strategy": record.strategy,
            "perspective_mode": record.perspective_mode,
            "statistical_voice_score": score_preference,
            "next_steps": [
                "Add authorised writing with voice add-sources.",
                "Build, review, verify, and approve the candidate voice.",
            ],
        }
    )
    return 0


def onboard(context: VoiceCommandContext) -> int:
    arguments = context.arguments
    voice_id = voice_id_for(arguments.voice_id)
    if voice_id != arguments.voice_id:
        raise ValueError("voice_id must already be a repository-safe slug")
    display_name = arguments.label or f"{arguments.author_name} — General"
    if arguments.strategy == VoiceStrategy.STARTER.value:
        return _activate_starter(context, voice_id, display_name)
    return _stage_source_derived(context, voice_id, display_name)


def create(context: VoiceCommandContext) -> int:
    arguments = context.arguments
    author_name = arguments.author_name or arguments.name
    if not author_name:
        raise ValueError("--author-name is required (or use legacy --name)")
    display_name = arguments.label or arguments.name or author_name
    voice_id = voice_id_for(arguments.voice_id or display_name)
    if arguments.voice_id and voice_id != arguments.voice_id:
        raise ValueError("--voice-id must already be a repository-safe slug")
    order = VoiceWorkOrder(
        display_name=display_name,
        voice_id=voice_id,
        author_name=author_name,
        author_aliases=arguments.author_alias,
        authorisation=Authorisation(
            confirmed=bool(arguments.authorised_by),
            attested_by=arguments.authorised_by,
            intended_uses=arguments.use or ["general-text"],
        ),
        urls=source_lines(arguments.sources),
        documents=documents(arguments.documents),
        strategy=VoiceStrategy.SOURCE_DERIVED,
    )
    context.builder.save_work_order(order)
    _record_created_voice(context, order)
    print_json(order if arguments.no_build else context.builder.build(voice_id))
    return 0


def _record_created_voice(context: VoiceCommandContext, order: VoiceWorkOrder) -> None:
    arguments = context.arguments
    save_voice_onboarding(
        context.root,
        VoiceOnboardingRecord(
            voice_id=order.voice_id,
            display_name=order.display_name,
            author_name=order.author_name,
            status="collecting-sources",
            strategy=VoiceStrategy.SOURCE_DERIVED,
            selected_by=arguments.authorised_by,
            selected_at=datetime.now(UTC).isoformat(),
            perspective_mode="pending-source-derived-activation",
        ),
    )
    save_score_preference(
        context.root,
        order.voice_id,
        enabled=arguments.statistical_voice_score != "disabled",
        method=_score_method(arguments.statistical_voice_score),
        selected_by=arguments.authorised_by,
    )
