import io
import runpy
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = runpy.run_path(str(ROOT / "scripts" / "validate_distribution.py"))
REQUIRED_WHEEL_FILES = VALIDATOR["REQUIRED_WHEEL_FILES"]
VALIDATE = VALIDATOR["validate"]


def _metadata(
    *,
    name: str = "content-creator",
    version: str = "1.8.0",
    licence: str = "AGPL-3.0-or-later",
    repository: str = "https://github.com/vadhoob90/Content_Creator_Core",
) -> str:
    return "\n".join(
        [
            "Metadata-Version: 2.4",
            f"Name: {name}",
            f"Version: {version}",
            f"License-Expression: {licence}",
            f"Project-URL: Repository, {repository}",
            "",
            "",
        ]
    )


def _wheel(directory: Path, *, metadata: str | None = None, omit: str | None = None) -> Path:
    path = directory / "content_creator-1.8.0-py3-none-any.whl"
    with zipfile.ZipFile(path, "w") as archive:
        for resource in sorted(REQUIRED_WHEEL_FILES - ({omit} if omit else set())):
            archive.writestr(resource, "fixture")
        archive.writestr(
            "content_creator-1.8.0.dist-info/METADATA",
            metadata if metadata is not None else _metadata(),
        )
    return path


def _sdist(directory: Path, *, omit: str | None = None) -> Path:
    path = directory / "content_creator-1.8.0.tar.gz"
    required = {
        "LICENSE.md",
        "NOTICE",
        "README.md",
        "pyproject.toml",
        "src/content_creator/version.py",
    }
    with tarfile.open(path, "w:gz") as archive:
        for relative in sorted(required - ({omit} if omit else set())):
            payload = b"fixture"
            member = tarfile.TarInfo(f"content_creator-1.8.0/{relative}")
            member.size = len(payload)
            archive.addfile(member, io.BytesIO(payload))
    return path


def _distribution(directory: Path, *, metadata: str | None = None) -> None:
    _wheel(directory, metadata=metadata)
    _sdist(directory)


def test_distribution_harness_accepts_complete_artifacts(tmp_path):
    _distribution(tmp_path)

    manifest = VALIDATE(tmp_path, "1.8.0")

    assert manifest["package"] == "content-creator"
    assert manifest["version"] == "1.8.0"
    assert set(manifest["artifacts"]) == {
        "content_creator-1.8.0-py3-none-any.whl",
        "content_creator-1.8.0.tar.gz",
    }
    assert all(item["sha256"] for item in manifest["artifacts"].values())


def test_distribution_harness_rejects_missing_wheel_resource(tmp_path):
    missing = sorted(REQUIRED_WHEEL_FILES)[0]
    _wheel(tmp_path, omit=missing)
    _sdist(tmp_path)

    with pytest.raises(ValueError, match="missing required packaged resources"):
        VALIDATE(tmp_path, "1.8.0")


@pytest.mark.parametrize(
    ("metadata", "message"),
    [
        (_metadata(name="other"), "Unexpected package name"),
        (_metadata(version="9.9.9"), "Expected version 1.8.0"),
        (_metadata(licence="MIT"), "does not declare AGPL"),
        (_metadata(repository="https://example.invalid/repository"), "missing the repository URL"),
    ],
)
def test_distribution_harness_rejects_mutated_metadata(tmp_path, metadata, message):
    _distribution(tmp_path, metadata=metadata)

    with pytest.raises(ValueError, match=message):
        VALIDATE(tmp_path, "1.8.0")


def test_distribution_harness_rejects_missing_sdist_file(tmp_path):
    _wheel(tmp_path)
    _sdist(tmp_path, omit="NOTICE")

    with pytest.raises(ValueError, match="Source distribution is missing: NOTICE"):
        VALIDATE(tmp_path, "1.8.0")


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_distribution_harness_rejects_duplicate_artifacts(tmp_path, artifact):
    _distribution(tmp_path)
    suffix = ".whl" if artifact == "wheel" else ".tar.gz"
    (tmp_path / f"content_creator-duplicate{suffix}").write_bytes(b"duplicate")

    with pytest.raises(ValueError, match="Expected one"):
        VALIDATE(tmp_path, "1.8.0")


@pytest.mark.parametrize("artifact", ["wheel", "sdist"])
def test_distribution_harness_rejects_corrupt_archives(tmp_path, artifact):
    _distribution(tmp_path)
    if artifact == "wheel":
        (tmp_path / "content_creator-1.8.0-py3-none-any.whl").write_bytes(b"not a zip")
        error = zipfile.BadZipFile
    else:
        (tmp_path / "content_creator-1.8.0.tar.gz").write_bytes(b"not a tarball")
        error = tarfile.ReadError

    with pytest.raises(error):
        VALIDATE(tmp_path, "1.8.0")
