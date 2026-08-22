"""Evaluate declared inward dependency boundaries for Content Creator Core."""

from __future__ import annotations

from typing import Any

ENTRY_POINT_PATTERNS = (
    "content_creator.cli",
    "content_creator.commands.*",
)
CONCRETE_PROVIDER_PATTERNS = (
    "content_creator.providers.anthropic",
    "content_creator.providers.bedrock",
    "content_creator.providers.claude_native",
    "content_creator.providers.codex_native",
    "content_creator.providers.fake",
    "content_creator.providers.native_cli",
    "content_creator.providers.openai",
)

DEPENDENCY_BOUNDARIES: tuple[dict[str, Any], ...] = (
    {
        "name": "domain-is-independent",
        "sources": ("content_creator.domain",),
        "allowed_targets": (),
    },
    {
        "name": "storage-points-inward",
        "sources": ("content_creator.storage",),
        "allowed_targets": ("content_creator.domain",),
    },
    {
        "name": "entrypoints-are-terminal",
        "sources": ("content_creator.*",),
        "excluded_sources": ENTRY_POINT_PATTERNS,
        "forbidden_targets": ENTRY_POINT_PATTERNS,
    },
    {
        "name": "providers-do-not-drive-workflows",
        "sources": ("content_creator.providers.*",),
        "forbidden_targets": (
            *ENTRY_POINT_PATTERNS,
            "content_creator.orchestrator",
            "content_creator.orchestration_support",
        ),
    },
    {
        "name": "application-uses-provider-boundary",
        "sources": ("content_creator.*",),
        "excluded_sources": ("content_creator.providers.*",),
        "forbidden_targets": CONCRETE_PROVIDER_PATTERNS,
    },
)


def _matches(module: str, pattern: str) -> bool:
    """Return whether one module matches an exact or descendant pattern."""
    if pattern.endswith(".*"):
        prefix = pattern[:-2]
        return module == prefix or module.startswith(prefix + ".")
    return module == pattern


def _matches_any(module: str, patterns: tuple[str, ...]) -> bool:
    """Return whether one module matches any declared pattern."""
    return any(_matches(module, pattern) for pattern in patterns)


def _module_edges(module: dict[str, Any]) -> list[dict[str, Any]]:
    """Return line-aware edges while accepting reports written before edge evidence."""
    edges = module.get("import_edges")
    if edges is not None:
        return list(edges)
    return [{"target": target, "line": None} for target in module.get("imports", [])]


def dependency_boundary_violations(modules: list[dict[str, Any]]) -> list[str]:
    """Return violations of declared source-to-target dependency boundaries."""
    violations = []
    for module in modules:
        source = str(module["module"])
        path = str(module.get("path", source))
        for rule in DEPENDENCY_BOUNDARIES:
            if not _matches_any(source, rule["sources"]):
                continue
            if _matches_any(source, rule.get("excluded_sources", ())):
                continue
            for edge in _module_edges(module):
                target = str(edge["target"])
                allowed = rule.get("allowed_targets")
                forbidden = rule.get("forbidden_targets", ())
                rejected = allowed is not None and not _matches_any(target, allowed)
                rejected = rejected or _matches_any(target, forbidden)
                if not rejected:
                    continue
                location = path
                if edge.get("line") is not None:
                    location = "{}:{}".format(path, edge["line"])
                violations.append(
                    "dependency boundary {!r}: {} imports {} -> {}".format(
                        rule["name"], location, source, target
                    )
                )
    return sorted(set(violations))
