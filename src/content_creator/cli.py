from __future__ import annotations

import argparse
import difflib
import json
import os
from pathlib import Path
from typing import Optional

import yaml

from .agent_resources import STANDARD_TEMPLATE, AgentWorkspace
from .configuration import Configuration
from .domain import (
    AuthorContribution,
    PerspectiveSelection,
    ResearchDepth,
    ResearchSource,
    WorkOrder,
)
from .evaluation import run_live_suite, run_replay_suite
from .intake import ClarificationRequired
from .learning import LearningMemory
from .orchestrator import Orchestrator
from .packs import PackRegistry
from .perspective_assessment import (
    create_blind_comparison,
    record_blind_comparison,
)
from .perspectives import (
    PerspectiveCatalogueStore,
    PerspectiveEntry,
    PerspectiveManifest,
    PerspectiveProposalStore,
    PerspectiveProvenance,
    PerspectiveRegistry,
)
from .providers import ProviderError, ProviderRegistry
from .resource_paths import ResourceResolver
from .storage import RunStore
from .voice_builder import VoiceBuilder
from .voices import (
    Authorisation,
    VoiceManifest,
    VoiceRegistry,
    VoiceWorkOrder,
    hash_file,
    voice_id_for,
)
from .workspace import (
    DEFAULT_CORE_REF,
    DEFAULT_CORE_URL,
    WorkspaceScaffolder,
    initialise_workspace,
)

PROVIDERS = ["anthropic", "openai", "codex-native", "claude-native"]


def _root(value: Optional[str]) -> Path:
    return Path(value or ".").resolve()


def _print(value) -> None:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    print(json.dumps(value, indent=2, default=str))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="content-creator")
    parser.add_argument(
        "--root",
        "--workspace",
        dest="root",
        help="Content workspace (default: current directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    initialise = sub.add_parser(
        "init", help="Initialise a repository-owned content workspace"
    )
    initialise.add_argument(
        "--agent-template",
        default=STANDARD_TEMPLATE,
        help="Packaged agent template to scaffold (default: standard)",
    )

    workspace = sub.add_parser(
        "workspace",
        help="Create a complete thin repository that consumes Content Creator Core",
    )
    workspace_sub = workspace.add_subparsers(
        dest="workspace_command",
        required=True,
    )
    workspace_create = workspace_sub.add_parser(
        "create",
        help="Scaffold a new author-owned content repository",
    )
    workspace_create.add_argument(
        "directory",
        help="Destination directory; created when it does not exist",
    )
    workspace_create.add_argument(
        "--name",
        help="Repository display name (default: destination directory name)",
    )
    workspace_create.add_argument("--author-name", required=True)
    workspace_create.add_argument("--voice-id")
    workspace_create.add_argument("--voice-label")
    workspace_create.add_argument(
        "--pack",
        action="append",
        default=[],
        help="Content pack to enable; repeat for several (default: general-text)",
    )
    workspace_create.add_argument(
        "--agent-template",
        default=STANDARD_TEMPLATE,
        help="Packaged agent template to scaffold (default: standard)",
    )
    workspace_create.add_argument(
        "--core-url",
        default=DEFAULT_CORE_URL,
        help="Git URL for the Content Creator Core dependency",
    )
    workspace_create.add_argument(
        "--core-ref",
        default=DEFAULT_CORE_REF,
        help="Immutable Core tag or commit to pin (default: installed version tag)",
    )
    workspace_create.add_argument(
        "--perspective-mode",
        choices=["automatic", "explicit", "disabled"],
        default="automatic",
        help="Perspective selection policy for the new workspace",
    )

    agents = sub.add_parser(
        "agents", help="Scaffold and inspect repository-owned agents"
    )
    agent_sub = agents.add_subparsers(dest="agent_command", required=True)
    for command in ("scaffold", "status", "diff-template"):
        item = agent_sub.add_parser(command)
        item.add_argument(
            "--template",
            default=STANDARD_TEMPLATE,
            help="Packaged agent template (default: standard)",
        )

    provider = sub.add_parser("provider", help="Verify provider configuration")
    provider_sub = provider.add_subparsers(dest="provider_command", required=True)
    provider_verify = provider_sub.add_parser("verify")
    provider_verify.add_argument("provider_name", choices=PROVIDERS)

    plan = sub.add_parser("plan", help="Turn natural language into a work order")
    plan.add_argument("request")
    plan.add_argument("--provider", choices=PROVIDERS)

    sub.add_parser("doctor", help="Validate offline configuration and assets")
    sub.add_parser("packs", help="List installed content packs")

    pack = sub.add_parser("pack", help="Inspect content packs")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)
    pack_sub.add_parser("list")
    pack_show = pack_sub.add_parser("show")
    pack_show.add_argument("pack_id")
    pack_show.add_argument("--resolved", action="store_true")
    pack_validate = pack_sub.add_parser("validate")
    pack_validate.add_argument("pack_id")
    pack_create = pack_sub.add_parser("create")
    pack_create.add_argument("pack_id")
    pack_create.add_argument("--extends", default="general-text")

    voice = sub.add_parser("voice", help="Create, approve, and manage voices")
    voice_sub = voice.add_subparsers(dest="voice_command", required=True)
    voice_create = voice_sub.add_parser("create")
    voice_create.add_argument(
        "--name",
        help="Legacy shorthand for author name, display label, and generated id",
    )
    voice_create.add_argument("--voice-id", help="Stable local voice identifier")
    voice_create.add_argument("--label", help="Human-facing voice label")
    voice_create.add_argument(
        "--author-name",
        help="Author/byline identity used for attribution",
    )
    voice_create.add_argument(
        "--author-alias",
        action="append",
        default=[],
        help="Additional authorised byline or transcript identity",
    )
    voice_create.add_argument("--authorised-by")
    voice_create.add_argument("--use", action="append", default=[])
    voice_create.add_argument("--sources")
    voice_create.add_argument("--documents", action="append", default=[])
    voice_create.add_argument("--no-build", action="store_true")
    voice_create.add_argument("--provider", choices=PROVIDERS)
    voice_create.add_argument(
        "--offline-analysis",
        action="store_true",
        help="Use deterministic fixture analysis instead of an LLM",
    )
    for command in ("build", "rebuild", "status", "show", "signature", "verify"):
        item = voice_sub.add_parser(command)
        item.add_argument("voice_id")
        if command in {"build", "rebuild"}:
            item.add_argument("--provider", choices=PROVIDERS)
            item.add_argument("--offline-analysis", action="store_true")
    voice_sub.add_parser("list")
    voice_approve = voice_sub.add_parser("approve")
    voice_approve.add_argument("voice_id")
    voice_approve.add_argument("--approved-by", default="repository-owner")
    voice_approve.add_argument("--override-evaluation", action="store_true")
    voice_approve.add_argument("--reason")
    voice_deactivate = voice_sub.add_parser("deactivate")
    voice_deactivate.add_argument("voice_id")
    voice_deactivate.add_argument("--reason", required=True)
    voice_reactivate = voice_sub.add_parser("reactivate")
    voice_reactivate.add_argument("voice_id")
    voice_reactivate.add_argument("--approved-by", default="repository-owner")
    voice_add = voice_sub.add_parser("add-sources")
    voice_add.add_argument("voice_id")
    voice_add.add_argument("--sources")
    voice_add.add_argument("--documents", action="append", default=[])
    voice_diff = voice_sub.add_parser("diff")
    voice_diff.add_argument("voice_id")
    voice_diff.add_argument("--from", dest="from_version", required=True)
    voice_diff.add_argument("--to", dest="to_version", required=True)
    voice_consolidate = voice_sub.add_parser("consolidate-learnings")
    voice_consolidate.add_argument("voice_id")

    perspective = sub.add_parser(
        "perspective",
        help="Manage context-isolated author perspectives",
    )
    perspective_sub = perspective.add_subparsers(
        dest="perspective_command", required=True
    )
    perspective_create = perspective_sub.add_parser("create")
    perspective_create.add_argument("--voice", required=True)
    perspective_create.add_argument("--context", required=True)
    perspective_create.add_argument("--display-name")
    perspective_create.add_argument("--statement")
    perspective_create.add_argument("--type", default="position")
    perspective_create.add_argument("--topic", action="append", default=[])
    perspective_create.add_argument("--qualification", action="append", default=[])
    perspective_create.add_argument("--counterposition", action="append", default=[])
    perspective_create.add_argument("--evidence")
    perspective_list = perspective_sub.add_parser("list")
    perspective_list.add_argument("--voice", required=True)
    perspective_catalogue = perspective_sub.add_parser("catalogue")
    perspective_catalogue.add_argument("--voice", required=True)
    perspective_verify_catalogue = perspective_sub.add_parser(
        "verify-catalogue"
    )
    perspective_verify_catalogue.add_argument("--voice", required=True)
    for command in ("status", "show", "verify", "proposals"):
        item = perspective_sub.add_parser(command)
        item.add_argument("--voice", required=True)
        item.add_argument("--context", required=True)
    perspective_approve = perspective_sub.add_parser("approve")
    perspective_approve.add_argument("--voice", required=True)
    perspective_approve.add_argument("--context", required=True)
    perspective_approve.add_argument(
        "--approved-by", default="repository-owner"
    )
    perspective_deactivate = perspective_sub.add_parser("deactivate")
    perspective_deactivate.add_argument("--voice", required=True)
    perspective_deactivate.add_argument("--context", required=True)
    perspective_deactivate.add_argument("--reason", required=True)
    perspective_stage = perspective_sub.add_parser("stage-proposal")
    perspective_stage.add_argument("--voice", required=True)
    perspective_stage.add_argument("--context", required=True)
    perspective_stage.add_argument("--proposal", required=True)
    perspective_retire = perspective_sub.add_parser("retire")
    perspective_retire.add_argument("--voice", required=True)
    perspective_retire.add_argument("--context", required=True)
    perspective_retire.add_argument("--entry", required=True)
    perspective_retire.add_argument("--reason", required=True)
    perspective_compare = perspective_sub.add_parser("compare-create")
    perspective_compare.add_argument("--run", required=True)
    perspective_compare.add_argument("--baseline", required=True)
    perspective_record = perspective_sub.add_parser("compare-record")
    perspective_record.add_argument("--run", required=True)
    perspective_record.add_argument("--assessment", required=True)

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
    parser.add_argument("request", nargs="?")
    parser.add_argument("--brief", help="JSON or YAML content brief")
    parser.add_argument("--topic")
    parser.add_argument("--pack")
    parser.add_argument("--voice", default="default")
    parser.add_argument("--voice-version")
    parser.add_argument("--perspective-context", action="append", default=[])
    parser.add_argument("--perspective-version")
    parser.add_argument("--no-perspective", action="store_true")
    parser.add_argument("--thesis")
    parser.add_argument("--intended-challenge")
    parser.add_argument("--personal-basis")
    parser.add_argument("--author-supplied", action="store_true")
    parser.add_argument("--perspective-entry", action="append", default=[])
    parser.add_argument("--format", choices=["text", "post", "article"])
    parser.add_argument("--research", choices=["none", "light", "deep"])
    parser.add_argument("--research-source", choices=["none", "supplied", "agent"])
    parser.add_argument("--research-file")
    parser.add_argument("--provider", choices=PROVIDERS)
    parser.add_argument("--objective")
    parser.add_argument("--audience")
    parser.add_argument("--language")
    parser.add_argument("--structure")
    parser.add_argument("--destination")
    parser.add_argument("--length", help="Word range such as 700:900")


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    root = _root(args.root)
    if args.command == "init":
        _print(initialise_workspace(root, args.agent_template))
        return 0
    if args.command == "workspace":
        destination = Path(args.directory).expanduser()
        if not destination.is_absolute():
            destination = (
                root / destination
                if args.root
                else Path.cwd() / destination
            )
        destination = destination.resolve()
        _print(
            WorkspaceScaffolder(destination).create(
                name=args.name or destination.name,
                author_name=args.author_name,
                voice_id=args.voice_id,
                voice_label=args.voice_label,
                packs=args.pack,
                agent_template=args.agent_template,
                core_url=args.core_url,
                core_ref=args.core_ref,
                perspective_mode=args.perspective_mode,
            )
        )
        return 0
    if args.command == "agents":
        workspace = AgentWorkspace(root)
        if args.agent_command == "scaffold":
            _print(workspace.scaffold(args.template))
        elif args.agent_command == "status":
            _print(workspace.status(args.template))
        else:
            _print(workspace.diff_template(args.template))
        return 0
    if args.command == "provider":
        provider_name = args.provider_name
        if provider_name in {"anthropic", "openai"}:
            variable = "{}_API_KEY".format(provider_name.upper())
            configured = bool(os.getenv(variable))
            _print(
                {
                    "provider": provider_name,
                    "configured": configured,
                    "credential_variable": variable,
                }
            )
            return 0 if configured else 8
        try:
            provider = ProviderRegistry(root=root).get(provider_name)
            authentication = provider.verify()
        except ProviderError as exc:
            _print(
                {
                    "provider": provider_name,
                    "configured": False,
                    "error": str(exc),
                }
            )
            return 8
        _print(
            {
                "provider": provider_name,
                "configured": True,
                **authentication,
            }
        )
        return 0
    if args.command == "doctor":
        configuration = Configuration(root)
        packs = PackRegistry(root).list()
        resources = ResourceResolver(root)
        voice = resources.path("profiles/default/voice.md")
        checks = {
            "model_catalogue": bool(configuration.models),
            "content_packs": [pack.id for pack in packs],
            "default_voice": voice.exists(),
            "route_cases": resources.path(
                "evals/cases/route-matrix.yaml"
            ).exists(),
            "repository_agents": AgentWorkspace(root).status(),
        }
        healthy = (
            checks["model_catalogue"]
            and bool(checks["content_packs"])
            and checks["default_voice"]
            and checks["route_cases"]
            and checks["repository_agents"]["complete"]
        )
        _print({"status": "ok" if healthy else "error", "checks": checks})
        return 0 if healthy else 1
    if args.command == "packs":
        _print([pack.model_dump(mode="json") for pack in PackRegistry(root).list()])
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
            _print(packs.resolve(pack_id))
            return 0
        if args.pack_command == "list":
            _print([item.model_dump(mode="json") for item in packs.list()])
        else:
            item = (
                packs.resolve(args.pack_id)
                if args.pack_command in {"show", "validate"} or args.resolved
                else packs.get(args.pack_id)
            )
            _print(item)
        return 0
    if args.command == "voice":
        return _voice_command(root, args)
    if args.command == "perspective":
        return _perspective_command(root, args)
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
        if args.brief:
            data = yaml.safe_load(
                Path(args.brief).read_text(encoding="utf-8")
            )
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
                args.research_source
                or ("none" if depth == ResearchDepth.NONE else "agent")
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
                _print({"needs_clarification": True, "questions": exc.questions})
                return 3
            order.voice_id = args.voice
            order.voice_version = args.voice_version
        if args.no_perspective:
            order.perspective_mode = "disabled"
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
                raise ValueError(
                    "--perspective-version requires exactly one --perspective-context"
                )
            order.perspective_version = args.perspective_version
        if (
            args.thesis
            or args.intended_challenge
            or args.personal_basis
            or args.perspective_entry
        ):
            order.author_contribution = AuthorContribution(
                thesis=args.thesis,
                intended_challenge=args.intended_challenge,
                personal_basis=args.personal_basis,
                supplied_by_author=args.author_supplied,
                reusable_perspective_entry_ids=args.perspective_entry,
                provenance_notes=["Supplied through the run command"],
            )
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


def _source_lines(path: Optional[str]) -> list:
    if not path:
        return []
    return [
        line.strip()
        for line in Path(path).read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _documents(values: list) -> list:
    result = []
    for value in values:
        path = Path(value)
        if path.is_dir():
            result.extend(
                str(item)
                for item in sorted(path.iterdir())
                if item.is_file()
                and item.suffix.lower()
                in {".txt", ".md", ".html", ".pdf", ".docx"}
            )
        else:
            result.append(str(path))
    return result


def _voice_command(root: Path, args) -> int:
    runner = None
    if not getattr(args, "offline_analysis", False) and command_needs_model(args):
        runner = Orchestrator(root).runner
    builder = VoiceBuilder(root, runner=runner, provider=getattr(args, "provider", None))
    registry = VoiceRegistry(root)
    command = args.voice_command
    if command == "create":
        author_name = args.author_name or args.name
        if not author_name:
            raise ValueError(
                "--author-name is required (or use legacy --name)"
            )
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
        )
        builder.save_work_order(order)
        _print(order if args.no_build else builder.build(voice_id))
        return 0
    if command in {"build", "rebuild"}:
        _print(builder.build(args.voice_id))
        return 0
    if command == "list":
        _print(registry.list())
        return 0
    if command == "approve":
        if args.override_evaluation and not args.reason:
            raise ValueError("--override-evaluation requires --reason")
        _print(
            registry.activate(
                args.voice_id,
                args.approved_by,
                args.reason if args.override_evaluation else None,
            )
        )
        return 0
    if command == "deactivate":
        _print(registry.deactivate(args.voice_id, args.reason))
        return 0
    if command == "reactivate":
        _print(registry.activate(args.voice_id, args.approved_by, "reactivation"))
        return 0
    if command == "add-sources":
        order = builder.load_work_order(args.voice_id)
        order.urls.extend(item for item in _source_lines(args.sources) if item not in order.urls)
        order.documents.extend(
            item for item in _documents(args.documents) if item not in order.documents
        )
        builder.save_work_order(order)
        _print(order)
        return 0
    if command == "consolidate-learnings":
        path = LearningMemory(root, args.voice_id).consolidate_candidate()
        _print(
            {
                "voice_id": args.voice_id,
                "status": "candidate",
                "path": str(path.relative_to(root)),
            }
        )
        return 0
    if command == "diff":
        voice_root = root / "profiles" / args.voice_id

        def profile(version):
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
        candidate_status = (
            VoiceManifest.model_validate_json(manifest_path.read_text()).status.value
            if manifest_path.exists()
            else None
        )
        _print({"voice_id": args.voice_id, "candidate": candidate_status, "active": active})
        return 0
    if command == "show":
        print((candidate / "profile.md").read_text(encoding="utf-8"))
        return 0
    if command == "signature":
        _print(
            json.loads(
                (candidate / "linguistic-signature.json").read_text(encoding="utf-8")
            )
        )
        return 0
    if command == "verify":
        manifest = VoiceManifest.model_validate_json(manifest_path.read_text())
        mismatches = [
            name
            for name, filename in manifest.components.items()
            if hash_file(candidate / filename) != manifest.component_hashes[name]
        ]
        _print({"voice_id": args.voice_id, "valid": not mismatches, "mismatches": mismatches})
        return 0 if not mismatches else 6
    return 2


def _perspective_command(root: Path, args) -> int:
    command = args.perspective_command
    if command == "compare-create":
        baseline = Path(args.baseline)
        if not baseline.is_absolute():
            baseline = root / baseline
        _print(
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
        _print(
            record_blind_comparison(
                root,
                args.run,
                assessment,
            )
        )
        return 0
    registry = PerspectiveRegistry(root, args.voice)
    if command == "catalogue":
        _print(
            PerspectiveCatalogueStore(root, args.voice).load().model_dump(
                mode="json"
            )
        )
        return 0
    if command == "verify-catalogue":
        result = PerspectiveCatalogueStore(root, args.voice).verify()
        _print(result)
        return 0 if result["valid"] else 6
    if command == "create":
        entries = []
        if args.statement:
            if not args.evidence:
                raise ValueError(
                    "--evidence is required when creating a perspective statement"
                )
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
        _print(
            registry.stage(
                args.context,
                entries,
                display_name=args.display_name,
            )
        )
        return 0
    if command == "list":
        _print(registry.list())
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
        _print(
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
        _print(
            {
                "voice_id": args.voice,
                "context_id": args.context,
                "valid": not mismatches,
                "mismatches": mismatches,
            }
        )
        return 0 if not mismatches else 6
    if command == "approve":
        _print(registry.activate(args.context, args.approved_by))
        return 0
    if command == "deactivate":
        _print(registry.deactivate(args.context, args.reason))
        return 0
    if command == "proposals":
        _print(PerspectiveProposalStore(root, args.voice, args.context).list())
        return 0
    if command == "stage-proposal":
        _print(registry.stage_proposal(args.context, args.proposal))
        return 0
    if command == "retire":
        _print(registry.retire_entry(args.context, args.entry, args.reason))
        return 0
    return 2


def command_needs_model(args) -> bool:
    return args.voice_command in {"create", "build", "rebuild"}


if __name__ == "__main__":
    raise SystemExit(main())
