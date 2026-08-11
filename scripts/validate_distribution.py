#!/usr/bin/env python3
"""Validate release artifacts before they are uploaded to a package index."""

from __future__ import annotations

import argparse
import hashlib
import json
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path

REQUIRED_WHEEL_FILES = {
    "content_creator/resources/agent-templates/standard/agents/writer.md",
    "content_creator/resources/config/models.yaml",
    "content_creator/resources/contracts/agent-harness.md",
    "content_creator/resources/contracts/roles/writer.md",
    "content_creator/resources/evals/cases/route-matrix.yaml",
    "content_creator/resources/packs/general-text/pack.json",
    "content_creator/resources/profiles/starter/clear-professional.md",
    "content_creator/resources/rubrics/core.yaml",
    "content_creator/resources/skills/content-creator/SKILL.md",
    "content_creator/resources/skills/voice-builder/SKILL.md",
    "content_creator/resources/visuals/components.json",
}


def _single(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(
            "Expected one {!r} artifact in {}, found {}".format(pattern, directory, len(matches))
        )
    return matches[0]


def _metadata(names: list[str], read) -> str:
    metadata_paths = [name for name in names if name.endswith(".dist-info/METADATA")]
    if len(metadata_paths) != 1:
        raise ValueError("Wheel must contain exactly one METADATA file")
    return read(metadata_paths[0]).decode("utf-8")


def validate(directory: Path, expected_version: str) -> dict[str, object]:
    wheel = _single(directory, "content_creator-*.whl")
    sdist = _single(directory, "content_creator-*.tar.gz")

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
        missing = sorted(REQUIRED_WHEEL_FILES - set(wheel_names))
        if missing:
            raise ValueError(
                "Wheel is missing required packaged resources: {}".format(", ".join(missing))
            )
        metadata = Parser().parsestr(_metadata(wheel_names, archive.read))

    if metadata["Name"] != "content-creator":
        raise ValueError("Unexpected package name: {}".format(metadata["Name"]))
    if metadata["Version"] != expected_version:
        raise ValueError(
            "Expected version {}, found {}".format(expected_version, metadata["Version"])
        )
    if metadata["License-Expression"] != "AGPL-3.0-or-later":
        raise ValueError("Distribution does not declare AGPL-3.0-or-later")
    if not any(
        value == "Repository, https://github.com/vadhoob90/Content_Creator_Core"
        for value in metadata.get_all("Project-URL", [])
    ):
        raise ValueError("Distribution metadata is missing the repository URL")

    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = {"/".join(name.split("/")[1:]) for name in archive.getnames()}
    required_sdist = {
        "LICENSE.md",
        "NOTICE",
        "README.md",
        "pyproject.toml",
        "src/content_creator/version.py",
    }
    missing_sdist = sorted(required_sdist - sdist_names)
    if missing_sdist:
        raise ValueError("Source distribution is missing: {}".format(", ".join(missing_sdist)))

    artifacts = {}
    for path in (wheel, sdist):
        artifacts[path.name] = {
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "size": path.stat().st_size,
        }
    return {
        "package": metadata["Name"],
        "version": metadata["Version"],
        "artifacts": artifacts,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--expected-version", required=True)
    args = parser.parse_args()
    print(
        json.dumps(
            validate(args.directory, args.expected_version),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
