"""Implement the visual command family."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from ..packs import PackRegistry
from ..run_queries import RunQueries
from ..visual_preferences import VisualPreferenceMemory
from ..visual_requests import VisualRenderRequest, VisualRequestWorkflow
from ..visuals import VisualBrief, VisualCritique, VisualError, VisualWorkflow


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
    replace = commands.add_parser("replace", help="Replace media on a published package")
    replace.add_argument("run_id")
    replace.add_argument("asset_id")
    learn = commands.add_parser("learn", help="Record visual-only author preferences")
    learn.add_argument("run_id")
    learn.add_argument("--feedback", required=True)
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
    queries = RunQueries(root)
    state = queries.state(args.run_id)
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
    elif args.visual_command in {"publish", "replace", "learn"}:
        return _run_package_command(root, args, emit, workflow, state, profile)
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
        emit(json.loads(queries.artifact(args.run_id, "visuals/manifest.json")))
    return 0


def _run_package_command(
    root: Path,
    args: argparse.Namespace,
    emit: Callable[[Any], None],
    workflow: VisualWorkflow,
    state: Any,
    profile: Any,
) -> int:
    """Run package publication, replacement, or visual preference commands.

    Args:
        root (Path): Author workspace root.
        args (argparse.Namespace): Parsed visual command arguments.
        emit (Callable[[Any], None]): Structured command output writer.
        workflow (VisualWorkflow): Governed visual lifecycle service.
        state (Any): Persisted run state selected by the command.
        profile (Any): Resolved pack visual profile.

    Returns:
        int: Zero after the requested visual package operation completes.

    Raises:
        VisualError: If a published run has no selected replacement media.
    """
    if args.visual_command == "learn":
        path = VisualPreferenceMemory(root, state.work_order.voice_id).record(
            args.run_id,
            args.feedback,
        )
        emit({"scope": "visual", "path": str(path.relative_to(root))})
        return 0
    from ..orchestrator import Orchestrator

    orchestrator = Orchestrator(root)
    if args.visual_command == "replace":
        emit(orchestrator.replace_visual(args.run_id, args.asset_id))
        return 0
    if state.status.value == "published":
        asset = workflow.ensure_publication_ready(args.run_id, profile)
        if asset is None:
            raise VisualError("Published run has no selected visual replacement")
        emit(orchestrator.replace_visual(args.run_id, asset.asset_id))
    else:
        emit(orchestrator.publish(args.run_id))
    return 0
