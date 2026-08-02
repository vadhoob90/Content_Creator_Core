"""Voice command execution, isolated from the CLI runtime."""

from __future__ import annotations

import argparse
import difflib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import List, Optional

from ..configuration import Configuration
from ..learning import LearningMemory
from ..orchestrator import Orchestrator
from ..storage import StorageError
from ..voice_assessment import assess_voice_draft, load_score_preference, save_score_preference
from ..voice_builder import VoiceBuilder
from ..voice_ml import train_voice_ml_model
from ..voices import (
    Authorisation,
    VoiceManifest,
    VoiceOnboardingRecord,
    VoiceRegistry,
    VoiceStrategy,
    VoiceWorkOrder,
    hash_file,
    load_voice_onboarding,
    save_voice_onboarding,
    voice_id_for,
)
from .shared import print_json
from .voice_parser import register as register


def command_needs_model(args: argparse.Namespace) -> bool:
    return args.voice_command in {"build", "rebuild"} or (
        args.voice_command == "create" and not args.no_build
    )


def _source_lines(path: Optional[str]) -> List[str]:
    if not path:
        return []
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _documents(values: List[str]) -> List[str]:
    result: List[str] = []
    for value in values:
        path = Path(value).expanduser().resolve()
        if path.is_dir():
            result.extend(
                str(item)
                for item in sorted(path.rglob("*"))
                if item.is_file()
                and item.suffix.lower() in {".txt", ".md", ".html", ".pdf", ".docx"}
            )
        else:
            result.append(str(path))
    return result


def run(root: Path, args: argparse.Namespace) -> int:
    runner = None
    if not getattr(args, "offline_analysis", False) and command_needs_model(args):
        runner = Orchestrator(root).runner
    builder = VoiceBuilder(root, runner=runner, provider=getattr(args, "provider", None))
    registry = VoiceRegistry(root)
    command = args.voice_command
    if command == "onboard":
        voice_id = voice_id_for(args.voice_id)
        if voice_id != args.voice_id:
            raise ValueError("voice_id must already be a repository-safe slug")
        display_name = args.label or "{} — General".format(args.author_name)
        intended_uses = args.use or ["general-text"]
        if args.strategy == VoiceStrategy.STARTER.value:
            if args.statistical_voice_score != "disabled":
                raise ValueError(
                    "Starter voices cannot use statistical voice scoring because "
                    "they have no author evidence"
                )
            resolved = registry.activate_starter(
                voice_id=voice_id,
                display_name=display_name,
                author_name=args.author_name,
                selected_by=args.selected_by,
                intended_uses=intended_uses,
            )
            score_preference = save_score_preference(
                root,
                voice_id,
                enabled=False,
                method="deterministic",
                selected_by=args.selected_by,
            )
            print_json(
                {
                    "status": "starter-active",
                    "voice": resolved,
                    "perspective_mode": "disabled",
                    "statistical_voice_score": score_preference,
                    "perspective_disabled_reason": ("starter-voice-without-author-evidence"),
                    "next_step": (
                        "Create content with --voice {}. Re-run voice onboard "
                        "with --strategy source-derived when author evidence "
                        "is available."
                    ).format(voice_id),
                }
            )
            return 0
        selected_at = datetime.now(UTC).isoformat()
        order = VoiceWorkOrder(
            display_name=display_name,
            voice_id=voice_id,
            author_name=args.author_name,
            authorisation=Authorisation(
                confirmed=True,
                attested_by=args.selected_by,
                intended_uses=intended_uses,
            ),
            strategy=VoiceStrategy.SOURCE_DERIVED,
        )
        builder.save_work_order(order)
        record = VoiceOnboardingRecord(
            voice_id=voice_id,
            display_name=display_name,
            author_name=args.author_name,
            status="collecting-sources",
            strategy=VoiceStrategy.SOURCE_DERIVED,
            selected_by=args.selected_by,
            selected_at=selected_at,
            perspective_mode="pending-source-derived-activation",
        )
        save_voice_onboarding(root, record)
        score_method = (
            "deterministic"
            if args.statistical_voice_score == "disabled"
            else args.statistical_voice_score
        )
        score_preference = save_score_preference(
            root,
            voice_id,
            enabled=args.statistical_voice_score != "disabled",
            method=score_method,
            selected_by=args.selected_by,
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
    if command == "create":
        author_name = args.author_name or args.name
        if not author_name:
            raise ValueError("--author-name is required (or use legacy --name)")
        display_name = args.label or args.name or author_name
        voice_id = voice_id_for(args.voice_id or display_name)
        if args.voice_id and voice_id != args.voice_id:
            raise ValueError("--voice-id must already be a repository-safe slug")
        order = VoiceWorkOrder(
            display_name=display_name,
            voice_id=voice_id,
            author_name=author_name,
            author_aliases=args.author_alias,
            authorisation=Authorisation(
                confirmed=bool(args.authorised_by),
                attested_by=args.authorised_by,
                intended_uses=args.use or ["general-text"],
            ),
            urls=_source_lines(args.sources),
            documents=_documents(args.documents),
            strategy=VoiceStrategy.SOURCE_DERIVED,
        )
        builder.save_work_order(order)
        save_voice_onboarding(
            root,
            VoiceOnboardingRecord(
                voice_id=voice_id,
                display_name=display_name,
                author_name=author_name,
                status="collecting-sources",
                strategy=VoiceStrategy.SOURCE_DERIVED,
                selected_by=args.authorised_by,
                selected_at=datetime.now(UTC).isoformat(),
                perspective_mode="pending-source-derived-activation",
            ),
        )
        score_method = (
            "deterministic"
            if args.statistical_voice_score == "disabled"
            else args.statistical_voice_score
        )
        save_score_preference(
            root,
            voice_id,
            enabled=args.statistical_voice_score != "disabled",
            method=score_method,
            selected_by=args.authorised_by,
        )
        print_json(order if args.no_build else builder.build(voice_id))
        return 0
    if command in {"build", "rebuild"}:
        print_json(builder.build(args.voice_id))
        return 0
    if command == "list":
        print_json(registry.list())
        return 0
    if command == "verify-all":
        voice_ids = set(registry.list())
        voice_ids.update(
            path.parent.parent.name
            for path in (root / "profiles").glob("*/candidate/manifest.json")
        )
        reports = [_verify_voice(root, registry, voice_id) for voice_id in sorted(voice_ids)]
        valid = all(report["valid"] for report in reports)
        print_json({"valid": valid, "voices": reports})
        return 0 if valid else 6
    if command == "approve":
        if args.override_evaluation and not args.reason:
            raise ValueError("--override-evaluation requires --reason")
        print_json(
            registry.activate(
                args.voice_id,
                args.approved_by,
                args.reason if args.override_evaluation else None,
            )
        )
        return 0
    if command == "deactivate":
        print_json(registry.deactivate(args.voice_id, args.reason))
        return 0
    if command == "reactivate":
        print_json(registry.activate(args.voice_id, args.approved_by, "reactivation"))
        return 0
    if command == "add-sources":
        order = builder.load_work_order(args.voice_id)
        order.urls.extend(item for item in _source_lines(args.sources) if item not in order.urls)
        order.documents.extend(
            item for item in _documents(args.documents) if item not in order.documents
        )
        builder.save_work_order(order)
        print_json(order)
        return 0
    if command == "consolidate-learnings":
        path = LearningMemory(root, args.voice_id).consolidate_candidate()
        print_json(
            {
                "voice_id": args.voice_id,
                "status": "candidate",
                "path": str(path.relative_to(root)),
            }
        )
        return 0
    if command in {"assess", "score"}:
        draft_path = Path(args.draft).expanduser()
        if not draft_path.is_absolute():
            draft_path = root / draft_path
        if not draft_path.is_file():
            raise StorageError("Draft does not exist: {}".format(draft_path))
        policy = Configuration(root).statistical_voice_score_policy
        policy["method"] = "deterministic" if command == "assess" else args.method
        print_json(
            assess_voice_draft(
                root,
                args.voice_id,
                args.voice_version,
                draft_path.read_text(encoding="utf-8"),
                policy,
            )
        )
        return 0
    if command == "score-config":
        if not (root / "profiles" / args.voice_id).is_dir():
            raise StorageError("Unknown voice: {}".format(args.voice_id))
        existing_preference = load_score_preference(root, args.voice_id) or {}
        preference = save_score_preference(
            root,
            args.voice_id,
            enabled=args.enable,
            method=args.method or existing_preference.get("method", "deterministic"),
            selected_by=args.selected_by,
        )
        print_json(preference)
        return 0
    if command == "train-ml":
        result = train_voice_ml_model(
            root,
            args.voice_id,
            args.voice_version,
            [Path(item) for item in _documents(args.comparison_documents)],
            accept_low_confidence=args.accept_low_confidence,
            replace=args.replace,
        )
        print_json(result)
        return 0 if result["trained"] else 5
    if command == "diff":
        voice_root = root / "profiles" / args.voice_id

        def profile(version: str) -> List[str]:
            directory = (
                voice_root / "candidate"
                if version == "candidate"
                else voice_root / "versions" / version
            )
            return (directory / "profile.md").read_text(encoding="utf-8").splitlines()

        print(
            "\n".join(
                difflib.unified_diff(
                    profile(args.from_version),
                    profile(args.to_version),
                    fromfile=args.from_version,
                    tofile=args.to_version,
                    lineterm="",
                )
            )
        )
        return 0
    candidate = root / "profiles" / args.voice_id / "candidate"
    manifest_path = candidate / "manifest.json"
    if command == "status":
        active = registry.list().get(args.voice_id)
        onboarding = load_voice_onboarding(root, args.voice_id)
        candidate_status = (
            VoiceManifest.model_validate_json(manifest_path.read_text()).status.value
            if manifest_path.exists()
            else None
        )
        print_json(
            {
                "voice_id": args.voice_id,
                "onboarding": (onboarding.model_dump(mode="json") if onboarding else None),
                "candidate": candidate_status,
                "active": active,
                "statistical_voice_score": load_score_preference(root, args.voice_id),
            }
        )
        return 0
    if command == "show":
        directory = candidate
        if not directory.exists():
            resolved = registry.resolve(args.voice_id)
            directory = root / resolved["path"]
        print((directory / "profile.md").read_text(encoding="utf-8"))
        return 0
    if command == "signature":
        signature = (candidate / "linguistic-signature.json").read_text(encoding="utf-8")
        print_json(json.loads(signature))
        return 0
    if command == "verify":
        report = _verify_voice(root, registry, args.voice_id)
        print_json(report)
        return 0 if report["valid"] else 6
    return 2


def _verify_voice(
    root: Path,
    registry: VoiceRegistry,
    voice_id: str,
) -> dict:
    directory = root / "profiles" / voice_id / "candidate"
    manifest_path = directory / "manifest.json"
    if not manifest_path.exists():
        resolved = registry.resolve(voice_id)
        directory = root / resolved["path"]
        manifest_path = directory / "manifest.json"
    manifest = VoiceManifest.model_validate_json(manifest_path.read_text())
    mismatches = [
        name
        for name, filename in manifest.components.items()
        if not (directory / filename).exists()
        or hash_file(directory / filename) != manifest.component_hashes[name]
    ]
    return {
        "voice_id": voice_id,
        "valid": not mismatches,
        "mismatches": mismatches,
    }
