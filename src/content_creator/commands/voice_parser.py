"""Register voice command arguments in cohesive groups."""

from __future__ import annotations

import argparse

from .shared import PROVIDERS


def _register_onboard(commands: argparse._SubParsersAction) -> None:
    onboard = commands.add_parser("onboard", help="Choose a starter or source-derived voice route")
    onboard.add_argument("voice_id")
    onboard.add_argument("--strategy", choices=["starter", "source-derived"], required=True)
    onboard.add_argument("--author-name", required=True)
    onboard.add_argument("--label")
    onboard.add_argument("--selected-by", default="repository-owner")
    onboard.add_argument("--use", action="append", default=[])
    onboard.add_argument(
        "--statistical-voice-score",
        choices=["disabled", "deterministic", "ml"],
        default="disabled",
    )


def _register_create(commands: argparse._SubParsersAction) -> None:
    create = commands.add_parser("create")
    create.add_argument("--name", help="Legacy shorthand for author, label, and id")
    create.add_argument("--voice-id")
    create.add_argument("--label")
    create.add_argument("--author-name")
    create.add_argument("--author-alias", action="append", default=[])
    create.add_argument("--authorised-by")
    create.add_argument("--use", action="append", default=[])
    create.add_argument("--sources")
    create.add_argument("--documents", action="append", default=[])
    create.add_argument("--no-build", action="store_true")
    create.add_argument("--provider", choices=PROVIDERS)
    create.add_argument(
        "--statistical-voice-score",
        choices=["disabled", "deterministic", "ml"],
        default="disabled",
    )
    create.add_argument("--offline-analysis", action="store_true")


def _register_build_and_assessment(commands: argparse._SubParsersAction) -> None:
    for command_name in ("build", "rebuild", "status", "show", "signature", "verify"):
        command = commands.add_parser(command_name)
        command.add_argument("voice_id")
        if command_name in {"build", "rebuild"}:
            command.add_argument("--provider", choices=PROVIDERS)
            command.add_argument("--offline-analysis", action="store_true")
    assess = commands.add_parser("assess")
    assess.add_argument("voice_id")
    assess.add_argument("--draft", required=True)
    assess.add_argument("--voice-version")
    score = commands.add_parser("score")
    score.add_argument("voice_id")
    score.add_argument("--draft", required=True)
    score.add_argument("--voice-version")
    score.add_argument("--method", choices=["deterministic", "ml"], required=True)
    score_config = commands.add_parser("score-config")
    score_config.add_argument("voice_id")
    score_config.add_argument("--method", choices=["deterministic", "ml"])
    score_state = score_config.add_mutually_exclusive_group(required=True)
    score_state.add_argument("--enable", action="store_true")
    score_state.add_argument("--disable", action="store_true")
    score_config.add_argument("--selected-by")


def _register_training(commands: argparse._SubParsersAction) -> None:
    train = commands.add_parser("train-ml")
    train.add_argument("voice_id")
    train.add_argument("--voice-version")
    train.add_argument("--comparison-documents", action="append", required=True)
    train.add_argument("--accept-low-confidence", action="store_true")
    train.add_argument("--replace", action="store_true")


def _register_lifecycle(commands: argparse._SubParsersAction) -> None:
    commands.add_parser("list")
    commands.add_parser("verify-all")
    approve = commands.add_parser("approve")
    approve.add_argument("voice_id")
    approve.add_argument("--approved-by", default="repository-owner")
    approve.add_argument("--override-evaluation", action="store_true")
    approve.add_argument("--reason")
    deactivate = commands.add_parser("deactivate")
    deactivate.add_argument("voice_id")
    deactivate.add_argument("--reason", required=True)
    reactivate = commands.add_parser("reactivate")
    reactivate.add_argument("voice_id")
    reactivate.add_argument("--approved-by", default="repository-owner")
    add_sources = commands.add_parser("add-sources")
    add_sources.add_argument("voice_id")
    add_sources.add_argument("--sources")
    add_sources.add_argument("--documents", action="append", default=[])
    diff = commands.add_parser("diff")
    diff.add_argument("voice_id")
    diff.add_argument("--from", dest="from_version", required=True)
    diff.add_argument("--to", dest="to_version", required=True)
    consolidate = commands.add_parser("consolidate-learnings")
    consolidate.add_argument("voice_id")


def register(subparsers: argparse._SubParsersAction) -> None:
    voice = subparsers.add_parser("voice", help=argparse.SUPPRESS)
    commands = voice.add_subparsers(dest="voice_command", required=True)
    _register_onboard(commands)
    _register_create(commands)
    _register_build_and_assessment(commands)
    _register_training(commands)
    _register_lifecycle(commands)
