"""Compose the command-line parser from focused command-family registrations."""

from __future__ import annotations

import argparse

from ..version import VERSION
from . import (
    context_commands,
    operations,
    personalisation,
    perspective,
    provider,
    schema,
    visual,
    voice,
)
from .lifecycle_parser import (
    register_coordinator,
    register_diagnostics,
    register_evaluation,
    register_packs,
    register_publication,
    register_run,
)
from .shared import PROVIDERS, AuthorHelpFormatter
from .workspace_parser import register_agents, register_experience, register_workspace


def build_parser() -> argparse.ArgumentParser:
    """Build the parser workflow.

    Returns:
        argparse.ArgumentParser: The constructed argument parser for parser.
    """
    parser = argparse.ArgumentParser(prog="content-creator", formatter_class=AuthorHelpFormatter)
    parser.add_argument("--version", action="version", version="%(prog)s {}".format(VERSION))
    parser.add_argument("--root", "--workspace", dest="root")
    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
        metavar=(
            "{start,overview,personalisation,context,workspace,doctor,run,status,submission,publish,learn,"
            "revise,verify-publications,diagnostics,visual,coordinator,schema,operations,advanced}"
        ),
    )
    schema.register(subparsers)
    operations.register(subparsers)
    register_workspace(subparsers)
    register_agents(subparsers)
    provider.register(subparsers, PROVIDERS)
    register_experience(subparsers)
    personalisation.register(subparsers)
    context_commands.register(subparsers)
    register_coordinator(subparsers)
    register_diagnostics(subparsers)
    register_packs(subparsers)
    voice.register(subparsers)
    perspective.register(subparsers)
    register_run(subparsers)
    register_publication(subparsers)
    visual.register(subparsers)
    register_evaluation(subparsers)
    return parser
