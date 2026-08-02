"""Perspective command execution, isolated from the CLI runtime."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..perspective_assessment import create_blind_comparison, record_blind_comparison
from ..perspectives import (
    PerspectiveCatalogueStore,
    PerspectiveEntry,
    PerspectiveError,
    PerspectiveManifest,
    PerspectiveProposalStore,
    PerspectiveProvenance,
    PerspectiveRegistry,
)
from ..voices import VoiceRegistry, hash_file
from .perspective_parser import register as register
from .shared import print_json


def run(root: Path, args: argparse.Namespace) -> int:
    command = args.perspective_command
    if command == "compare-create":
        baseline = Path(args.baseline)
        if not baseline.is_absolute():
            baseline = root / baseline
        print_json(
            create_blind_comparison(
                root,
                args.run,
                baseline,
            )
        )
        return 0
    if command == "compare-record":
        assessment = Path(args.assessment)
        if not assessment.is_absolute():
            assessment = root / assessment
        print_json(
            record_blind_comparison(
                root,
                args.run,
                assessment,
            )
        )
        return 0
    resolved_voice = VoiceRegistry(root).resolve(args.voice)
    if not resolved_voice.get("perspectives_allowed", True):
        raise PerspectiveError(
            "Perspectives are disabled for starter voice {} until a "
            "source-derived voice is reviewed and activated".format(args.voice)
        )
    registry = PerspectiveRegistry(root, args.voice)
    if command == "catalogue":
        print_json(PerspectiveCatalogueStore(root, args.voice).load().model_dump(mode="json"))
        return 0
    if command == "verify-catalogue":
        result = PerspectiveCatalogueStore(root, args.voice).verify()
        print_json(result)
        return 0 if result["valid"] else 6
    if command == "create":
        entries = []
        if args.statement:
            if not args.evidence:
                raise ValueError("--evidence is required when creating a perspective statement")
            entries.append(
                PerspectiveEntry(
                    type=args.type,
                    statement=args.statement,
                    topics=args.topic,
                    qualifications=args.qualification,
                    counterpositions=args.counterposition,
                    provenance=[
                        PerspectiveProvenance(
                            kind="direct_author_input",
                            reference=args.evidence,
                        )
                    ],
                )
            )
        print_json(
            registry.stage(
                args.context,
                entries,
                display_name=args.display_name,
            )
        )
        return 0
    if command == "list":
        print_json(registry.list())
        return 0
    context_root = registry.context_root(args.context)
    candidate = context_root / "candidate"
    manifest_path = candidate / "manifest.json"
    if command == "status":
        manifest = (
            PerspectiveManifest.model_validate_json(manifest_path.read_text())
            if manifest_path.exists()
            else None
        )
        print_json(
            {
                "voice_id": args.voice,
                "context_id": args.context,
                "candidate": manifest.status.value if manifest else None,
                "active": registry.list().get(args.context),
            }
        )
        return 0
    if command == "show":
        directory = candidate
        if not directory.exists():
            resolved = registry.resolve(args.context)
            directory = root / resolved["path"]
        print((directory / "perspective.md").read_text(encoding="utf-8"))
        return 0
    if command == "verify":
        manifest = PerspectiveManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        mismatches = [
            name
            for name, filename in manifest.components.items()
            if hash_file(candidate / filename) != manifest.component_hashes[name]
        ]
        print_json(
            {
                "voice_id": args.voice,
                "context_id": args.context,
                "valid": not mismatches,
                "mismatches": mismatches,
            }
        )
        return 0 if not mismatches else 6
    if command == "approve":
        print_json(registry.activate(args.context, args.approved_by))
        return 0
    if command == "deactivate":
        print_json(registry.deactivate(args.context, args.reason))
        return 0
    if command == "proposals":
        print_json(PerspectiveProposalStore(root, args.voice, args.context).list())
        return 0
    if command == "stage-proposal":
        print_json(registry.stage_proposal(args.context, args.proposal))
        return 0
    if command == "retire":
        print_json(registry.retire_entry(args.context, args.entry, args.reason))
        return 0
    return 2
