"""Small command-line surface for validating the initial scaffold."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from content_creator.routing import load_catalog, select_route


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="content-creator")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("doctor", help="validate the repository configuration")

    plan = subcommands.add_parser("plan", help="show a deterministic model route")
    plan.add_argument("--provider", default=None)
    plan.add_argument(
        "--complexity",
        choices=("simple", "standard", "deep"),
        default="standard",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = repository_root()
    catalog = load_catalog(root / "config" / "providers.json")

    if args.command == "doctor":
        load_catalog(root / "packs" / "general-text" / "pack.json")
        load_catalog(root / "profiles" / "registry.json")
        load_catalog(root / "rubrics" / "core.json")
        print("Configuration OK")
        return 0

    provider = args.provider or catalog["default_provider"]
    route = select_route(catalog, provider, args.complexity)
    print(json.dumps(route.__dict__, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
