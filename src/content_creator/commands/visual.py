"""Visual asset command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from ..packs import PackRegistry
from ..storage import RunStore
from ..visuals import VisualBrief, VisualCritique, VisualWorkflow


def register(subparsers: Any) -> None:
    parser = subparsers.add_parser("visual", help="Manage visual assets for a reviewed run")
    commands = parser.add_subparsers(dest="visual_command", required=True)
    brief = commands.add_parser("brief", help="Create a typed visual brief")
    brief.add_argument("run_id")
    brief.add_argument("brief_file")
    for command in ("validate", "select", "approve"):
        item = commands.add_parser(command)
        item.add_argument("run_id")
        item.add_argument("asset_id")
    critique = commands.add_parser("critique")
    critique.add_argument("run_id")
    critique.add_argument("asset_id")
    critique.add_argument("critique_file")
    commands.add_parser("publish").add_argument("run_id")
    commands.add_parser("show").add_argument("run_id")


def run(root: Path, args: argparse.Namespace, emit: Callable[[Any], None]) -> int:
    workflow = VisualWorkflow(root)
    store = RunStore(root)
    state = store.load(args.run_id)
    profile = (
        PackRegistry(root)
        .resolve(state.work_order.content_pack, state.work_order.pack_options)
        .visuals
    )
    if args.visual_command == "brief":
        payload = json.loads(Path(args.brief_file).read_text(encoding="utf-8"))
        payload["run_id"] = args.run_id
        emit(workflow.create_brief(VisualBrief.model_validate(payload), profile))
    elif args.visual_command == "validate":
        emit(workflow.validate(args.run_id, args.asset_id, profile))
    elif args.visual_command == "critique":
        payload = json.loads(Path(args.critique_file).read_text(encoding="utf-8"))
        emit(
            workflow.record_critique(
                args.run_id, args.asset_id, VisualCritique.model_validate(payload)
            )
        )
    elif args.visual_command == "select":
        emit(workflow.select(args.run_id, args.asset_id))
    elif args.visual_command == "approve":
        emit(workflow.approve(args.run_id, args.asset_id))
    elif args.visual_command == "publish":
        target = workflow.publish(args.run_id, profile)
        emit({"published_path": str(target.relative_to(root)) if target else None})
    else:
        emit(json.loads(store.read_artifact(args.run_id, "visuals/manifest.json")))
    return 0
