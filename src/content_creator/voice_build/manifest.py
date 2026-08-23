"""Render candidate manifests and build reports from completed voice builds."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ..storage import RunStore
from ..versioned_artifacts import hash_file, hash_json
from ..voice_models import VoiceManifest, VoiceStatus, VoiceStrategy
from ..voice_upgrade.evidence import evidence_from_sources, evidence_set_hash
from ..voice_upgrade.models import EvidenceSet
from .models import BuildState


def write_voice_manifest(state: BuildState, evaluation: dict) -> VoiceManifest:
    """Write the complete hash-bound candidate manifest and build report.

    Persist the represented evidence baseline before hashing components, then attach
    governed upgrade metadata without changing the normal build contract.

    Args:
        state (BuildState): Completed voice build state.
        evaluation (dict): Standalone and regression evaluation result.

    Returns:
        VoiceManifest: Persisted candidate manifest.
    """
    evidence = _write_evidence_baseline(state)
    components = _components(state)
    component_hashes = {
        name: hash_file(state.candidate / filename) for name, filename in components.items()
    }
    candidate_hash = hash_json(component_hashes)
    manifest = VoiceManifest(
        id=state.order.voice_id,
        display_name=state.order.display_name,
        author_name=state.order.attribution_name,
        author_aliases=state.order.author_aliases,
        version="candidate",
        status=VoiceStatus.AWAITING_APPROVAL if evaluation["passed"] else VoiceStatus.BUILT,
        candidate_hash=candidate_hash,
        components=components,
        component_hashes=component_hashes,
        supported_packs=state.corpus["supported_packs"],
        authorisation=state.order.authorisation,
        strategy=VoiceStrategy.SOURCE_DERIVED,
        evidence_status="author-sources",
        perspectives_allowed=True,
        evolution_mode=state.evolution.mode,
        baseline_version=state.evolution.baseline_version,
        baseline_candidate_hash=state.evolution.baseline_candidate_hash,
        evolution_delta_hash=state.evolution.delta_hash,
        **_upgrade_fields(state, evaluation, evidence),
    )
    RunStore._atomic_text(state.candidate / "manifest.json", manifest.model_dump_json(indent=2))
    RunStore._atomic_text(
        state.candidate / "build-report.json",
        json.dumps(
            {
                "voice_id": state.order.voice_id,
                "candidate_hash": candidate_hash,
                "source_failures": state.errors,
                "status": manifest.status.value,
            },
            indent=2,
        ),
    )
    return manifest


def _components(state: BuildState) -> dict[str, str]:
    """Return candidate component names and filenames.

    Args:
        state (BuildState): Completed voice build state.

    Returns:
        dict[str, str]: Component map used for manifest hashing.
    """
    components = {
        "profile": "profile.md",
        "constraints": "constraints.json",
        "rubric": "voice-rubric.json",
        "sources": "source-index.json",
        "patterns": "patterns.json",
        "corpus": "corpus-report.json",
        "linguistic_signature": "linguistic-signature.json",
        "evaluation_report": "evaluation-report.json",
        "evidence_baseline": "evidence-baseline.json",
    }
    if state.evolution.delta is not None:
        components["evolution_delta"] = state.evolution.artifact_name
    if state.upgrade_context:
        components.update(
            {
                "voice_upgrade_plan": "voice-upgrade-plan.json",
                "evidence_baseline": "evidence-baseline.json",
                "evidence_delta": "evidence-delta.json",
                "learning_selection": "learning-selection.json",
                "learning_dispositions": "learning-dispositions.json",
            }
        )
    if state.analysis_artifact is not None:
        components["analyst_report"] = "analyst-report.json"
    if state.criticism_artifact is not None:
        components["critic_report"] = "critic-report.json"
    return components


def _upgrade_fields(state: BuildState, evaluation: dict, evidence: EvidenceSet) -> dict:
    """Return optional governed-upgrade manifest fields.

    Args:
        state (BuildState): Completed voice build state.
        evaluation (dict): Candidate evaluation result.
        evidence (EvidenceSet): Complete evidence represented by the candidate.

    Returns:
        dict: Upgrade metadata or an explicit strategy transition.
    """
    context = state.upgrade_context
    if context:
        return {
            "upgrade_state": "awaiting_approval" if evaluation["passed"] else "built",
            "upgrade_mode": context.plan.mode.value,
            "evidence_cutoff": evidence.evidence_cutoff,
            "evidence_baseline_hash": evidence_set_hash(evidence),
            "evidence_delta_hash": evidence_set_hash(context.evidence_delta),
            "learning_dispositions_hash": hash_file(state.candidate / "learning-dispositions.json"),
            "upgrade_build_fingerprint": context.build_fingerprint,
            "strategy_transition": context.plan.strategy_transition,
        }
    baseline = state.evolution.baseline
    transition = (
        "starter-neutral-to-source-derived"
        if baseline and baseline.strategy in {VoiceStrategy.STARTER, VoiceStrategy.STARTER_NEUTRAL}
        else None
    )
    return {
        "strategy_transition": transition,
        "evidence_cutoff": evidence.evidence_cutoff,
        "evidence_baseline_hash": evidence_set_hash(evidence),
    }


def _write_evidence_baseline(state: BuildState) -> EvidenceSet:
    """Persist the complete evidence set represented by the candidate.

    Args:
        state (BuildState): Completed voice build state.

    Returns:
        EvidenceSet: Candidate evidence baseline included in manifest hashing.
    """
    evidence = (
        state.upgrade_context.represented_evidence
        if state.upgrade_context
        else evidence_from_sources(
            state.order.voice_id,
            state.sources,
            _evidence_cutoff(state),
        )
    )
    RunStore._atomic_text(
        state.candidate / "evidence-baseline.json",
        evidence.model_dump_json(indent=2),
    )
    return evidence


def _evidence_cutoff(state: BuildState) -> str:
    """Return a stable cutoff from the authorised local evidence boundary.

    Args:
        state (BuildState): Completed voice build state.

    Returns:
        str: Latest work-order or local-source modification time in ISO-8601 form.
    """
    candidates = [state.voice_root / "work-order.json"]
    candidates.extend(Path(locator) for locator in state.order.documents)
    timestamps = [path.stat().st_mtime for path in candidates if path.is_file()]
    timestamp = max(timestamps) if timestamps else 0
    return datetime.fromtimestamp(timestamp, tz=UTC).isoformat()
