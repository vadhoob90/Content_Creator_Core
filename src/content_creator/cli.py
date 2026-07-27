from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional

from .configuration import Configuration
from .domain import ContentFormat, ResearchDepth, ResearchSource, WorkOrder
from .evaluation import run_live_suite, run_replay_suite
from .intake import ClarificationRequired
from .orchestrator import Orchestrator
from .packs import PackRegistry


def _root(value: Optional[str]) -> Path:
    return Path(value or ".").resolve()


def _print(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="content-creator")
    parser.add_argument("--root", help="Repository root (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Turn natural language into a work order")
    plan.add_argument("request")
    plan.add_argument("--provider", choices=["anthropic", "openai"])

    sub.add_parser("doctor", help="Validate offline configuration and assets")
    sub.add_parser("packs", help="List installed content packs")

    run = sub.add_parser("run", help="Create a run and execute its route")
    _add_run_arguments(run)

    status = sub.add_parser("status", help="Show persisted run state")
    status.add_argument("run_id")

    resume = sub.add_parser("approve-research", help="Resume a deep-research run")
    resume.add_argument("run_id")
    resume.add_argument("--notes")

    reject = sub.add_parser("reject-research", help="Stop after the research checkpoint")
    reject.add_argument("run_id")
    reject.add_argument("--notes")

    publish = sub.add_parser("publish", help="Move the reviewed output into published/")
    publish.add_argument("run_id")
    publish.add_argument("--filename")
    publish.add_argument("--feedback")

    evaluate = sub.add_parser("eval", help="Run replay or live evaluation")
    evaluate.add_argument("--mode", choices=["replay", "live"], default="replay")
    evaluate.add_argument(
        "--providers", nargs="+", default=["anthropic", "openai"]
    )
    return parser


def _add_run_arguments(parser) -> None:
    parser.add_argument("request")
    parser.add_argument("--topic")
    parser.add_argument("--pack", choices=["linkedin-post", "linkedin-article"])
    parser.add_argument("--voice", default="default")
    parser.add_argument("--format", choices=["post", "article"])
    parser.add_argument("--research", choices=["none", "light", "deep"])
    parser.add_argument("--research-source", choices=["none", "supplied", "agent"])
    parser.add_argument("--research-file")
    parser.add_argument("--provider", choices=["anthropic", "openai"])


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    if args.command == "doctor":
        configuration = Configuration(root)
        packs = PackRegistry(root).list()
        voice = root / "profiles" / "default" / "voice.md"
        checks = {
            "model_catalogue": bool(configuration.models),
            "content_packs": [pack.id for pack in packs],
            "default_voice": voice.exists(),
            "route_cases": (root / "evals" / "cases" / "route-matrix.yaml").exists(),
        }
        healthy = (
            checks["model_catalogue"]
            and bool(checks["content_packs"])
            and checks["default_voice"]
            and checks["route_cases"]
        )
        _print({"status": "ok" if healthy else "error", "checks": checks})
        return 0 if healthy else 1
    if args.command == "packs":
        _print([pack.model_dump(mode="json") for pack in PackRegistry(root).list()])
        return 0
    if args.command == "eval":
        runner = run_live_suite if args.mode == "live" else run_replay_suite
        report = runner(root, args.providers)
        _print(report)
        return 0 if report["passed"] == report["total"] else 1

    orchestrator = Orchestrator(root)
    if args.command == "plan":
        try:
            _print(orchestrator.plan_request(args.request, provider=args.provider))
            return 0
        except ClarificationRequired as exc:
            _print({"needs_clarification": True, "questions": exc.questions})
            return 3
    if args.command == "run":
        if args.pack or args.format or args.research or args.research_source:
            content_format = args.format
            if args.pack:
                content_format = (
                    "article" if args.pack == "linkedin-article" else "post"
                )
            depth = ResearchDepth(args.research or "none")
            source = ResearchSource(
                args.research_source
                or ("none" if depth == ResearchDepth.NONE else "agent")
            )
            order = WorkOrder(
                request=args.request,
                topic=args.topic or args.request,
                content_pack=args.pack,
                voice_id=args.voice,
                format=ContentFormat(content_format or "post"),
                research_depth=depth,
                research_source=source,
                supplied_research_path=args.research_file,
                provider=args.provider,
            )
        else:
            try:
                order = orchestrator.plan_request(args.request, provider=args.provider)
            except ClarificationRequired as exc:
                _print({"needs_clarification": True, "questions": exc.questions})
                return 3
            order.voice_id = args.voice
        _print(orchestrator.start(order))
        return 0
    if args.command == "status":
        _print(orchestrator.store.load(args.run_id))
        return 0
    if args.command == "approve-research":
        _print(orchestrator.resume_research(args.run_id, True, notes=args.notes))
        return 0
    if args.command == "reject-research":
        _print(orchestrator.resume_research(args.run_id, False, notes=args.notes))
        return 0
    if args.command == "publish":
        _print(
            orchestrator.publish(
                args.run_id, filename=args.filename, feedback=args.feedback
            )
        )
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
