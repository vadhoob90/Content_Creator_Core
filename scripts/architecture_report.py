#!/usr/bin/env python3
"""Report package size and internal import dependencies without third-party tools."""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "content_creator"
PACKAGE_NAME = "content_creator"


def module_name(path: Path) -> str:
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join([PACKAGE_NAME, *parts]) if parts else PACKAGE_NAME


def internal_imports(path: Path, tree: ast.AST) -> list[str]:
    current = module_name(path)
    package_parts = current.split(".") if path.name == "__init__.py" else current.split(".")[:-1]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if alias.name.startswith(PACKAGE_NAME)
            )
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                keep = len(package_parts) - (node.level - 1)
                base = package_parts[:keep]
                target = ".".join([*base, *(node.module or "").split(".")]).rstrip(".")
            else:
                target = node.module or ""
            if target.startswith(PACKAGE_NAME) and target != current:
                imports.add(target)
    return sorted(imports)


def build_report() -> dict:
    modules = []
    for path in sorted(PACKAGE_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        modules.append(
            {
                "module": module_name(path),
                "path": str(path.relative_to(ROOT)),
                "line_count": len(source.splitlines()),
                "imports": internal_imports(path, tree),
            }
        )
    return {
        "package": PACKAGE_NAME,
        "summary": {
            "module_count": len(modules),
            "line_count": sum(module["line_count"] for module in modules),
        },
        "modules": modules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()
    report = build_report()
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print("{module_count} modules, {line_count} lines".format(**report["summary"]))
    for module in sorted(report["modules"], key=lambda item: item["line_count"], reverse=True):
        print("{line_count:5}  {module}".format(**module))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
