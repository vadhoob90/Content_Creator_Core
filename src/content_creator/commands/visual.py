"""Implement the visual command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from ..packs import PackRegistry
from ..storage import RunStore
from ..visual_requests import VisualRenderRequest, VisualRequestWorkflow
from ..visuals import VisualBrief, VisualCritique, VisualWorkflow


def register(subparsers: Any) -> None:
    """Register the visual workflow.

    Args:
        subparsers (Any): The argparse subparser collection receiving the command.

    Returns:
        None: The callable updates register state and returns no value.
    """
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
    components = commands.add_parser(
        "components", help="List compatible reusable Core visual components"
    )
    components.add_argument("run_id")
    components.add_argument("--role")
    render = commands.add_parser("render", help="Render validated visual review variants")
    render.add_argument("run_id")
    render.add_argument("--role")
    render.add_argument("--request", default="Create an image for this content.")
    render.add_argument("--variants", type=int, default=1)
    render.add_argument("--adapter")
    render.add_argument("--parent-asset-id")
    render.add_argument("--objective")
    render.add_argument("--alt-text")
    commands.add_parser("publish").add_argument("run_id")
    commands.add_parser("show").add_argument("run_id")


def run(root: Path, args: argparse.Namespace, emit: Callable[[Any], None]) -> int:
    """Run the visual workflow.

    Resolve the persisted content pack once, then dispatch the requested command
    through either the established asset lifecycle or the component-aware request path.

    Args:
        root (Path): The workspace root directory.
        args (argparse.Namespace): The parsed command-line arguments.
        emit (Callable[[Any], None]): The emit value passed to run.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    workflow = VisualWorkflow(root)
    store = RunStore(root)
    state = store.load(args.run_id)
    pack = PackRegistry(root).resolve(state.work_order.content_pack, state.work_order.pack_options)
    profile = pack.visuals
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
    elif args.visual_command == "components":
        emit(
            [
                component.model_dump(mode="json")
                for component in VisualRequestWorkflow(root).components(profile, args.role)
            ]
        )
    elif args.visual_command == "render":
        emit(
            VisualRequestWorkflow(root).render(
                profile=profile,
                request=VisualRenderRequest(
                    run_id=args.run_id,
                    pack_id=pack.id,
                    pack_version=pack.version,
                    request=args.request,
                    role=args.role,
                    variants=args.variants,
                    adapter_name=args.adapter,
                    parent_asset_id=args.parent_asset_id,
                    objective=args.objective,
                    alt_text=args.alt_text,
                ),
            )
        )
    else:
        emit(json.loads(store.read_artifact(args.run_id, "visuals/manifest.json")))
    return 0
