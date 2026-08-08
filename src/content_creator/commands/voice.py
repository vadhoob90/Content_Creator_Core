"""Implement the voice command family."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..orchestrator import Orchestrator
from ..voice_builder import VoiceBuilder
from ..voices import VoiceRegistry
from .voice_context import VoiceCommandContext
from .voice_onboarding import create, onboard
from .voice_operations import (
    VoiceHandler,
    add_sources,
    approve,
    assess,
    build,
    configure_score,
    consolidate_learnings,
    deactivate,
    list_voices,
    reactivate,
    reject,
    show_diff,
    show_profile,
    show_signature,
    show_status,
    train_model,
    verify,
    verify_all,
)
from .voice_parser import register as register

ROUTES: dict[str, VoiceHandler] = {
    "add-sources": add_sources,
    "approve": approve,
    "assess": assess,
    "build": build,
    "consolidate-learnings": consolidate_learnings,
    "create": create,
    "deactivate": deactivate,
    "diff": show_diff,
    "list": list_voices,
    "onboard": onboard,
    "reactivate": reactivate,
    "reject": reject,
    "rebuild": build,
    "score": assess,
    "score-config": configure_score,
    "show": show_profile,
    "signature": show_signature,
    "status": show_status,
    "train-ml": train_model,
    "verify": verify,
    "verify-all": verify_all,
}


def command_needs_model(arguments: argparse.Namespace) -> bool:
    """Return the command needs model.

    Args:
        arguments (argparse.Namespace): The arguments value passed to command needs
            model.

    Returns:
        bool: Whether command needs model satisfies the documented condition.
    """
    return arguments.voice_command in {"build", "rebuild"} or (
        arguments.voice_command == "create" and not arguments.no_build
    )


def run(root: Path, arguments: argparse.Namespace) -> int:
    """Run the voice workflow.

    Args:
        root (Path): The workspace root directory.
        arguments (argparse.Namespace): The arguments value passed to run.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    runner = None
    if not getattr(arguments, "offline_analysis", False) and command_needs_model(arguments):
        runner = Orchestrator(root).runner
    context = VoiceCommandContext(
        root=root,
        arguments=arguments,
        builder=VoiceBuilder(root, runner=runner, provider=getattr(arguments, "provider", None)),
        registry=VoiceRegistry(root),
    )
    handler = ROUTES.get(arguments.voice_command)
    return handler(context) if handler else 2
