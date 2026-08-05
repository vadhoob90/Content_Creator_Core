"""Focused comparison, catalogue, lifecycle, and proposal operations."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..perspective_assessment import create_blind_comparison, record_blind_comparison
from ..perspectives import (
    PerspectiveCatalogueStore,
    PerspectiveEntry,
    PerspectiveManifest,
    PerspectiveProposalStore,
    PerspectiveProvenance,
    PerspectiveRegistry,
)
from ..voices import hash_file
from .shared import print_json


@dataclass(frozen=True)
class PerspectiveCommandContext:
    """Represent a perspective command context."""

    root: Path
    arguments: argparse.Namespace
    registry: PerspectiveRegistry | None = None


PerspectiveHandler = Callable[[PerspectiveCommandContext], int]


def create_comparison(context: PerspectiveCommandContext) -> int:
    """Create comparison."""
    baseline = Path(context.arguments.baseline)
    if not baseline.is_absolute():
        baseline = context.root / baseline
    print_json(create_blind_comparison(context.root, context.arguments.run, baseline))
    return 0


def record_comparison(context: PerspectiveCommandContext) -> int:
    """Record comparison."""
    assessment = Path(context.arguments.assessment)
    if not assessment.is_absolute():
        assessment = context.root / assessment
    print_json(record_blind_comparison(context.root, context.arguments.run, assessment))
    return 0


def _registry(context: PerspectiveCommandContext) -> PerspectiveRegistry:
    """Return the registry."""
    if context.registry is None:
        raise RuntimeError("Perspective registry is required for this command")
    return context.registry


def show_catalogue(context: PerspectiveCommandContext) -> int:
    """Show catalogue."""
    catalogue = PerspectiveCatalogueStore(context.root, context.arguments.voice).load()
    print_json(catalogue.model_dump(mode="json"))
    return 0


def verify_catalogue(context: PerspectiveCommandContext) -> int:
    """Verify catalogue."""
    result = PerspectiveCatalogueStore(context.root, context.arguments.voice).verify()
    print_json(result)
    return 0 if result["valid"] else 6


def create(context: PerspectiveCommandContext) -> int:
    """Create perspective operations."""
    arguments = context.arguments
    entries = []
    if arguments.statement:
        if not arguments.evidence:
            raise ValueError("--evidence is required when creating a perspective statement")
        entries.append(
            PerspectiveEntry(
                type=arguments.type,
                statement=arguments.statement,
                topics=arguments.topic,
                qualifications=arguments.qualification,
                counterpositions=arguments.counterposition,
                provenance=[
                    PerspectiveProvenance(
                        kind="direct_author_input",
                        reference=arguments.evidence,
                    )
                ],
            )
        )
    print_json(
        _registry(context).stage(
            arguments.context,
            entries,
            display_name=arguments.display_name,
        )
    )
    return 0


def list_perspectives(context: PerspectiveCommandContext) -> int:
    """List perspectives."""
    print_json(_registry(context).list())
    return 0


def _candidate(context: PerspectiveCommandContext) -> Path:
    """Return the candidate."""
    return _registry(context).context_root(context.arguments.context) / "candidate"


def show_status(context: PerspectiveCommandContext) -> int:
    """Show status."""
    manifest_path = _candidate(context) / "manifest.json"
    manifest = (
        PerspectiveManifest.model_validate_json(manifest_path.read_text())
        if manifest_path.exists()
        else None
    )
    print_json(
        {
            "voice_id": context.arguments.voice,
            "context_id": context.arguments.context,
            "candidate": manifest.status.value if manifest else None,
            "active": _registry(context).list().get(context.arguments.context),
        }
    )
    return 0


def show(context: PerspectiveCommandContext) -> int:
    """Show perspective operations."""
    directory = _candidate(context)
    if not directory.exists():
        resolved = _registry(context).resolve(context.arguments.context)
        directory = context.root / resolved["path"]
    print((directory / "perspective.md").read_text(encoding="utf-8"))
    return 0


def verify(context: PerspectiveCommandContext) -> int:
    """Verify perspective operations."""
    candidate = _candidate(context)
    manifest = PerspectiveManifest.model_validate_json(
        (candidate / "manifest.json").read_text(encoding="utf-8")
    )
    mismatches = [
        component_name
        for component_name, filename in manifest.components.items()
        if hash_file(candidate / filename) != manifest.component_hashes[component_name]
    ]
    print_json(
        {
            "voice_id": context.arguments.voice,
            "context_id": context.arguments.context,
            "valid": not mismatches,
            "mismatches": mismatches,
        }
    )
    return 0 if not mismatches else 6


def approve(context: PerspectiveCommandContext) -> int:
    """Approve perspective operations."""
    arguments = context.arguments
    print_json(_registry(context).activate(arguments.context, arguments.approved_by))
    return 0


def deactivate(context: PerspectiveCommandContext) -> int:
    """Deactivate perspective operations."""
    arguments = context.arguments
    print_json(_registry(context).deactivate(arguments.context, arguments.reason))
    return 0


def show_proposals(context: PerspectiveCommandContext) -> int:
    """Show proposals."""
    arguments = context.arguments
    print_json(PerspectiveProposalStore(context.root, arguments.voice, arguments.context).list())
    return 0


def stage_proposal(context: PerspectiveCommandContext) -> int:
    """Stage proposal."""
    arguments = context.arguments
    print_json(_registry(context).stage_proposal(arguments.context, arguments.proposal))
    return 0


def retire(context: PerspectiveCommandContext) -> int:
    """Retire perspective operations."""
    arguments = context.arguments
    print_json(
        _registry(context).retire_entry(arguments.context, arguments.entry, arguments.reason)
    )
    return 0
