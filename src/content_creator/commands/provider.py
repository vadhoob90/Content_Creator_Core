"""Provider command family."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Any, Callable, Sequence

import yaml

from ..configuration import ConfigurationError
from ..providers import ProviderError, ProviderRegistry
from ..storage import RunStore


def register(subparsers: Any, providers: Sequence[str]) -> None:
    parser = subparsers.add_parser("provider", help=argparse.SUPPRESS)
    commands = parser.add_subparsers(dest="provider_command", required=True)
    select = commands.add_parser("select", help="Persist the workspace default provider")
    select.add_argument("provider_name", choices=providers)
    verify = commands.add_parser("verify")
    verify.add_argument("provider_name", choices=providers)


def run(root: Path, args: argparse.Namespace, emit: Callable[[Any], None]) -> int:
    provider_name = args.provider_name
    if args.provider_command == "select":
        path = root / "content-creator.yaml"
        configuration = (
            yaml.safe_load(path.read_text(encoding="utf-8")) or {} if path.exists() else {}
        )
        if not isinstance(configuration, dict):
            raise ConfigurationError("content-creator.yaml must contain a mapping")
        provider_configuration = configuration.get("provider", {}) or {}
        if not isinstance(provider_configuration, dict):
            raise ConfigurationError("provider configuration must be a mapping")
        provider_configuration["default"] = provider_name
        configuration["provider"] = provider_configuration
        RunStore._atomic_text(path, yaml.safe_dump(configuration, sort_keys=False))
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
