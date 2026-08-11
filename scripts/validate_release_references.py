"""Reject stale Core versions in active release-facing documentation."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION_FILE = ROOT / "src" / "content_creator" / "version.py"
ACTIVE_RELEASE_DOCUMENTS = (
    ROOT / "docs" / "guides" / "creating-a-content-workspace.md",
    ROOT / "docs" / "guides" / "workspace-dependencies.md",
    ROOT / "docs" / "core" / "README.md",
)
REFERENCE_PATTERNS = (
    re.compile(r"content-creator==(?P<version>\d+\.\d+\.\d+)"),
    re.compile(r"--core-ref v(?P<version>\d+\.\d+\.\d+)"),
    re.compile(r"workspace upgrade --to v(?P<version>\d+\.\d+\.\d+)"),
    re.compile(r"immutable `v(?P<version>\d+\.\d+\.\d+)` release"),
)


def package_version() -> str:
    """Return the package version without importing the package."""
    match = re.search(
        r'^VERSION\s*=\s*"(?P<version>\d+\.\d+\.\d+)"$',
        VERSION_FILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    if not match:
        raise ValueError("Could not read the package version")
    return match.group("version")


def stale_references(version: str) -> list[str]:
    """Return active documentation references that do not match the package."""
    stale = []
    for path in ACTIVE_RELEASE_DOCUMENTS:
        text = path.read_text(encoding="utf-8")
        for pattern in REFERENCE_PATTERNS:
            for match in pattern.finditer(text):
                if match.group("version") != version:
                    line = text.count("\n", 0, match.start()) + 1
                    stale.append(
                        "{}:{} references {} (expected {})".format(
                            path.relative_to(ROOT),
                            line,
                            match.group("version"),
                            version,
                        )
                    )
    return stale


def main() -> int:
    """Validate release-facing documentation against the package version."""
    version = package_version()
    stale = stale_references(version)
    if stale:
        raise SystemExit("Stale active release references:\n- " + "\n- ".join(stale))
    print("Active release references match content-creator {}".format(version))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
