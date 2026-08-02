"""Compatibility façade and typed router for perspective commands."""

from __future__ import annotations

import argparse
from pathlib import Path

from ..perspectives import PerspectiveError, PerspectiveRegistry
from ..voices import VoiceRegistry
from .perspective_operations import (
    PerspectiveCommandContext,
    PerspectiveHandler,
    approve,
    create,
    create_comparison,
    deactivate,
    list_perspectives,
    record_comparison,
    retire,
    show,
    show_catalogue,
    show_proposals,
    show_status,
    stage_proposal,
    verify,
    verify_catalogue,
)
from .perspective_parser import register as register

COMPARISON_ROUTES: dict[str, PerspectiveHandler] = {
    "compare-create": create_comparison,
    "compare-record": record_comparison,
}
ROUTES: dict[str, PerspectiveHandler] = {
    "approve": approve,
    "catalogue": show_catalogue,
    "create": create,
    "deactivate": deactivate,
    "list": list_perspectives,
    "proposals": show_proposals,
    "retire": retire,
    "show": show,
    "stage-proposal": stage_proposal,
    "status": show_status,
    "verify": verify,
    "verify-catalogue": verify_catalogue,
}


def _context(root: Path, arguments: argparse.Namespace) -> PerspectiveCommandContext:
    resolved_voice = VoiceRegistry(root).resolve(arguments.voice)
    if not resolved_voice.get("perspectives_allowed", True):
        raise PerspectiveError(
            f"Perspectives are disabled for starter voice {arguments.voice} until a "
            "source-derived voice is reviewed and activated"
        )
    return PerspectiveCommandContext(
        root=root,
        arguments=arguments,
        registry=PerspectiveRegistry(root, arguments.voice),
    )


def run(root: Path, arguments: argparse.Namespace) -> int:
    comparison_handler = COMPARISON_ROUTES.get(arguments.perspective_command)
    if comparison_handler:
        return comparison_handler(PerspectiveCommandContext(root, arguments))
    handler = ROUTES.get(arguments.perspective_command)
    return handler(_context(root, arguments)) if handler else 2
