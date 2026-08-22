"""Implement the provider command family."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Callable, Sequence

from ..configuration import persist_default_provider
from ..providers import ProviderError, ProviderRegistry


def register(subparsers: Any, providers: Sequence[str]) -> None:
    """Register the provider workflow.

    Args:
        subparsers (Any): The argparse subparser collection receiving the command.
        providers (Sequence[str]): The providers value passed to register.

    Returns:
        None: The callable updates register state and returns no value.
    """
    parser = subparsers.add_parser("provider", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="provider_command", required=True)
    select = commands.add_parser("select", help="Persist the workspace default provider")
    select.add_argument("provider_name", choices=providers)
    verify = commands.add_parser("verify")
    verify.add_argument("provider_name", choices=providers)


def run(root: Path, args: argparse.Namespace, emit: Callable[[Any], None]) -> int:
    """Run the provider workflow.

    Args:
        root (Path): The workspace root directory.
        args (argparse.Namespace): The parsed command-line arguments.
        emit (Callable[[Any], None]): The emit value passed to run.

    Returns:
        int: The process exit status, where zero indicates successful handling.
    """
    provider_name = args.provider_name
    if args.provider_command == "select":
        path = persist_default_provider(root, provider_name)
        emit({"status": "ok", "provider": provider_name, "persisted_to": str(path)})
        return 0
    if provider_name in {"anthropic", "openai"}:
        variable = "{}_API_KEY".format(provider_name.upper())
        configured = bool(os.getenv(variable))
        emit({"provider": provider_name, "configured": configured, "credential_variable": variable})
        return 0 if configured else 8
    try:
        selected = ProviderRegistry(root=root).get(provider_name)
        authentication = selected.verify()
    except ProviderError as exc:
        emit({"provider": provider_name, "configured": False, "error": str(exc)})
        return 8
    emit({"provider": provider_name, "configured": True, **authentication})
    return 0
