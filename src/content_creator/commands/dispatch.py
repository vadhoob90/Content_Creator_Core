"""Dispatch non-specialist command families and lifecycle commands."""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

import yaml

from ..agent_resources import AgentWorkspace
from ..coordinator import ContentCoordinator
from ..domain import (
    AuthorContribution,
    PerspectiveMode,
    PerspectiveSelection,
    ResearchDepth,
    ResearchSource,
    WorkOrder,
)
from ..evaluation import run_live_suite, run_replay_suite
from ..experience import render_overview, render_start
from ..health import WorkspaceHealth
from ..intake import ClarificationRequired
from ..orchestrator import Orchestrator
from ..packs import PackRegistry
from ..storage import RunStore
from ..upgrade import WorkspaceUpgrader
from ..workspace import WorkspaceScaffolder, initialise_workspace
from . import operations as operations_commands
from . import provider as provider_commands
from . import schema as schema_commands
from . import visual as visual_commands
from .parser import build_parser
from .shared import print_json, resolve_root


def run(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    root = resolve_root(args.root)
    if args.command == "advanced":
        print(
            "Advanced commands:\n"
            "  init, agents, provider, plan, coordinator, pack, packs, voice,\n"
            "  perspective, approve-research, reject-research, eval\n\n"
            "Use: content-creator <command> --help"
        )
        return 0
    if args.command == "schema":
        return schema_commands.run(root, args, print_json)
    if args.command == "operations":
        return operations_commands.run(root, args, print_json)
    if args.command == "init":
        print_json(initialise_workspace(root, args.agent_template))
        return 0
    if args.command == "workspace":
        if args.workspace_command == "upgrade":
            upgrader = WorkspaceUpgrader(root)
            print_json(upgrader.apply(args.to) if args.apply else upgrader.preview(args.to))
            return 0
        destination = Path(args.directory).expanduser()
        if not destination.is_absolute():
            destination = root / destination if args.root else Path.cwd() / destination
        destination = destination.resolve()
        print_json(
            WorkspaceScaffolder(destination).create(
                name=args.name or destination.name,
                author_name=args.author_name,
                voice_id=args.voice_id,
                voice_label=args.voice_label,
                packs=args.pack,
                agent_template=args.agent_template,
                core_source=args.core_source,
                core_url=args.core_url,
                core_ref=args.core_ref,
                perspective_mode=args.perspective_mode,
            )
        )
        return 0
    if args.command == "agents":
        workspace = AgentWorkspace(root)
        if args.agent_command == "scaffold":
            print_json(workspace.scaffold(args.template))
        elif args.agent_command == "status":
            print_json(workspace.status(args.template))
        else:
            print_json(workspace.diff_template(args.template))
        return 0
    if args.command == "provider":
        return provider_commands.run(root, args, print_json)
    if args.command == "doctor":
        report = WorkspaceHealth(root).report()
        print_json(report)
        return 0 if report["status"] == "ok" else 1
    if args.command == "overview":
        snapshot = ContentCoordinator(root).snapshot(args.run_limit)
        if args.json:
            print_json(snapshot)
        else:
            print(render_overview(snapshot))
        return 0
    if args.command == "start":
        coordinator = ContentCoordinator(root)
        snapshot = coordinator.snapshot()
        if not args.request or not snapshot.is_workspace:
            if args.json:
                print_json(snapshot)
            else:
                print(render_start(snapshot))
            return 0
        try:
            order = Orchestrator(root).plan_request(
                args.request,
                provider=args.provider,
            )
        except ClarificationRequired as exc:
            if args.json:
                print_json(
                    {
                        "needs_clarification": True,
                        "questions": exc.questions,
                        "workspace": snapshot.model_dump(mode="json"),
                    }
                )
            else:
                print(render_start(snapshot, questions=exc.questions))
            return 3
        if args.json:
            print_json(
                {
                    "workspace": snapshot.model_dump(mode="json"),
                    "work_order": order.model_dump(mode="json"),
                    "mutates_workspace": False,
                    "approval_points": [
                        "research checkpoint when required",
                        "final author review",
                        "repository-local publication",
                    ],
                }
            )
        else:
            print(render_start(snapshot, order=order))
        return 0
    if args.command == "coordinator":
        coordinator = ContentCoordinator(root)
        if args.coordinator_command == "capabilities":
            print_json(coordinator.capabilities())
        elif args.coordinator_command == "context":
            print_json(coordinator.context(args.run_limit))
        elif args.coordinator_command == "runs":
            print_json(coordinator.runs(args.limit))
        else:
            print_json(coordinator.next_actions(args.run_id))
        return 0
    if args.command == "packs":
        print_json([pack.model_dump(mode="json") for pack in PackRegistry(root).list()])
        return 0
    if args.command == "pack":
        packs = PackRegistry(root)
        if args.pack_command == "create":
            pack_id = args.pack_id
            destination = root / "packs" / pack_id
            if destination.exists():
                raise ValueError("Content pack already exists: {}".format(pack_id))
            destination.mkdir(parents=True)
            RunStore._atomic_text(
                destination / "pack.json",
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "id": pack_id,
                        "version": "0.1.0",
                        "extends": args.extends,
                        "format": "text",
                        "destination": "content/{}/published".format(pack_id),
                        "rubric": "rubric.yaml",
                    },
                    indent=2,
                ),
            )
            RunStore._atomic_text(
                destination / "rubric.yaml",
                "dimensions: {}\nhard_gates: []",
            )
            RunStore._atomic_text(destination / "validators.yaml", "append: []")
            RunStore._atomic_text(
                destination / "README.md",
                "# {}\n\nExtends `{}`.".format(pack_id, args.extends),
            )
            (destination / "evals").mkdir()
            print_json(packs.resolve(pack_id))
            return 0
        if args.pack_command == "list":
            print_json([item.model_dump(mode="json") for item in packs.list()])
        else:
            item = (
                packs.resolve(args.pack_id)
                if args.pack_command in {"show", "validate"} or args.resolved
                else packs.get(args.pack_id)
            )
            print_json(item)
        return 0
    if args.command == "voice":
        from .voice import run as run_voice

        return run_voice(root, args)
    if args.command == "perspective":
        from .perspective import run as run_perspective

        return run_perspective(root, args)
    if args.command == "eval":
        runner = run_live_suite if args.mode == "live" else run_replay_suite
        report = runner(root, args.providers)
        print_json(report)
        return 0 if report["passed"] == report["total"] else 1

    orchestrator = Orchestrator(root)
    if args.command == "plan":
        try:
            print_json(orchestrator.plan_request(args.request, provider=args.provider))
            return 0
        except ClarificationRequired as exc:
            print_json({"needs_clarification": True, "questions": exc.questions})
            return 3
    if args.command == "run":
        if args.brief:
            data = yaml.safe_load(Path(args.brief).read_text(encoding="utf-8"))
            research = data.pop("research", {}) or {}
            data.setdefault("research_depth", research.get("depth", "none"))
            data.setdefault("research_source", research.get("source", "none"))
            order = WorkOrder.model_validate(data)
            if args.provider:
                order.provider = args.provider
            if args.voice != "default":
                order.voice_id = args.voice
            if args.voice_version:
                order.voice_version = args.voice_version
        elif args.pack or args.format or args.research or args.research_source:
            if not args.request:
                raise ValueError("run requires a request or --brief")
            content_format = args.format
            if args.pack:
                content_format = PackRegistry(root).get(args.pack).format
            depth = ResearchDepth(args.research or "none")
            source = ResearchSource(
                args.research_source or ("none" if depth == ResearchDepth.NONE else "agent")
            )
            order = WorkOrder(
                request=args.request,
                topic=args.topic or args.request,
                content_pack=args.pack,
                voice_id=args.voice,
                voice_version=args.voice_version,
                format=content_format or "text",
                research_depth=depth,
                research_source=source,
                supplied_research_path=args.research_file,
                provider=args.provider,
                objective=args.objective or "share a useful perspective",
                audience=args.audience or "professional audience",
                pack_options={
                    key: value
                    for key, value in {
                        "length": args.length,
                        "language": args.language,
                        "structure": args.structure,
                        "destination": args.destination,
                    }.items()
                    if value is not None
                },
            )
        else:
            if not args.request:
                raise ValueError("run requires a request or --brief")
            try:
                order = orchestrator.plan_request(args.request, provider=args.provider)
            except ClarificationRequired as exc:
                print_json({"needs_clarification": True, "questions": exc.questions})
                return 3
            order.voice_id = args.voice
            order.voice_version = args.voice_version
        if args.no_perspective:
            order.perspective_mode = PerspectiveMode.DISABLED
            order.perspective_context = None
            order.perspective_version = None
            order.perspective_selections = []
        elif args.perspective_context:
            order.perspective_selections = [
                PerspectiveSelection(
                    context_id=context,
                    version=(
                        args.perspective_version
                        if index == 0 and len(args.perspective_context) == 1
                        else None
                    ),
                )
                for index, context in enumerate(args.perspective_context)
            ]
            order.perspective_context = order.perspective_selections[0].context_id
        if args.perspective_version:
            if len(args.perspective_context) != 1:
                raise ValueError("--perspective-version requires exactly one --perspective-context")
            order.perspective_version = args.perspective_version
        if args.thesis or args.intended_challenge or args.personal_basis or args.perspective_entry:
            order.author_contribution = AuthorContribution(
                thesis=args.thesis,
                intended_challenge=args.intended_challenge,
                personal_basis=args.personal_basis,
                supplied_by_author=args.author_supplied,
                reusable_perspective_entry_ids=args.perspective_entry,
                provenance_notes=["Supplied through the run command"],
            )
        if args.parent_run:
            parent = orchestrator.store.load(args.parent_run)
            order.parent_run_id = parent.id
            order.content_session_id = parent.work_order.content_session_id
        elif args.content_session:
            order.content_session_id = args.content_session
        if args.idempotency_key is None:
            state = orchestrator.start(order)
        else:
            state = orchestrator.start(
                order,
                idempotency_key=args.idempotency_key,
            )
        print_json(state)
        return 0
    if args.command == "diagnostics":
        if args.diagnostics_command in {"show", "preflight"}:
            print_json(orchestrator.diagnostic_preflight(args.run_id))
            return 0
        if not (
            args.issue_url.startswith("https://github.com/")
            or args.issue_url.startswith("https://www.github.com/")
        ):
            raise ValueError("--issue-url must be a GitHub HTTPS URL")
        print_json(orchestrator.link_diagnostic_issue(args.run_id, args.issue_url))
        return 0
    if args.command == "status":
        print_json(orchestrator.store.load(args.run_id))
        return 0
    if args.command == "submission":
        submission_state = orchestrator.store.load_by_idempotency_key(args.idempotency_key)
        if submission_state is None:
            raise ValueError("Unknown idempotency key")
        print_json(submission_state)
        return 0
    if args.command == "visual":
        return visual_commands.run(root, args, print_json)
    if args.command == "approve-research":
        print_json(orchestrator.resume_research(args.run_id, True, notes=args.notes))
        return 0
    if args.command == "reject-research":
        print_json(orchestrator.resume_research(args.run_id, False, notes=args.notes))
        return 0
    if args.command == "publish":
        print_json(
            orchestrator.publish(
                args.run_id,
                filename=args.filename,
                feedback=args.feedback,
                diagnostic_decision=args.diagnostic_decision,
            )
        )
        return 0
    return 2
